/* Test-only x86 syscall forwarding and scoped filesystem failure injection. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

void *p2d_next_syscall __attribute__((visibility("hidden")));
__attribute__((constructor)) static void init(void)
{ p2d_next_syscall=dlsym(RTLD_NEXT,"syscall"); }
__asm__(".text\n.globl syscall\n.type syscall,@function\nsyscall:\n"
        "cmp $316,%rdi\nje p2d_test_renameat2\njmp *p2d_next_syscall(%rip)\n"
        ".size syscall,.-syscall\n.hidden p2d_next_syscall\n.hidden p2d_test_renameat2\n");
long p2d_test_renameat2(long nr,int dir,const char *name,int dir2,const char *name2,unsigned flags)
{
    (void)dir;(void)name;(void)dir2;(void)name2;(void)flags;
    if(getenv("P2D_TEST_MOVE_RENAME_FAIL")) { errno=EINVAL;return -1; }
    return ((long(*)(long,int,const char*,int,const char*,unsigned))p2d_next_syscall)(nr,dir,name,dir2,name2,flags);
}
static int path_matches(int fd,const char *wanted)
{
    if(!wanted)return 0;
    char name[64],path[4096];snprintf(name,sizeof(name),"/proc/self/fd/%d",fd);
    ssize_t n=readlink(name,path,sizeof(path)-1);if(n<0)return 0;path[n]=0;return !strcmp(wanted,path);
}
ssize_t write(int fd,const void *bytes,size_t size)
{
    static long limit=-2;
    if(path_matches(fd,getenv("P2D_TEST_MOVE_WRITE_TARGET"))) {
        if(limit==-2)limit=7;
        if(!limit){errno=EIO;return -1;}
        if(size>(size_t)limit)size=limit;
        ssize_t n=((ssize_t(*)(int,const void*,size_t))dlsym(RTLD_NEXT,"write"))(fd,bytes,size);
        if(n>0)limit-=n;return n;
    }
    return ((ssize_t(*)(int,const void*,size_t))dlsym(RTLD_NEXT,"write"))(fd,bytes,size);
}
int fsync(int fd)
{
    static int calls;
    static int swapped;
    if(!swapped && path_matches(fd,getenv("P2D_TEST_MOVE_SWAP_DIR"))) {
        const char *name=getenv("P2D_TEST_MOVE_SWAP_NAME"),*replacement=getenv("P2D_TEST_MOVE_SWAP_REPLACEMENT");
        const char *backup=getenv("P2D_TEST_MOVE_SWAP_BACKUP");
        if(!name||!replacement||!backup||rename(name,backup)||rename(replacement,name)) { errno=EIO;return -1; }
        swapped=1;
    }
    if(path_matches(fd,getenv("P2D_TEST_MOVE_SYNC_TARGET"))) {
        int nth=atoi(getenv("P2D_TEST_MOVE_SYNC_NTH"));calls++;
        if(!nth||calls==nth){errno=EIO;return -1;}
    }
    return ((int(*)(int))dlsym(RTLD_NEXT,"fsync"))(fd);
}
