#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "net_setup.h"
typedef struct State { const P2DWChar *first,*after; int marker,reads,writes,commits,releases,query_error,apply_error,commit_error,attempted,begins,begin_error; unsigned version; } State;
static void check(int value,const char *why){if(!value){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
static int marker(void *p,unsigned *v){State*s=p;*v=s->version;if(s->attempted&&s->marker==1){*v=0;return 0;}return s->marker;}
static int query(void*p,const P2DWChar**out){State*s=p;*out=s->reads++?s->after:s->first;return s->query_error;}
static void release(void*p,const P2DWChar*x){State*s=p;(void)x;s->releases++;}
static int apply(void*p,const P2DWChar*x){State*s=p;s->writes++;check(s->attempted,"durable guard before apply");check(x!=0,"apply has XML");return s->apply_error;}
static int commit(void*p,unsigned v){State*s=p;check(v==1,"only version1 marker");s->commits++;return s->commit_error;}
static int begin_attempt(void*p){State*s=p;s->begins++;if(s->begin_error)return -1;s->attempted=1;return 0;}
static P2DSetupResult run(State*s){P2DSetupOps ops={s,marker,query,release,apply,commit,begin_attempt};return p2d_net_setup_run(&ops);}
static P2DWChar* load(const char*dir,const char*name){char path[4096];FILE*f;long n;char*bytes;P2DWChar*text;long i;snprintf(path,sizeof(path),"%s/%s",dir,name);f=fopen(path,"rb");check(f!=0,"fixture exists");fseek(f,0,SEEK_END);n=ftell(f);rewind(f);bytes=malloc((size_t)n+1);text=calloc((size_t)n+1,2);check(bytes&&text,"fixture allocation");check(fread(bytes,1,(size_t)n,f)==(size_t)n,"fixture read");fclose(f);for(i=0;i<n;i++){check((unsigned char)bytes[i]<128,"ASCII fixture");text[i]=(unsigned char)bytes[i];}free(bytes);return text;}
static P2DWChar* copy(const P2DWChar*s){size_t n=0;P2DWChar*d;while(s[n])n++;d=malloc((n+1)*2);check(d!=0,"copy");memcpy(d,s,(n+1)*2);return d;}
int main(int argc,char**argv){P2DWChar*stock,*after,*changed,*stock65,*after65;State s;size_t i;check(argc==2,"fixture directory");stock=load(argv[1],"stock-wm6.xml");after=load(argv[1],"configured-wm6.xml");stock65=load(argv[1],"stock-wm65.xml");after65=load(argv[1],"configured-wm65.xml");
#define FRESH() do{memset(&s,0,sizeof(s));s.marker=1;s.first=stock;s.after=after;}while(0)
 FRESH();check(run(&s)==P2D_SETUP_APPLIED&&s.writes==1&&s.commits==1&&s.reads==2&&s.releases==2,"stock applies once after exact readback");
 FRESH();s.first=stock65;s.after=after65;check(run(&s)==P2D_SETUP_APPLIED&&s.writes==1&&s.commits==1&&s.begins==1,"WM6.5 stock ReadOnly metadata applies with exact matching readback");
 FRESH();s.first=after65;check(run(&s)==P2D_SETUP_CUSTOM&&!s.writes&&!s.begins,"unmarked WM6.5 configured route is preserved");
 changed=copy(stock65);for(i=0;changed[i];i++)if(changed[i]=='R'&&changed[i+1]=='e'&&changed[i+2]=='a'&&changed[i+3]=='d'){size_t n=i;while(changed[n]&&changed[n]!='0')n++;check(changed[n]=='0',"ReadOnly fixture value");changed[n]='1';break;}
 FRESH();s.first=changed;check(run(&s)==P2D_SETUP_CUSTOM&&!s.writes&&!s.begins,"WM6.5 ReadOnly1 custom configuration is never normalized away");free(changed);
 FRESH();s.first=stock65;s.after=after;check(run(&s)==P2D_SETUP_FAILED&&s.writes==2&&!s.commits,"WM6.5 verification cannot accept mismatched older schema");
 FRESH();s.marker=0;s.version=1;s.first=0;check(run(&s)==P2D_SETUP_ALREADY_DONE&&!s.reads&&!s.writes&&!s.commits,"existing marker prevents queries and writes despite later user changes");
 FRESH();s.marker=0;s.version=2;check(run(&s)==P2D_SETUP_ALREADY_DONE&&!s.writes,"future marker preserved");
 FRESH();s.marker=0;s.version=0;check(run(&s)==P2D_SETUP_CUSTOM&&!s.writes,"unknown marker preserved");
 FRESH();s.marker=-1;check(run(&s)==P2D_SETUP_FAILED&&!s.reads&&!s.writes,"marker read failure prevents setup");
 FRESH();s.query_error=-1;check(run(&s)==P2D_SETUP_UNSUPPORTED&&!s.writes&&!s.commits,"denied query does not change settings");
 FRESH();s.begin_error=-1;check(run(&s)==P2D_SETUP_FAILED&&s.begins==1&&!s.writes&&!s.commits,"failed durable guard prevents all provisioning");
 FRESH();s.first=after;check(run(&s)==P2D_SETUP_CUSTOM&&!s.writes,"unmarked existing route is not overwritten");
 changed=copy(stock);for(i=0;changed[i];i++)if(changed[i]=='6'){changed[i]='7';break;}FRESH();s.first=changed;check(run(&s)==P2D_SETUP_CUSTOM&&!s.writes,"custom destination or planner parameter preserved");free(changed);
 FRESH();s.first=(const P2DWChar*)L"<bad>";check(run(&s)==P2D_SETUP_CUSTOM&&!s.writes,"malformed or unknown response preserved");
 FRESH();s.after=stock;check(run(&s)==P2D_SETUP_FAILED&&s.writes==2&&!s.commits,"failed readback removes only the owned route and never marks success");
 FRESH();s.apply_error=-1;check(run(&s)==P2D_SETUP_FAILED&&s.writes==2&&!s.commits,"partial apply failure attempts owned cleanup");
 FRESH();s.commit_error=-1;check(run(&s)==P2D_SETUP_FAILED&&s.writes==1&&s.commits==1,"uncertain marker persistence retains the verified route");
 s.first=stock;s.reads=0;s.commit_error=0;
 check(run(&s)==P2D_SETUP_CUSTOM&&s.writes==1&&s.commits==1,"marker failure then user route removal must never reapply on relaunch");
 check(p2d_net_setup_run(0)==P2D_SETUP_UNSUPPORTED,"missing API ops unsupported");
 free(stock);free(after);free(stock65);free(after65);puts("PASS setup policy: WM5/6/6.5 stock,custom,unknown,once-only,query/apply/readback/marker failure");return 0;}
