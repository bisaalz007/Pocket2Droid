#ifndef P2D_NET_SETUP_H
#define P2D_NET_SETUP_H
typedef unsigned short P2DWChar;
typedef enum P2DSetupResult { P2D_SETUP_APPLIED, P2D_SETUP_ALREADY_DONE,
    P2D_SETUP_CUSTOM, P2D_SETUP_UNSUPPORTED, P2D_SETUP_FAILED } P2DSetupResult;
typedef struct P2DSetupOps {
    void *opaque;
    int (*read_marker)(void *, unsigned *); /* 0 found,1 absent,-1 error */
    int (*query)(void *, const P2DWChar **);
    void (*release)(void *, const P2DWChar *);
    int (*apply)(void *, const P2DWChar *);
    int (*commit)(void *, unsigned);
    int (*begin_attempt)(void *); /* durable once-only guard before mutation */
} P2DSetupOps;
extern const P2DWChar p2d_setup_query[];
P2DSetupResult p2d_net_setup_run(const P2DSetupOps *ops);
#endif
