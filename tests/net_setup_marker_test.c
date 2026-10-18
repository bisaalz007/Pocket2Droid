#include <stdio.h>
#include <stdlib.h>
#define _start guest_entry
#include "../guest/network-setup/net_setup.c"
#undef _start
static int present,deleted,fail_flush,machine_flushed,bad_order;
static int attempted,attempt_flushed,fail_attempt_flush,missing_flush;
static DWORD stored_version;
static int same(const P2DWChar*a,const P2DWChar*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static void check(int ok,const char*why){if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
static long fake_flush(HANDLE key){
    if(key==(HANDLE)0x80000002){machine_flushed=1;return 0;}
    if(key==(HANDLE)2){if(fail_attempt_flush)return 5;attempt_flushed=1;return 0;}
    return fail_flush?5:0;
}
HANDLE LoadLibraryW(const P2DWChar *s){(void)s;return (HANDLE)1;}
void *GetProcAddressW(HANDLE h,const P2DWChar *s){(void)h;(void)s;return missing_flush?0:(void*)fake_flush;}
long RegOpenKeyExW(HANDLE h,const P2DWChar*s,DWORD a,DWORD b,HANDLE*out){
    (void)h;(void)a;(void)b;
    if(same(s,attempt_key)){*out=(HANDLE)2;return attempted?0:2;}
    *out=(HANDLE)1;return present||attempted?0:2;
}
long RegQueryValueExW(HANDLE h,const P2DWChar*s,DWORD*a,DWORD*b,void*c,DWORD*d){
    (void)h;(void)s;(void)a;if(!present)return 2;*b=4;*(DWORD*)c=stored_version;*d=4;return 0;
}
long RegCreateKeyExW(HANDLE h,const P2DWChar*s,DWORD a,P2DWChar*b,DWORD c,DWORD d,void*e,HANDLE*out,DWORD*f){
    (void)h;(void)a;(void)b;(void)c;(void)d;(void)e;
    if(same(s,attempt_key)){*out=(HANDLE)2;*f=attempted?2:1;attempted=1;}
    else{*out=(HANDLE)1;*f=1;}return 0;
}
long RegSetValueExW(HANDLE h,const P2DWChar*s,DWORD a,DWORD b,const void*c,DWORD d){
    (void)h;(void)s;(void)a;(void)b;(void)d;if(!machine_flushed)bad_order=1;
    present=1;stored_version=*(const DWORD*)c;return 0;
}
long RegDeleteValueW(HANDLE h,const P2DWChar*s){(void)h;(void)s;present=0;deleted++;return 0;}
long RegCloseKey(HANDLE h){(void)h;return 0;}
void ExitThread(DWORD value){(void)value;}
int main(void){
    unsigned version=99;
    check(read_marker(0,&version)==1,"fresh guest has no markers");
    missing_flush=1;check(begin_attempt(0)==-1&&!attempted,"missing durability API creates no guard");missing_flush=0;
    fail_attempt_flush=1;
    check(begin_attempt(0)==-1&&attempted&&!attempt_flushed&&!present,"guard flush failure prevents authorization and never claims success");
    check(read_marker(0,&version)==0&&version==0,"uncertain attempt guard fails closed on relaunch");
    check(begin_attempt(0)==-1,"existing guard never authorizes another mutation");
    attempted=0;fail_attempt_flush=0;
    check(begin_attempt(0)==0&&attempted&&attempt_flushed&&!present,"fresh attempt is durably guarded without success marker");
    fail_flush=1;
    check(commit(0,1)==-1&&!present&&deleted==1,"partial marker flush failure removes Version");
    check(attempted&&read_marker(0,&version)==0&&version==0,"failed final marker retains once-only guard");
    check(!bad_order,"machine settings flush before success marker");
    fail_flush=0;machine_flushed=0;
    check(commit(0,1)==0&&present&&machine_flushed,"successful marker retained after machine flush");
    check(read_marker(0,&version)==0&&version==1,"verified success takes precedence over attempt guard");
    puts("PASS actual CE marker adapter: durable attempt, failure opt-out, atomic claim and partial-write cleanup");return 0;
}
