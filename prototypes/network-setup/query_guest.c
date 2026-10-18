/* Disposable query-only guest probe. Never included in an APK. */
typedef unsigned long DWORD;
typedef unsigned short WCHAR;
typedef void *HANDLE;
typedef long HRESULT;
extern HANDLE CreateFileW(const WCHAR *, DWORD, DWORD, void *, DWORD, DWORD, HANDLE);
extern int WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
extern int CloseHandle(HANDLE);
extern int ReadFile(HANDLE, void *, DWORD, DWORD *, void *);
extern long RegOpenKeyExW(HANDLE,const WCHAR*,DWORD,DWORD,HANDLE*);
extern long RegQueryValueExW(HANDLE,const WCHAR*,DWORD*,DWORD*,void*,DWORD*);
extern long RegCloseKey(HANDLE);
extern HANDLE LoadLibraryW(const WCHAR *);
extern void *GetProcAddressW(HANDLE, const WCHAR *);
extern void ExitThread(DWORD);
extern int CreateProcessW(const WCHAR *, WCHAR *, void *, void *, int, DWORD, void *, void *, void *, void *);
typedef HRESULT (*ProcessConfig)(const WCHAR *, DWORD, WCHAR **);

static void text(HANDLE file, const char *s)
{
    DWORD n = 0, written;
    while (s[n]) n++;
    WriteFile(file, s, n, &written, 0);
}
static void number(HANDLE file, DWORD value)
{
    char buffer[11];
    unsigned i;
    buffer[0] = '0'; buffer[1] = 'x'; buffer[10] = '\n';
    for (i=0; i<8; i++) buffer[2+i] = "0123456789abcdef"[(value >> (28-4*i)) & 15];
    { DWORD n; WriteFile(file, buffer, 11, &n, 0); }
}
static const WCHAR path[] = L"\\Storage Card\\p2d-network-query.txt";
static const WCHAR xml[] = L"<wap-provisioningdoc><characteristic-query type=\"CM_ProxyEntries\"/><characteristic-query type=\"CM_Networks\"/><characteristic-query type=\"CM_Planner\"/></wap-provisioningdoc>";
void _start(void)
{
    HANDLE file = CreateFileW(path, 0x40000000, 1, 0, 2, 0x80, 0);
    HANDLE module;
    ProcessConfig process;
    WCHAR *result = 0;
    HRESULT status;
    DWORD n, written;
    if (file == (HANDLE)-1) ExitThread(1);
    text(file, "P2D query-only helper started\n");
    {
        HANDLE key;DWORD kind=0,size=4,value=0;
        long status=RegOpenKeyExW((HANDLE)0x80000001,L"Software\\Pocket2Droid\\NetworkSetup",0,0,&key);
        text(file,"marker-open=");number(file,(DWORD)status);
        if(!status){status=RegQueryValueExW(key,L"Version",0,&kind,&value,&size);RegCloseKey(key);text(file,"marker-status=");number(file,(DWORD)status);text(file,"marker-version=");number(file,value);}
        status=RegOpenKeyExW((HANDLE)0x80000001,L"Software\\Pocket2Droid\\NetworkSetup\\Attempt1",0,0,&key);
        text(file,"attempt-open=");number(file,(DWORD)status);if(!status)RegCloseKey(key);
    }
    module = LoadLibraryW(L"aygshell.dll");
    number(file, (DWORD)module);
    process = module ? (ProcessConfig)GetProcAddressW(module, L"DMProcessConfigXML") : 0;
    number(file, (DWORD)process);
    if (!process) { CloseHandle(file); ExitThread(2); }
    status = process(xml, 1, &result);
    number(file, (DWORD)status);
    if (result) {
        for (n=0; n<65536 && result[n]; n++);
        WriteFile(file, result, n*2, &written, 0);
    }
    {
        WCHAR input[4096];
        HANDLE apply = CreateFileW(L"\\Storage Card\\apply.xml", 0x80000000, 1, 0, 3, 0x80, 0);
        if (apply != (HANDLE)-1) {
            n = 0;
            if (ReadFile(apply, input, sizeof(input)-2, &n, 0) && n && !(n&1)) {
                WCHAR *answer = 0;
                HANDLE after;
                DWORD pi[4] = {0,0,0,0};
                input[n/2] = 0;
                status = process(input, 1, &answer);
                after = CreateFileW(L"\\Storage Card\\p2d-network-after.xml", 0x40000000, 1, 0, 2, 0x80, 0);
                if (after != (HANDLE)-1) {
                    number(after, (DWORD)status);
                    answer = 0;
                    status = process(xml, 1, &answer);
                    number(after, (DWORD)status);
                    if (answer) {
                        for(n=0;n<65536 && answer[n];n++);
                        WriteFile(after, answer, n*2, &written, 0);
                    }
                    CloseHandle(after);
                }
                if (CreateProcessW(L"\\Windows\\iexplore.exe", L"http://google.com/", 0, 0, 0, 0, 0, 0, 0, pi)) {
                    CloseHandle((HANDLE)pi[0]);CloseHandle((HANDLE)pi[1]);
                }
            }
            CloseHandle(apply);
        }
    }
    {
        HANDLE browse=CreateFileW(L"\\Storage Card\\browser.flag",0x80000000,1,0,3,0x80,0);
        if(browse!=(HANDLE)-1){
            DWORD pi[4]={0,0,0,0},bytes=0;WCHAR url[256];
            int valid=ReadFile(browse,url,sizeof(url)-2,&bytes,0)&&bytes&&!(bytes&1);
            CloseHandle(browse);url[valid?bytes/2:0]=0;
            if(CreateProcessW(L"\\Windows\\iexplore.exe",valid?url:L"http://google.com/",0,0,0,0,0,0,0,pi)){CloseHandle((HANDLE)pi[0]);CloseHandle((HANDLE)pi[1]);}
        }
    }
    /* The diagnostic process exits immediately. Its output allocation is
       reclaimed with its address space; do not guess another DLL's allocator. */
    CloseHandle(file);
    ExitThread(0);
}
