#include "net_setup.h"
#include "stock_wm6.h"
#include "stock_wm65.h"
const P2DWChar p2d_setup_query[] = L"<wap-provisioningdoc><characteristic-query type=\"CM_ProxyEntries\"/><characteristic-query type=\"CM_Networks\"/><characteristic-query type=\"CM_Planner\"/></wap-provisioningdoc>";
static const P2DWChar prefix[] = L"<wap-provisioningdoc><characteristic type=\"CM_ProxyEntries\">";
static const P2DWChar change[] = L"<wap-provisioningdoc><characteristic type=\"CM_ProxyEntries\"><characteristic type=\"P2D-Work-Internet\"><parm name=\"SrcId\" value=\"{A1182988-0D73-439E-87AD-2A5B369F808B}\"/><parm name=\"DestId\" value=\"{436EF144-B4FB-4863-A041-8F905A62C572}\"/><parm name=\"Proxy\" value=\"\"/><parm name=\"Type\" value=\"0\"/><parm name=\"Enable\" value=\"1\"/></characteristic></characteristic></wap-provisioningdoc>";
static const P2DWChar undo[] = L"<wap-provisioningdoc><characteristic type=\"CM_ProxyEntries\"><nocharacteristic type=\"P2D-Work-Internet\"/></characteristic></wap-provisioningdoc>";
static unsigned length(const P2DWChar *s)
{
    unsigned n=0;
    if(!s)return 0;
    while(n<16384 && s[n])n++;
    return n==16384?0:n;
}
static int same(const P2DWChar *a,const P2DWChar *b)
{
    unsigned n=length(a),m=length(b),i=0;
    if(!n||!m)return 0;
    while(n && a[n-1]<=32)n--;
    while(m && b[m-1]<=32)m--;
    while(i<n && a[i]<=32)i++;
    a+=i;n-=i;i=0;
    while(i<m && b[i]<=32)i++;
    b+=i;m-=i;
    if(n!=m)return 0;
    for(i=0;i<n;i++)if(a[i]!=b[i])return 0;
    return 1;
}
static int verified(const P2DWChar *s,const P2DWChar *stock,const P2DWChar *route)
{
    unsigned n=length(s),i=0,j,k=length(prefix),r=length(route);
    if(!n)return 0;
    while(s[i] && s[i]<=32)i++;
    for(j=0;j<k;j++)if(s[i+j]!=prefix[j])return 0;
    if(i+k+r>n)return 0;
    for(j=0;j<r;j++)if(s[i+k+j]!=route[j])return 0;
    return same(s+i+k+r,stock+k);
}
P2DSetupResult p2d_net_setup_run(const P2DSetupOps *o)
{
    const P2DWChar *answer=0;unsigned version=0;int status,stock,ok;
    if(!o||!o->read_marker||!o->query||!o->release||!o->apply||!o->commit||!o->begin_attempt)return P2D_SETUP_UNSUPPORTED;
    status=o->read_marker(o->opaque,&version);
    if(!status)return version?P2D_SETUP_ALREADY_DONE:P2D_SETUP_CUSTOM;
    if(status!=1)return P2D_SETUP_FAILED;
    status=o->query(o->opaque,&answer);
    stock=status?0:same(answer,STOCK_CONFIG)?1:same(answer,STOCK_WM65_CONFIG)?2:0;
    if(answer)o->release(o->opaque,answer);
    if(status)return P2D_SETUP_UNSUPPORTED;
    if(!stock)return P2D_SETUP_CUSTOM;
    if(o->begin_attempt(o->opaque))return P2D_SETUP_FAILED;
    if(o->apply(o->opaque,change)){o->apply(o->opaque,undo);return P2D_SETUP_FAILED;}
    answer=0;status=o->query(o->opaque,&answer);
    ok=!status&&verified(answer,stock==1?STOCK_CONFIG:STOCK_WM65_CONFIG,
                         stock==1?REPORTED_ROUTE:REPORTED_WM65_ROUTE);
    if(answer)o->release(o->opaque,answer);
    if(!ok){o->apply(o->opaque,undo);return P2D_SETUP_FAILED;}
    /* After verification, an I/O error can make marker persistence uncertain.
       Keep the working route so a possibly persisted marker remains truthful.
       The durable attempt guard prevents all later automatic writes, including
       after a user removes this route and the configuration becomes stock. */
    if(o->commit(o->opaque,1))return P2D_SETUP_FAILED;
    return P2D_SETUP_APPLIED;
}
