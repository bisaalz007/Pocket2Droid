/* Test-only fake-clock/notification adapter around actual QEMU timer code. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define QEMU_TIMER_ATTR_EXTERNAL 1
#define QEMU_CLOCK_REALTIME 0
#define QEMU_CLOCK_VIRTUAL 1
#define QEMU_CLOCK_HOST 2
#define QEMU_CLOCK_VIRTUAL_RT 3
#define REPLAY_MODE_NONE 0
#define CHECKPOINT_CLOCK_HOST 0
#define CHECKPOINT_CLOCK_VIRTUAL_RT 1
#define CHECKPOINT_CLOCK_VIRTUAL 2
#define RUN_ON_CPU_HOST_PTR(t) (t)
#define qatomic_read(p) (*(p))
#define qatomic_set(p,v) (*(p)=(v))
#define WITH_QEMU_LOCK_GUARD(p) for(int once=1;once;once=0)
typedef void QEMUTimerCB(void *);
typedef struct QEMUTimer QEMUTimer;
typedef struct {int type;bool enabled;} QEMUClock;
typedef struct QEMUTimerList {
    QEMUClock *clock;
    QEMUTimer *active_timers;
    int active_timers_lock,timers_done_ev;
} QEMUTimerList;
struct QEMUTimer {
    int64_t expire_time,wake_time;
    QEMUTimerList *timer_list;
    QEMUTimerCB *cb;
    void *opaque;
    QEMUTimer *next;
    int attributes,scale;
};
static __thread QEMUTimer *current_timer;
static __thread int64_t current_timer_wake;
static int replay_mode,icount_mode;
static int64_t now;
static unsigned notifications,callbacks;
static void *first_cpu;
static void timer_fire(void *unused) {assert(false);}
static void async_run_on_cpu(void *cpu,void (*cb)(void *),void *data) {assert(false);}
static int64_t qemu_clock_get_ns(int type) {return now;}
static int icount_enabled(void) {return icount_mode;}
static bool replay_checkpoint(int x) {return true;}
static void qemu_mutex_lock(int *p) {}
static void qemu_mutex_unlock(int *p) {}
static void qemu_event_reset(int *p) {}
static void qemu_event_set(int *p) {}
static void timerlist_notify(QEMUTimerList *list) {notifications++;}
/* ACTUAL_TIMER_FUNCTIONS */
static QEMUClock clock_state={QEMU_CLOCK_VIRTUAL,true};
static QEMUTimerList list={.clock=&clock_state}, nested={.clock=&clock_state};
static QEMUTimer media={.expire_time=-1,.wake_time=-1,.timer_list=&list,.scale=1};
static QEMUTimer peer={.expire_time=-1,.wake_time=-1,.timer_list=&list,.scale=1};
static QEMUTimer child={.expire_time=-1,.wake_time=-1,.timer_list=&nested,.scale=1};
static unsigned scenario;
static void noop(void *p) {callbacks++;}
static void *external_rearm(void *p) {
    timer_mod_coalesced_ns(&media,20,400);
    return NULL;
}
static void rearm(void *p) {
    callbacks++;
    if(scenario==1) timer_mod_coalesced_ns(&media,20,400);
    else if(scenario==2) timer_mod_coalesced_ns(&media,20,30);
    else if(scenario==3) timer_mod_coalesced_ns(&peer,20,400);
    else if(scenario==6) {
        pthread_t worker;
        assert(pthread_create(&worker,NULL,external_rearm,NULL)==0);
        assert(pthread_join(worker,NULL)==0);
    } else if(scenario==7) {
        timerlist_run_timers(&nested);
        assert(current_timer==&media && current_timer_wake==320);
        timer_mod_coalesced_ns(&media,20,400);
    } else assert(false);
}
int main(int argc,char **argv) {
    scenario=strtoul(argv[1],NULL,10);
    media.cb=rearm;peer.cb=child.cb=noop;
    if(scenario==0) {
        timer_mod_coalesced_ns(&media,10,320);
        assert(timerlist_next_deadline_ns(&list)==10);
        assert(timerlist_deadline_ns(&list)==320);
        unsigned before=notifications;
        timer_mod_ns(&peer,100);
        assert(notifications==before+1);
        assert(timerlist_deadline_ns(&list)==100);
        timer_del_locked(&list,&peer);
        assert(timerlist_deadline_ns(&list)==320);
        timer_mod_coalesced_ns(&peer,20,50);
        assert(timerlist_deadline_ns(&list)==50);
    } else if(scenario<=3 || scenario==6 || scenario==7) {
        timer_mod_coalesced_ns(&media,10,320);
        if(scenario==7) timer_mod_ns(&child,5);
        notifications=0;now=10;timerlist_run_timers(&list);
        assert(callbacks==(scenario==7?2:1));
        assert(notifications==((scenario==2 || scenario==3 || scenario==6)?1:0));
        assert(current_timer==NULL);
    } else if(scenario==4) {
        timer_mod_coalesced_ns(&media,10,320);
        timer_mod_ns(&media,15);
        assert(media.wake_time==15 && timerlist_deadline_ns(&list)==15);
        timer_mod_anticipate_ns(&media,5);
        assert(media.wake_time==5 && timerlist_deadline_ns(&list)==5);
        clock_state.enabled=false;
        assert(timerlist_deadline_ns(&list)==-1);
        clock_state.enabled=true;
        timer_del_locked(&list,&media);
        assert(timerlist_deadline_ns(&list)==-1);
    } else if(scenario==5) {
        replay_mode=1;timer_mod_coalesced_ns(&media,10,320);
        assert(media.wake_time==10 && timerlist_deadline_ns(&list)==10);
        replay_mode=0;icount_mode=1;timer_mod_coalesced_ns(&media,20,640);
        assert(media.wake_time==20 && timerlist_deadline_ns(&list)==20);
    } else assert(false);
    printf("{\"scenario\":%u,\"notifications\":%u,\"callbacks\":%u,\"passed\":true}\n",
           scenario,notifications,callbacks);
}
