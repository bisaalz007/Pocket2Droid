/* Optional immutable guest setup bytes; no files in the real shared directory.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/bswap.h"
#include "qemu/memfd.h"
#include "hw/arm/p2d-net-setup-files.h"

bool p2d_net_setup_files_active(P2DNetSetupFiles *s)
{
    struct stat st;
    if (!s->initialized || s->fd < 0) {
        return false;
    }
    /* Digits have no case aliases. Any real inode, including a symlink,
     * owns this entire subtree; all lookup errors fail closed. */
    return fstatat(s->root_fd, "2577", &st, AT_SYMLINK_NOFOLLOW) && errno == ENOENT;
}

bool p2d_net_setup_files_handles(P2DNetSetupFiles *s, const char *relative_name)
{
    return !strcmp(relative_name, "2577") && p2d_net_setup_files_active(s);
}

bool p2d_net_setup_files_stat(P2DNetSetupFiles *s, bool directory, struct stat *st)
{
    if (fstat(s->fd, st)) {
        return false;
    }
    st->st_mode = directory ? S_IFDIR | 0500 : S_IFREG | 0400;
    if (directory) {
        st->st_size = 0;
    }
    return true;
}

void p2d_net_setup_files_cleanup(P2DNetSetupFiles *s)
{
    if (s->initialized && s->fd >= 0) {
        close(s->fd);
    }
    s->initialized = false;
    s->fd = -1;
}

bool p2d_net_setup_files_load(P2DNetSetupFiles *s, const char *path,
                              int root_fd, Error **errp)
{
    struct stat st;
    g_autofree uint8_t *bytes = NULL;
    int source = -1, image = -1;
    size_t done = 0, size;
    uint32_t pe;
    s->initialized = true;
    s->fd = -1;
    s->root_fd = root_fd;
    if (!fstatat(root_fd, "2577", &st, AT_SYMLINK_NOFOLLOW) || errno != ENOENT) {
        error_setg(errp, "Automatic network setup skipped: real StorageCard entry owns 2577");
        return false;
    }
    source = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (source < 0 || fstat(source, &st) || !S_ISREG(st.st_mode) ||
        st.st_size < 512 || st.st_size > 256 * 1024) {
        error_setg(errp, "Automatic network setup helper is unavailable or invalid");
        goto fail;
    }
    size = st.st_size;
    bytes = g_malloc(size);
    while (done < size) {
        ssize_t n = pread(source, bytes + done, size - done, done);
        if (n < 0 && errno == EINTR) {
            continue;
        }
        if (n <= 0) {
            error_setg(errp, "Automatic network setup helper could not be read");
            goto fail;
        }
        done += n;
    }
    pe = ldl_le_p(bytes + 60);
    if (memcmp(bytes, "MZ", 2) || pe > size - 96 ||
        memcmp(bytes + pe, "PE\0\0", 4) || lduw_le_p(bytes + pe + 4) != 0x1c0 ||
        lduw_le_p(bytes + pe + 20) < 72 || lduw_le_p(bytes + pe + 24) != 0x10b ||
        lduw_le_p(bytes + pe + 24 + 68) != 9 ||
        !(lduw_le_p(bytes + pe + 22) & 2) || (lduw_le_p(bytes + pe + 22) & 0x2000)) {
        error_setg(errp, "Automatic network setup helper is not an ARM CE executable");
        goto fail;
    }
    image = qemu_memfd_create("p2d-network-setup", size, false, 0,
                              F_SEAL_GROW | F_SEAL_SHRINK, errp);
    if (image < 0) {
        goto fail;
    }
    done = 0;
    while (done < size) {
        ssize_t n = pwrite(image, bytes + done, size - done, done);
        if (n < 0 && errno == EINTR) {
            continue;
        }
        if (n <= 0) {
            error_setg(errp, "Cannot snapshot automatic network setup helper");
            goto fail;
        }
        done += n;
    }
    /* Android app policy can deny chmod on memfd. The seals enforce byte
     * immutability; synthetic metadata and VCEFS enforce guest read-only access.
     * Changing the host mode is unnecessary and must not prevent delivery. */
    if (fcntl(image, F_ADD_SEALS, F_SEAL_WRITE | F_SEAL_SEAL)) {
        error_setg_errno(errp, errno, "Cannot seal automatic network setup helper");
        goto fail;
    }
    close(source);
    s->fd = image;
    return true;
fail:
    if (source >= 0) {
        close(source);
    }
    if (image >= 0) {
        close(image);
    }
    return false;
}
