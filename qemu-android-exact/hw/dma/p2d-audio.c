/* SPDX-License-Identifier: GPL-2.0-or-later
 * Bounded host-only PCM transport. No QEMU/guest scheduling dependencies.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "hw/arm/p2d-audio.h"
#include <fcntl.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#define PCM 2112u
#define CAP 65536u
#define SLOTS 64u
#define MAX_NS 200000000ULL
struct P2DAudioOutput { int fd; uint8_t *map; bool failed; };
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t get64(const uint8_t *p) { return get32(p)|(uint64_t)get32(p+4)<<32; }
static void put32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;i++)p[i]=v>>(i*8); }
static void put64(uint8_t *p,uint64_t v) { put32(p,v);put32(p+4,v>>32); }
static bool lock_file(P2DAudioOutput *a,short type) {
    struct flock l={.l_type=type,.l_whence=SEEK_SET};
    return fcntl(a->fd,F_SETLK,&l)==0;
}
static bool valid(P2DAudioOutput *a) {
    const uint8_t *m=a->map;
    if(get32(m)!=0x41443250 || get32(m+4)!=1 || get32(m+8)!=P2D_AUDIO_SIZE ||
       get32(m+12)!=SLOTS || get32(m+16)!=CAP || get32(m+44)>3)return false;
    uint32_t wp=get32(m+20),rp=get32(m+24),wb=get32(m+28),rb=get32(m+32);
    if(wp-rp>SLOTS || wb-rb>CAP || (wb|rb)&3)return false;
    for(uint32_t i=0;i<wp-rp;i++) {
        const uint8_t *p=m+64+((rp+i)%SLOTS)*32;
        uint32_t frames=get32(p+8),rate=get32(p+4);
        if(!frames || frames>P2D_AUDIO_FRAMES || rate<8000 || rate>192000 ||
           get32(p+12)!=rb || get32(p)!=get32(m+36) || !get64(p+16) ||
           get32(p+24) || get32(p+28))return false;
        rb+=frames*4;
    }
    return rb==wb;
}
static uint64_t now_ns(void) {
    struct timespec t;
    return clock_gettime(CLOCK_MONOTONIC,&t)==0 ? (uint64_t)t.tv_sec*1000000000+t.tv_nsec : 0;
}
static void discard(uint8_t *m) {
    uint32_t rp=get32(m+24);const uint8_t *p=m+64+(rp%SLOTS)*32;
    put32(m+24,rp+1);put32(m+32,get32(p+12)+get32(p+8)*4);
    put32(m+40,get32(m+40)+1);
}
static void empty(uint8_t *m) { put32(m+24,get32(m+20));put32(m+32,get32(m+28)); }
P2DAudioOutput *p2d_audio_open(const char *path) {
    if(!path || !*path)return NULL;
    int fd=open(path,O_RDWR|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
    struct stat st;
    if(fd<0)return NULL;
    if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size!=P2D_AUDIO_SIZE){close(fd);return NULL;}
    uint8_t *map=mmap(NULL,P2D_AUDIO_SIZE,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(map==MAP_FAILED){close(fd);return NULL;}
    P2DAudioOutput *a=calloc(1,sizeof(*a));
    if(!a){munmap(map,P2D_AUDIO_SIZE);close(fd);return NULL;}
    a->fd=fd;a->map=map;
    if(!lock_file(a,F_WRLCK)){p2d_audio_close(a);return NULL;}
    bool ok=valid(a);lock_file(a,F_UNLCK);
    if(!ok){p2d_audio_close(a);return NULL;}
    return a;
}
bool p2d_audio_reset(P2DAudioOutput *a,uint32_t status,uint32_t epoch) {
    if(!a || a->failed || status>3 || !lock_file(a,F_WRLCK))return false;
    bool ok=valid(a);
    if(ok){empty(a->map);put32(a->map+36,epoch);put32(a->map+44,status);}
    else a->failed=true;
    if(!lock_file(a,F_UNLCK)){a->failed=true;ok=false;}
    return ok;
}
bool p2d_audio_publish(P2DAudioOutput *a,const int16_t *samples,uint32_t frames,uint32_t rate,uint32_t epoch) {
    if(!a || a->failed || !samples || !frames || frames>P2D_AUDIO_FRAMES || rate<8000 || rate>192000 || !epoch ||
       (uint64_t)frames*1000000000>(uint64_t)rate*MAX_NS ||
       !lock_file(a,F_WRLCK))return false;
    bool ok=valid(a);
    uint8_t *m=a->map;
    uint64_t now=now_ns();
    if(!ok || !now){a->failed=true;goto done;}
    if(get32(m+36)!=epoch)empty(m);
    put32(m+36,epoch);
    uint64_t duration=(uint64_t)frames*1000000000/rate;
    for(uint32_t i=0,n=get32(m+20)-get32(m+24);i<n;i++) {
        const uint8_t *p=m+64+((get32(m+24)+i)%SLOTS)*32;
        duration+=(uint64_t)get32(p+8)*1000000000/get32(p+4);
    }
    while(get32(m+20)!=get32(m+24)) {
        const uint8_t *p=m+64+(get32(m+24)%SLOTS)*32;
        uint64_t stamp=get64(p+16);
        bool stale=stamp>now || now-stamp>MAX_NS;
        if(!stale && duration<=MAX_NS && get32(m+20)-get32(m+24)<SLOTS &&
           get32(m+28)-get32(m+32)+frames*4<=CAP)break;
        duration-=(uint64_t)get32(p+8)*1000000000/get32(p+4);
        discard(m);
    }
    uint32_t wp=get32(m+20),wb=get32(m+28);
    for(uint32_t i=0;i<frames*2;i++) {
        uint32_t pos=(wb+i*2)%CAP;uint16_t value=samples[i];
        m[PCM+pos]=value;m[PCM+pos+1]=value>>8;
    }
    uint8_t *p=m+64+(wp%SLOTS)*32;
    put32(p,epoch);put32(p+4,rate);put32(p+8,frames);put32(p+12,wb);put64(p+16,now);put64(p+24,0);
    put32(m+28,wb+frames*4);put32(m+20,wp+1);put32(m+44,1);
done:
    if(!lock_file(a,F_UNLCK)){a->failed=true;ok=false;}
    return ok && !a->failed;
}
void p2d_audio_close(P2DAudioOutput *a) {
    if(a){munmap(a->map,P2D_AUDIO_SIZE);close(a->fd);free(a);}
}
