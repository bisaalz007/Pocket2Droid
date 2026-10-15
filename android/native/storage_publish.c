#define _GNU_SOURCE
#include <jni.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef RENAME_NOREPLACE
#define RENAME_NOREPLACE 1
#endif

static void error(JNIEnv *env, const char *operation, int saved_errno)
{
    char message[256];
    snprintf(message, sizeof(message), "%s: %s", operation, strerror(saved_errno));
    jclass type = (*env)->FindClass(env, "java/io/IOException");
    if (type) (*env)->ThrowNew(env, type, message);
}

JNIEXPORT jboolean JNICALL
Java_com_samsixx_pocket2droid_StoragePublish_publishNoReplace(JNIEnv *env, jclass type,
                                                         jstring from, jstring to)
{
    (void)type;
    const char *source = (*env)->GetStringUTFChars(env, from, NULL);
    if (!source) return JNI_FALSE;
    const char *destination = (*env)->GetStringUTFChars(env, to, NULL);
    if (!destination) { (*env)->ReleaseStringUTFChars(env, from, source); return JNI_FALSE; }
    int result;
    do { result = syscall(SYS_renameat2, AT_FDCWD, source, AT_FDCWD, destination, RENAME_NOREPLACE); }
    while (result < 0 && errno == EINTR);
    int saved_errno = errno;
    (*env)->ReleaseStringUTFChars(env, to, destination);
    (*env)->ReleaseStringUTFChars(env, from, source);
    if (result == 0) return JNI_TRUE;
    /* The caller must durably journal before attempting an exclusive copy.
       Never use ordinary rename(), which can replace another writer's save. */
    if (saved_errno == EINVAL || saved_errno == ENOSYS || saved_errno == ENOTSUP)
        return JNI_FALSE;
    error(env, "Publish without replacing existing file", saved_errno);
    return JNI_FALSE;
}

static int exclusive_copy(const char *source, const char *destination)
{
    int in = open(source, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (in < 0) return -1;
    struct stat st;
    if (fstat(in, &st) || !S_ISREG(st.st_mode) || st.st_size < 0) {
        int code = errno; if (!code) code = EINVAL;
        close(in); errno = code; return -1;
    }
    int out = open(destination, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (out < 0) { int code = errno; close(in); errno = code; return code == EEXIST ? 0 : -1; }
    char buffer[64 * 1024]; off_t total = 0; int code = 0;
    for (;;) {
        ssize_t count;
        do { count = read(in, buffer, sizeof buffer); } while (count < 0 && errno == EINTR);
        if (count < 0) { code = errno; break; }
        if (!count) { if (total != st.st_size) code = EIO; break; }
        if (count > st.st_size - total) { code = EIO; break; }
        for (ssize_t offset = 0; offset < count;) {
            ssize_t written;
            do { written = write(out, buffer + offset, (size_t)(count - offset)); }
            while (written < 0 && errno == EINTR);
            if (written <= 0) { code = written ? errno : EIO; break; }
            offset += written;
        }
        if (code) break;
        total += count;
    }
    if (!code) {
        int result; do { result = fsync(out); } while (result < 0 && errno == EINTR);
        if (result < 0) code = errno;
    }
    if (close(out) < 0 && !code) code = errno;
    if (close(in) < 0 && !code) code = errno;
    /* On failure leave both files intact. A private journal blocks incomplete
       publication; pathname-based deletion here could remove another writer. */
    if (code) { errno = code; return -1; }
    return 1;
}

JNIEXPORT jboolean JNICALL
Java_com_samsixx_pocket2droid_StoragePublish_copyNoReplace(JNIEnv *env, jclass type,
                                                      jstring from, jstring to)
{
    (void)type;
    const char *source = (*env)->GetStringUTFChars(env, from, NULL);
    if (!source) return JNI_FALSE;
    const char *destination = (*env)->GetStringUTFChars(env, to, NULL);
    if (!destination) { (*env)->ReleaseStringUTFChars(env, from, source); return JNI_FALSE; }
    int result = exclusive_copy(source, destination), code = errno;
    (*env)->ReleaseStringUTFChars(env, to, destination);
    (*env)->ReleaseStringUTFChars(env, from, source);
    if (result < 0) error(env, "Copy without replacing existing file", code);
    return result > 0 ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_com_samsixx_pocket2droid_StoragePublish_syncDirectoryPath(JNIEnv *env, jclass type,
                                                          jstring directory)
{
    (void)type;
    const char *path = (*env)->GetStringUTFChars(env, directory, NULL);
    if (!path) return JNI_FALSE;
    int fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    int saved_errno = errno;
    (*env)->ReleaseStringUTFChars(env, directory, path);
    if (fd < 0) { error(env, "Open storage directory", saved_errno); return JNI_FALSE; }
    int result;
    do { result = fsync(fd); } while (result < 0 && errno == EINTR);
    saved_errno = errno;
    int close_result = close(fd);
    if (result < 0) {
        /* FUSE may not implement directory fsync. Files are still fsynced and
           private rollback is retained; missing published saves fail closed. */
        if (saved_errno == EINVAL || saved_errno == ENOTSUP) return JNI_FALSE;
        error(env, "Sync storage directory", saved_errno); return JNI_FALSE;
    }
    if (close_result < 0) { error(env, "Close storage directory", errno); return JNI_FALSE; }
    return JNI_TRUE;
}
