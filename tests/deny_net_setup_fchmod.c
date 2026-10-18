/* Android app policy denies chmod on memfd; keep all other calls real. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int fchmod(int fd, mode_t mode)
{
    char name[64], target[256];
    snprintf(name, sizeof(name), "/proc/self/fd/%d", fd);
    ssize_t size = readlink(name, target, sizeof(target) - 1);
    if (size >= 0) {
        target[size] = 0;
        if (strstr(target, "memfd:p2d-network-setup")) {
            errno = EACCES;
            return -1;
        }
    }
    int (*real_fchmod)(int, mode_t) = dlsym(RTLD_NEXT, "fchmod");
    return real_fchmod(fd, mode);
}
