/* SPDX-License-Identifier: GPL-2.0-or-later
 * Standalone shared-frame producer; fcntl locks interoperate with FileChannel.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include "hw/arm/p2d-frame.h"

static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; ++i) { p[i] = v >> (i * 8); }
}
static void put64(uint8_t *p, uint64_t v)
{
    for (unsigned i = 0; i < 8; ++i) { p[i] = v >> (i * 8); }
}

bool p2d_frame_open(P2DFrame *f, const char *path)
{
    struct stat st;
    int fd = open(path, O_RDWR | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) { return false; }
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size != P2D_FRAME_SIZE) {
        close(fd); return false;
    }
    uint8_t *map = mmap(NULL, P2D_FRAME_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED) { close(fd); return false; }
    *f = (P2DFrame){ .fd = fd, .map = map };
    return true;
}

bool p2d_frame_publish(P2DFrame *f, const uint32_t *pixels,
                       unsigned w, unsigned h, size_t stride)
{
    struct flock lock = { .l_type = F_WRLCK, .l_whence = SEEK_SET };
    if (!f->map || !w || !h || w > P2D_FRAME_WIDTH || h > P2D_FRAME_HEIGHT ||
        stride < w * 4u || fcntl(f->fd, F_SETLK, &lock) < 0) { return false; }
    bool changed = f->width != w || f->height != h;
    for (unsigned y = 0; !changed && y < h; ++y) {
        const uint32_t *src = (const uint32_t *)((const uint8_t *)pixels + y * stride);
        for (unsigned x = 0; x < w; ++x) {
            uint32_t pixel;
            memcpy(&pixel, f->map + 64 + (y * w + x) * 4, 4);
            if (pixel != (src[x] | 0xff000000u)) { changed = true; break; }
        }
    }
    if (changed) {
        for (unsigned y = 0; y < h; ++y) {
            const uint32_t *src = (const uint32_t *)((const uint8_t *)pixels + y * stride);
            for (unsigned x = 0; x < w; ++x) {
                put32(f->map + 64 + (y * w + x) * 4, src[x] | 0xff000000u);
            }
        }
        memcpy(f->map, "P2DF", 4);
        put32(f->map + 4, 1);
        put32(f->map + 8, w);
        put32(f->map + 12, h);
        put32(f->map + 16, 1);
        put64(f->map + 24, ++f->sequence);
        f->width = w; f->height = h;
    }
    lock.l_type = F_UNLCK;
    if (fcntl(f->fd, F_SETLK, &lock) < 0) { return false; }
    return changed;
}

void p2d_frame_close(P2DFrame *f)
{
    if (f->map) { munmap(f->map, P2D_FRAME_SIZE); }
    if (f->fd >= 0) { close(f->fd); }
    *f = (P2DFrame){ .fd = -1 };
}
