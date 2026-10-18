/* One-shot CE guest adapter: no UI, thread, file publication or ROM writes. */
#include "net_setup.h"
typedef unsigned long DWORD;
typedef void *HANDLE;
typedef long HRESULT;
typedef HRESULT (*ProcessConfig)(const P2DWChar *,DWORD,P2DWChar **);
typedef long (*FlushKey)(HANDLE);
extern HANDLE LoadLibraryW(const P2DWChar *);
extern void *GetProcAddressW(HANDLE,const P2DWChar *);
extern long RegOpenKeyExW(HANDLE,const P2DWChar *,DWORD,DWORD,HANDLE *);
extern long RegQueryValueExW(HANDLE,const P2DWChar *,DWORD *,DWORD *,void *,DWORD *);
extern long RegCreateKeyExW(HANDLE,const P2DWChar *,DWORD,P2DWChar *,DWORD,DWORD,void *,HANDLE *,DWORD *);
extern long RegSetValueExW(HANDLE,const P2DWChar *,DWORD,DWORD,const void *,DWORD);
extern long RegDeleteValueW(HANDLE,const P2DWChar *);
extern long RegCloseKey(HANDLE);
extern void ExitThread(DWORD);
static const P2DWChar marker_key[]=L"Software\\Pocket2Droid\\NetworkSetup";
static const P2DWChar attempt_key[]=L"Software\\Pocket2Droid\\NetworkSetup\\Attempt1";
static int read_marker(void *opaque,unsigned *version)
{
    HANDLE key;DWORD kind=0,size=4,value=0;long status;
    (void)opaque;
    status=RegOpenKeyExW((HANDLE)0x80000001,marker_key,0,0,&key);
    if(status==2)return 1;
    if(status)return -1;
    status=RegQueryValueExW(key,L"Version",0,&kind,&value,&size);RegCloseKey(key);
    if(status==2){
        status=RegOpenKeyExW((HANDLE)0x80000001,attempt_key,0,0,&key);
        if(status==2)return 1;
        if(status)return -1;
        RegCloseKey(key);*version=0;return 0;
    }
    if(status||kind!=4||size!=4)return -1;
    *version=(unsigned)value;return 0;
}
static int begin_attempt(void *opaque)
{
    HANDLE key,module;DWORD disposition;long status;FlushKey flush;
    (void)opaque;
    module=LoadLibraryW(L"coredll.dll");flush=module?(FlushKey)GetProcAddressW(module,L"RegFlushKey"):0;
    if(!flush)return -1;
    status=RegCreateKeyExW((HANDLE)0x80000001,attempt_key,0,0,0,0,0,&key,&disposition);
    if(status)return -1;
    /* Creation is the atomic claim: an existing guard never authorizes writes.
       Keep even an uncertain guard; manual setup is safer than reapplication. */
    status=disposition==1?flush(key):-1;
    RegCloseKey(key);return status?-1:0;
}
static int query(void *opaque,const P2DWChar **out)
{
    P2DWChar *answer=0;ProcessConfig fn=*(ProcessConfig *)opaque;
    HRESULT status=fn(p2d_setup_query,1,&answer);*out=answer;return status? -1:0;
}
static void release(void *opaque,const P2DWChar *answer)
{
    /* Bounded synchronous one-shot process: its API outputs live until exit.
       Never free another DLL's new[] output with an unrelated heap allocator. */
    (void)opaque;(void)answer;
}
static int apply(void *opaque,const P2DWChar *xml)
{
    P2DWChar *answer=0;ProcessConfig fn=*(ProcessConfig *)opaque;
    return fn(xml,1,&answer)?-1:0;
}
static int commit(void *opaque,unsigned version)
{
    HANDLE key,module;DWORD disposition,value=version;long status;FlushKey flush;
    (void)opaque;
    module=LoadLibraryW(L"coredll.dll");flush=module?(FlushKey)GetProcAddressW(module,L"RegFlushKey"):0;
    if(!flush)return -1;
    if(flush((HANDLE)0x80000002))return -1;
    status=RegCreateKeyExW((HANDLE)0x80000001,marker_key,0,0,0,0,0,&key,&disposition);
    if(status)return -1;
    status=RegSetValueExW(key,L"Version",0,4,&value,4);
    if(!status)status=flush(key);
    if(status){RegDeleteValueW(key,L"Version");flush(key);}
    RegCloseKey(key);return status?-1:0;
}
void _start(void)
{
    HANDLE module=LoadLibraryW(L"aygshell.dll");
    ProcessConfig fn=module?(ProcessConfig)GetProcAddressW(module,L"DMProcessConfigXML"):0;
    P2DSetupOps ops={&fn,read_marker,query,release,apply,commit,begin_attempt};
    P2DSetupResult result=fn?p2d_net_setup_run(&ops):P2D_SETUP_UNSUPPORTED;
    ExitThread((DWORD)result);
}
