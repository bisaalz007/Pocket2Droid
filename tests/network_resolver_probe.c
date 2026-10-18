/* Test-only real libslirp DNS/NAT client, no guest ROM or public DNS needed. */
#include <slirp/libslirp.h>
#include <arpa/inet.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
extern int get_dns_addr(struct in_addr *, uint16_t *);
extern int get_dns6_addr(struct in6_addr *, uint16_t *, uint32_t *);
static Slirp *s;
static struct pollfd fds[128];static int nfds,answer;
static int64_t now(void *o){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (int64_t)t.tv_sec*1000000000+t.tv_nsec;}
static int add(int fd,int ev,void *o){int i=nfds++;fds[i]=(struct pollfd){fd,((ev&SLIRP_POLL_IN)?POLLIN:0)|((ev&SLIRP_POLL_OUT)?POLLOUT:0),0};return i;}
static int events(int i,void *o){return ((fds[i].revents&POLLIN)?SLIRP_POLL_IN:0)|((fds[i].revents&POLLOUT)?SLIRP_POLL_OUT:0)|((fds[i].revents&POLLERR)?SLIRP_POLL_ERR:0);}
static slirp_ssize_t output(const void *v,size_t len,void *o){
    const unsigned char *p=v;
    if(len>=42&&p[12]==8&&p[13]==6&&p[21]==1){
        unsigned char a[42]={0};memcpy(a,p+6,6);memcpy(a+6,"\x02\x12\x34\x56\x78\x90",6);a[12]=8;a[13]=6;
        memcpy(a+14,p+14,8);a[21]=2;memcpy(a+22,a+6,6);memcpy(a+28,p+38,4);memcpy(a+32,p+22,6);memcpy(a+38,p+28,4);slirp_input(s,a,42);
    }
    if(len>54&&p[12]==8&&p[13]==0&&p[23]==17&&p[34]==0&&p[35]==53){
        answer=1;printf("packet ");for(size_t i=42;i<len;i++)printf("%02x",p[i]);puts("");
    }return len;
}
static void err(const char *x,void *o){}static void notify(void *o){}
static void registration(slirp_os_socket fd,void *o){}
int main(int argc,char **argv){
    SlirpConfig c={.version=6,.in_enabled=true};SlirpCb cb={.send_packet=output,.guest_error=err,.clock_get_ns=now,.notify=notify,.register_poll_socket=registration,.unregister_poll_socket=registration};
    inet_pton(AF_INET,"10.0.2.0",&c.vnetwork);inet_pton(AF_INET,"255.255.255.0",&c.vnetmask);inet_pton(AF_INET,"10.0.2.2",&c.vhost);inet_pton(AF_INET,"10.0.2.15",&c.vdhcp_start);inet_pton(AF_INET,"10.0.2.3",&c.vnameserver);
    setvbuf(stdout,NULL,_IOLBF,0);s=slirp_new(&c,&cb,NULL);if(!s)return 2;
    char line[64];unsigned seq=0;
    while(fgets(line,sizeof(line),stdin)){
        struct in_addr d;struct in6_addr d6;uint16_t port=0;uint32_t scope=0;char text[128];
        int result=line[0]=='6'?get_dns6_addr(&d6,&port,&scope):get_dns_addr(&d,&port);
        if(!result)inet_ntop(line[0]=='6'?AF_INET6:AF_INET,line[0]=='6'?(void*)&d6:(void*)&d,text,sizeof(text));else strcpy(text,"none");
        printf("resolver %s\n",text);
        if(line[0]=='n'){
            unsigned char p[68]={0};
            memcpy(p,"\x52\x55\x0a\0\2\3\2\x12\x34\x56\x78\x90\x08\0",14);
            p[14]=0x45;p[17]=54;p[22]=64;p[23]=17;memcpy(p+26,"\x0a\0\2\x0f\x0a\0\2\3",8);
            unsigned sum=0;for(int i=14;i<34;i+=2)sum+=(p[i]<<8)|p[i+1];sum=(sum&65535)+(sum>>16);sum=~sum;p[24]=sum>>8;p[25]=sum;
            p[34]=0x90;p[35]=++seq;p[37]=53;p[39]=34;
            memcpy(p+42,"\x12\x34\1\0\0\1\0\0\0\0\0\0\3p2d\4test\0\0\1\0\1",26);
            answer=0;slirp_input(s,p,68);
            int64_t until=now(NULL)+500000000;
            while(!answer&&now(NULL)<until){uint32_t ms=20;nfds=0;slirp_pollfds_fill(s,&ms,add,NULL);poll(fds,nfds,ms>20?20:ms);slirp_pollfds_poll(s,0,events,NULL);}
            if(!answer)puts("timeout");
        }
        puts("done");
    }slirp_cleanup(s);return 0;
}
