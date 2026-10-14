/* Test-only adapter around actual production media code; no engine hooks. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <limits.h>
typedef int SysBusDevice;
typedef int MemoryRegion;
typedef int DeviceState;
typedef int ClockEvent;
typedef uint64_t hwaddr;
typedef struct { uint64_t hz; } Clock;
typedef struct QEMUTimer {
    int64_t expire_time, wake_time;
    uint64_t sequence;
    void (*cb)(void *);
    void *opaque;
    void *timer_list;
} QEMUTimer;
typedef int qemu_irq;
typedef struct { QEMUTimer *timer4; } P2DSoc;
#define OBJECT_DECLARE_SIMPLE_TYPE(a,b)
#define P2D_MEDIA(d) ((P2DMedia *)(d))
#define BIT(n) (1u << (n))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define NANOSECONDS_PER_SECOND 1000000000LL
#define MEMTXATTRS_UNSPECIFIED 0
#define MEMTX_OK 0
#define LOG_UNIMP 0
#define REPLAY_MODE_NONE 0
static int replay_mode;
static int address_space_memory;
static int64_t clock_now, external_deadline = -1;
static unsigned mods, dels, callbacks, reads, irq_count, first_irq, errors;
static uint32_t memory_epoch;
static uint64_t sequence, external_sequence;
static unsigned host_wakes, forced_drains;
static uint64_t digest = 1469598103934665603ULL;
static uint64_t clock_get_hz(Clock *c) { return c->hz; }
static int64_t qemu_clock_get_ns(int type) { return clock_now; }
#define QEMU_CLOCK_VIRTUAL 1
static void timer_del(QEMUTimer *t) { t->expire_time=-1; dels++; }
static void timer_mod(QEMUTimer *t,int64_t when) {
    t->expire_time=t->wake_time=when;t->sequence=++sequence;mods++;
}
static void timer_mod_coalesced_ns(QEMUTimer *t,int64_t when,int64_t wake) {
    timer_mod(t,when);t->wake_time=wake;
}
static int icount_enabled(void) { return 0; }
static bool qemu_clock_run_timers(int type);
static bool qemu_clock_expired(int type);
static bool timer_pending(QEMUTimer *t) { return t->expire_time >= 0; }
static bool timer_expired(QEMUTimer *t,int64_t now) {return t->expire_time<=now;}
static void external_arm(int64_t when) {
    external_deadline=when;external_sequence=++sequence;
}
static int64_t timerlist_next_deadline_ns(void *list) { return external_deadline; }
static int address_space_read(void *as,uint64_t addr,int attrs,uint8_t *bytes,int len) {
    uint16_t value=(addr ^ (addr>>16) ^ memory_epoch*173u);
    bytes[0]=value;bytes[1]=value>>8;reads++;return MEMTX_OK;
}
static uint16_t lduw_le_p(void *p) { uint8_t *a=p;return a[0]|a[1]<<8; }
#define qemu_log_mask(...) ((void)0)
static void qemu_irq_pulse(qemu_irq irq) {
    if (!first_irq) first_irq=19;
    irq_count++;
}
/* MODEL */
static void hash_bytes(const void *p,size_t n) {
    const uint8_t *b=p;
    for(size_t i=0;i<n;i++){digest^=b[i];digest*=1099511628211ULL;}
}
static void snapshot(P2DMedia *s) {
    for(unsigned i=0;i<9;i++) (void)dma_read(s,i*4,4);
    (void)iis_read(s,0,4);
    hash_bytes(s->dma,sizeof(s->dma));
    hash_bytes(s->iis,sizeof(s->iis));
    hash_bytes(s->fifo,sizeof(s->fifo));
    hash_bytes(&s->head,sizeof(s->head));
    hash_bytes(&s->level,sizeof(s->level));
    hash_bytes(&s->loaded,sizeof(s->loaded));
    hash_bytes(&s->serial_next,sizeof(s->serial_next));
    hash_bytes(&s->event_next,sizeof(s->event_next));
    hash_bytes(&reads,sizeof(reads));
    hash_bytes(&irq_count,sizeof(irq_count));
    hash_bytes(&first_irq,sizeof(first_irq));

}
static void drain(P2DMedia *s,int64_t now,bool observe) {
    clock_now=now;unsigned budget=0;
    while(++budget<2000000) {
        int64_t next=s->event->expire_time;
        if(external_deadline>=0 && external_deadline<=now &&
           (next<0 || external_deadline<next ||
            (external_deadline==next && external_sequence<s->event->sequence))) {
            if(!first_irq) first_irq=14;
            /* Real Timer4 raises IRQ/reloads; it does not read/change IIS.
             * Compare interrupt state here and complete device state after
             * the queue drain, including every CPU MMIO observation below. */
            hash_bytes(&irq_count,sizeof(irq_count));
            hash_bytes(&first_irq,sizeof(first_irq));
            external_deadline=-1;
            continue;
        }
        if(next<0 || next>now) break;
        s->event->expire_time=-1;callbacks++;
        media_event(s);
    }
    if(budget>=2000000) errors++;
    if(observe) {
        s->pclk->hz=30000000;
        media_clock(s,0);
    }
}
static P2DMedia *active_media;
static bool qemu_clock_run_timers(int type) {
    forced_drains++;drain(active_media,clock_now,false);return true;
}
static bool qemu_clock_expired(int type) {
    return (active_media->event->expire_time>=0 &&
            active_media->event->expire_time<=clock_now) ||
           (external_deadline>=0 && external_deadline<=clock_now);
}
static void poll_host(P2DMedia *s,int64_t now) {
    clock_now=now;
    if((s->event->expire_time>=0 && s->event->wake_time<=now) ||
       (external_deadline>=0 && external_deadline<=now)) {
        host_wakes++;drain(s,now,false);
    }
}
static void configure(P2DMedia *s,unsigned count,bool reload) {
    dma_write(s,0,0x300ac000,4);
    dma_write(s,4,0,4);
    dma_write(s,8,0x55000010,4);
    dma_write(s,12,3,4);
    dma_write(s,16,0xa0900000u | (reload?0:BIT(22)) | count,4);
    iis_write(s,0,0x23,4);
    iis_write(s,4,0xad,4);
    iis_write(s,8,0x42,4);
    iis_write(s,12,0xa000,4);
    dma_write(s,32,2,4);
}
static uint32_t random_state=123456789;
static uint32_t rnd(void) {random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
int main(int argc,char **argv) {
    Clock c={50700000};QEMUTimer timer={.expire_time=-1};
    P2DMedia s={.pclk=&c,.event=&timer};active_media=&s;
    unsigned scenario=argc>1?strtoul(argv[1],NULL,0):0;
#ifdef P2D_AUDIO_MODEL
    if(argc>2){s.audio=p2d_audio_open(argv[2]);s.output_enabled=true;}
#endif
    if(scenario==0) {
        configure(&s,50000,false);
        drain(&s,100000000,false);snapshot(&s);
    } else if(scenario==11) {
        configure(&s,50000,false);
        for(unsigned i=1;i<=1024;i++) poll_host(&s,(int64_t)i*11361);
        snapshot(&s);
    } else if(scenario==12) {
        configure(&s,50000,false);
        drain(&s,37*11361,false);
        snapshot(&s);
        if(dma_read(&s,20,4)!=49931 || dma_read(&s,24,4)!=0x300ac08a ||
           ((iis_read(&s,12,4)>>6)&63)!=32) errors++;
    } else if(scenario==13) {
        c.hz=120000000;configure(&s,64,false);
        iis_write(&s,0,0x21,4);iis_write(&s,4,0x89,4);
        poll_host(&s,1);
        poll_host(&s,33810);
        QEMUTimer peer={.expire_time=-1};
        P2DSoc soc={.timer4=&peer};
        timer_before_update(&soc);
        external_arm(34144);
        drain(&s,34144,false);snapshot(&s);
    } else if(scenario==14) {
        configure(&s,50000,false);
        poll_host(&s,1);poll_host(&s,150000);
        c.hz=30000000;media_clock(&s,0);
        snapshot(&s);
        drain(&s,350000,false);snapshot(&s);
    } else if(scenario==15) {
        configure(&s,50000,false);
        drain(&s,1000000,false);
        media_reset((DeviceState *)&s);
        clock_now=2000000;
        unsigned before=forced_drains;
        snapshot(&s);
        if(forced_drains!=before || s.event_next || s.serial_next ||
           s.level || s.loaded || timer.expire_time>=0) errors++;
    } else if(scenario<9) {
        /* Timer-first, DMA-first, equal deadline, mid-stream clock change,
         * initial prefill ordering, autoload, fixed source, invalid source. */
        if(scenario==5){c.hz=120000000;configure(&s,33,false);external_arm(500);}
        else {
            configure(&s,scenario==6?64:200,scenario==6);
            external_arm(scenario==1?100000:scenario==2?10000000:
                              scenario==3?11361:150000);
            if(scenario==7) dma_write(&s,4,1,4);
            if(scenario==8) dma_write(&s,0,0x2fffffff,4);
        }
        drain(&s,10000000,scenario==4);snapshot(&s);
        dma_write(&s,32,4,4);drain(&s,20000000,false);snapshot(&s);
    } else {
        configure(&s,2000,true);
        for(unsigned i=0;i<10000;i++) {
            uint32_t r=rnd();
            drain(&s,clock_now+(r%50000),false);
            switch(r%12) {
            case 0: iis_write(&s,0,(r>>8)&0x3f,4);break;
            case 1: iis_write(&s,4,(r>>8)&0x1ff,4);break;
            case 2: iis_write(&s,8,(r>>8)&0x3ff,4);break;
            case 3: iis_write(&s,12,(r>>8)&0xf000,4);break;
            case 4: iis_write(&s,16,r,2);break;
            case 5: dma_write(&s,32,(r>>8)&6,4);break;
            case 6: c.hz=12000000+(r%120000000);media_clock(&s,0);break;
            case 7: memory_epoch++;break;
            case 8: configure(&s,1+(r%500),r&BIT(9));break;
            case 9: dma_write(&s,0,r&BIT(8)?0x300ac000:0x37fffffe,4);break;
            case 10: external_arm(clock_now+(r%20000));break;
            default:break;
            }
            snapshot(&s);
        }
    }
    printf("{\"scenario\":%u,\"digest\":\"%016" PRIx64 "\",\"callbacks\":%u,\"host_wakes\":%u,\"timer_mods\":%u,\"timer_dels\":%u,\"reads\":%u,\"irqs\":%u,\"first_irq\":%u,\"remaining\":%u,\"current_address\":%u,\"fifo_level\":%u,\"errors\":%u}\n",scenario,digest,callbacks,host_wakes,mods,dels,reads,irq_count,first_irq,s.dma[5],s.dma[6],s.level,errors);
#ifdef P2D_AUDIO_MODEL
    p2d_audio_close(s.audio);
#endif
    return errors?1:0;
}
