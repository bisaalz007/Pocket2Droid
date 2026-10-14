#define _GNU_SOURCE
#include <assert.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include "hw/arm/p2d-frame.h"

int main(void)
{
    char path[] = "/tmp/p2d-frame-test-XXXXXX";
    char linkpath[256];
    int fd = mkstemp(path);
    P2DFrame frame = { .fd = -1 };
    uint32_t pixels[] = { 0x00112233, 0x00445566, 0, 0x00778899, 0x00aabbcc, 0 };
    uint8_t *map;
    assert(fd >= 0);
    assert(!p2d_frame_open(&frame, path)); /* Wrong length rejected. */
    assert(ftruncate(fd, P2D_FRAME_SIZE) == 0);
    snprintf(linkpath, sizeof(linkpath), "%s-link", path);
    assert(symlink(path, linkpath) == 0);
    assert(!p2d_frame_open(&frame, linkpath));
    unlink(linkpath);
    assert(p2d_frame_open(&frame, path));
    map = mmap(NULL, P2D_FRAME_SIZE, PROT_READ, MAP_SHARED, fd, 0);
    assert(map != MAP_FAILED);
    assert(p2d_frame_publish(&frame, pixels, 2, 2, 12));
    assert(memcmp(map, "P2DF", 4) == 0);
    assert(*(uint64_t *)(map + 24) == 1);
    assert(*(uint32_t *)(map + 64) == 0xff112233);
    assert(*(uint32_t *)(map + 72) == 0xff778899); /* Stride skipped. */
    assert(!p2d_frame_publish(&frame, pixels, 2, 2, 12));
    assert(*(uint64_t *)(map + 24) == 1);
    assert(!p2d_frame_publish(&frame, pixels, 1025, 2, 12));
    /* Another process holds reader lock: producer must skip, then retry. */
    int ready[2], finish[2];
    assert(pipe(ready) == 0 && pipe(finish) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (!child) {
        struct flock lock = { .l_type = F_RDLCK, .l_whence = SEEK_SET };
        assert(fcntl(fd, F_SETLK, &lock) == 0);
        assert(write(ready[1], "r", 1) == 1);
        char c;
        assert(read(finish[0], &c, 1) == 1);
        _exit(0);
    }
    char c;
    assert(read(ready[0], &c, 1) == 1);
    pixels[0] = 0x00abcdef;
    assert(!p2d_frame_publish(&frame, pixels, 2, 2, 12));
    assert(*(uint64_t *)(map + 24) == 1);
    assert(write(finish[1], "f", 1) == 1);
    int status;
    assert(waitpid(child, &status, 0) == child && status == 0);
    assert(p2d_frame_publish(&frame, pixels, 2, 2, 12));
    assert(*(uint64_t *)(map + 24) == 2);
    assert(*(uint32_t *)(map + 64) == 0xffabcdef);
    uint32_t *wvga = calloc(480 * 800, sizeof(uint32_t));
    assert(wvga);
    wvga[480 * 800 - 1] = 0x00123456;
    assert(p2d_frame_publish(&frame, wvga, 480, 800, 480 * 4));
    assert(*(uint32_t *)(map + 12) == 800);
    assert(*(uint32_t *)(map + 64 + (480 * 800 - 1) * 4) == 0xff123456);
    assert(!p2d_frame_publish(&frame, wvga, 480, 801, 480 * 4));
    free(wvga);
    p2d_frame_close(&frame);
    munmap(map, P2D_FRAME_SIZE);
    close(fd);
    unlink(path);
    puts("PASS frame protocol, duplicate suppression, stride, bounds, locking");
    return 0;
}
