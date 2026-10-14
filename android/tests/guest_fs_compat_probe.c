/* Disposable host filesystem operations used by the guest SD-card bridge. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static void report(const char *name,int result,int code)
{ printf("%s result=%d errno=%d message=%s\n",name,result,code,strerror(code)); }

int main(int argc,char **argv)
{
    if(argc!=2) return 2;
    const char *root=argv[1];
    if(strncmp(root,"/sdcard/.p2d-guest-fs-probe-",28) &&
       strncmp(root,"/data/local/tmp/.p2d-guest-fs-probe-",36)) return 2;
    if(strstr(root,"..") || strlen(root)>300 || mkdir(root,0700)) return 2;
    char source[400],target[400];
    snprintf(source,sizeof(source),"%s/source",root);snprintf(target,sizeof(target),"%s/target",root);
    int fd=open(source,O_CREAT|O_EXCL|O_RDWR|O_CLOEXEC,0664);
    if(fd<0 || write(fd,"prepared",8)!=8 || fsync(fd)) return 1;
    struct stat st;if(fstat(fd,&st)) return 1;
    printf("file uid=%u gid=%u mode=%o\n",st.st_uid,st.st_gid,st.st_mode&0777);
    errno=0;int r=fchmod(fd,st.st_mode&0777),code=errno;report("fchmod_unchanged",r,code);
    errno=0;r=fchmod(fd,(st.st_mode&0777)&~0222);code=errno;report("fchmod_readonly",r,code);
    if(fstat(fd,&st)) return 1;
    printf("mode_after_readonly=%o\n",st.st_mode&0777);
    errno=0;r=fchmod(fd,(st.st_mode&0777)|S_IWUSR);code=errno;report("fchmod_writable",r,code);
    struct timespec times[2]={{.tv_nsec=UTIME_OMIT},{.tv_sec=1700000000}};
    errno=0;r=futimens(fd,times);code=errno;report("futimens_dos_timestamp",r,code);
    if(fstat(fd,&st)) return 1;
    printf("mtime_after=%lld\n",(long long)st.st_mtime);
    if(close(fd)) return 1;
    errno=0;r=syscall(SYS_renameat2,AT_FDCWD,source,AT_FDCWD,target,1);code=errno;report("rename_noreplace",r,code);
    if(!r && rename(target,source)) return 1;
    errno=0;r=link(source,target);code=errno;report("hard_link",r,code);
    if(!r && unlink(target)) return 1;
    if(unlink(source) || rmdir(root)) return 1;
    puts("PASS owned probe files removed; no emulator/user-data access");return 0;
}
