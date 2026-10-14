/* Disposable filesystem reproduction. Never opens Pocket2Droid's real files. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    const char *root = argv[1];
    if (strncmp(root, "/sdcard/.p2d-storage-probe-", 27) &&
        strncmp(root, "/data/local/tmp/.p2d-storage-probe-", 35)) return 2;
    if (strstr(root, "..") || strlen(root) > 300) return 2;
    if (mkdir(root, 0700)) { perror("Fresh probe directory"); return 1; }
    char source[400], target[400];
    snprintf(source, sizeof source, "%s/source", root);
    snprintf(target, sizeof target, "%s/target", root);
    int fd = open(source, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, "A", 1) != 1 || fsync(fd) || close(fd)) return 1;
    errno = 0;
    int result = syscall(SYS_renameat2, AT_FDCWD, source, AT_FDCWD, target, 1);
    int code = errno;
    printf("rename_noreplace result=%d errno=%d message=%s\n", result, code, strerror(code));
    if (!result) {
        if (rename(target, source)) return 1; /* Both are newly owned test paths. */
    }
    errno = 0; result = link(source, target); code = errno;
    printf("hard_link result=%d errno=%d message=%s\n", result, code, strerror(code));
    if (!result && unlink(target)) return 1;
    fd = open(target, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, "B", 1) != 1 || fsync(fd) || close(fd)) return 1;
    errno = 0; fd = open(target, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600); code = errno;
    printf("exclusive_existing result=%d errno=%d message=%s\n", fd, code, strerror(code));
    if (fd >= 0 || code != EEXIST) return 1;
    fd = open(target, O_RDONLY | O_CLOEXEC); char value = 0;
    if (fd < 0 || read(fd, &value, 1) != 1 || close(fd) || value != 'B') return 1;
    fd = open(root, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) return 1;
    errno = 0; result = fsync(fd); code = errno;
    printf("directory_sync result=%d errno=%d message=%s\n", result, code, strerror(code));
    if (close(fd)) return 1;
    /* Only the exact two probe files; never recursive cleanup. */
    if (unlink(source) || unlink(target) || rmdir(root)) return 1;
    puts("PASS preserved exclusive target; owned probe files removed");
    return 0;
}
