/* Host-test-only syscall/write faults; never linked into Android release. */
#undef syscall
#undef write
#undef fsync
#define _GNU_SOURCE
#include <errno.h>
#include <jni.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <stdio.h>
#include <unistd.h>

static long fail_after = -1;
static char sync_path[4096];
static int sync_fault, sync_nth, sync_calls;
int p2d_test_fsync(int fd)
{
    struct stat info;
    char link[64], path[4096];
    if (sync_fault && fstat(fd,&info)==0 && S_ISDIR(info.st_mode)) {
        snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
        ssize_t n=readlink(link,path,sizeof(path)-1);
        if(n>=0) {
            path[n]=0;
            if(!strcmp(path,sync_path) && (++sync_calls==sync_nth || sync_nth==0)) {
                errno=sync_fault==1 ? EINVAL : EIO; return -1;
            }
        }
    }
    return fsync(fd);
}
JNIEXPORT void JNICALL Java_com_samsixx_pocket2droid_StorageFallbackTest_directoryFault
    (JNIEnv *env,jclass type,jstring path,jint fault,jint nth)
{
    (void)type;
    const char *p=(*env)->GetStringUTFChars(env,path,NULL);
    if(!p) return;
    snprintf(sync_path,sizeof(sync_path),"%s",p);
    (*env)->ReleaseStringUTFChars(env,path,p);
    sync_fault=fault;sync_nth=nth;sync_calls=0;
}
long p2d_test_syscall(long number, ...)
{
    va_list ap; va_start(ap, number);
    int from_dir=va_arg(ap,int); const char *from=va_arg(ap,const char *);
    int to_dir=va_arg(ap,int); const char *to=va_arg(ap,const char *);
    unsigned flags=va_arg(ap,unsigned); va_end(ap);
    if (number!=SYS_renameat2) abort();
    if (getenv("P2D_TEST_STORAGE_UNSUPPORTED") &&
        (strstr(to,"/pocket2droid/") || strstr(to,"/shared/"))) {
        errno=EINVAL; return -1;
    }
    return syscall(number,from_dir,from,to_dir,to,flags);
}
ssize_t p2d_test_write(int fd, const void *bytes, size_t count)
{
    if (fail_after==0) { errno=EIO; return -1; }
    if (fail_after>0 && count>(size_t)fail_after) count=(size_t)fail_after;
    ssize_t result=write(fd,bytes,count);
    if (result>0 && fail_after>0) fail_after-=result;
    return result;
}
JNIEXPORT void JNICALL Java_com_samsixx_pocket2droid_StorageFallbackTest_failAfter
    (JNIEnv *env,jclass type,jlong bytes)
{ (void)env; (void)type; fail_after=bytes; }
