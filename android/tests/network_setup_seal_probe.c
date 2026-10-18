/* Isolated Android app-UID characterization: no ROM, card or save access. */
#define _GNU_SOURCE
#include <jni.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

JNIEXPORT jstring JNICALL
Java_com_samsixx_p2dsealprobe_SealProbe_run(JNIEnv *env, jclass type)
{
    char output[4096];
    size_t used = 0;
    int failures = 0;
    (void)type;
#define RECORD(name, result) do { \
    int value = (result), saved = errno; \
    used += snprintf(output + used, sizeof(output) - used, \
                     "%s=%d errno=%d (%s)\n", name, value, \
                     value < 0 ? saved : 0, value < 0 ? strerror(saved) : "ok"); \
} while (0)
    used += snprintf(output + used, sizeof(output) - used, "uid=%d\n", getuid());
    for (int old = 1; old >= 0; old--) {
        used += snprintf(output + used, sizeof(output) - used,
                         "sequence=%s\n", old ? "released-with-fchmod" : "seals-only");
        int fd = syscall(__NR_memfd_create, "p2d-seal-isolated",
                         MFD_CLOEXEC | MFD_ALLOW_SEALING);
        RECORD("memfd_create", fd);
        if (fd < 0) { failures++; continue; }
        RECORD("ftruncate", ftruncate(fd, 512));
        RECORD("initial-seals", fcntl(fd, F_ADD_SEALS, F_SEAL_GROW | F_SEAL_SHRINK));
        RECORD("initial-write", (int)pwrite(fd, "probe", 5, 0));
        if (old) RECORD("fchmod-0400", fchmod(fd, 0400));
        int sealed = fcntl(fd, F_ADD_SEALS, F_SEAL_WRITE | F_SEAL_SEAL);
        RECORD("final-seals", sealed);
        int seals = fcntl(fd, F_GET_SEALS);
        RECORD("get-seals", seals);
        int write_result = pwrite(fd, "X", 1, 0), write_errno = errno;
        RECORD("write-after-seal", write_result);
        int resize_result = ftruncate(fd, 513), resize_errno = errno;
        RECORD("grow-after-seal", resize_result);
        char bytes[5] = {0};
        int read_result = pread(fd, bytes, sizeof(bytes), 0);
        int expected = F_SEAL_WRITE | F_SEAL_SEAL | F_SEAL_GROW | F_SEAL_SHRINK;
        if (sealed || seals < 0 || (seals & expected) != expected ||
            write_result != -1 || write_errno != EPERM ||
            resize_result != -1 || resize_errno != EPERM ||
            read_result != 5 || memcmp(bytes, "probe", 5)) failures++;
        close(fd);
    }
    snprintf(output + used, sizeof(output) - used, "immutability_failures=%d\n", failures);
    return (*env)->NewStringUTF(env, output);
}
