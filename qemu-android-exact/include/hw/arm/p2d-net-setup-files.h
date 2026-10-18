/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef P2D_NET_SETUP_FILES_H
#define P2D_NET_SETUP_FILES_H
typedef struct P2DNetSetupFiles {
    bool initialized;
    int fd, root_fd;
} P2DNetSetupFiles;
struct stat;
bool p2d_net_setup_files_load(P2DNetSetupFiles *s, const char *path,
                              int root_fd, Error **errp);
bool p2d_net_setup_files_active(P2DNetSetupFiles *s);
bool p2d_net_setup_files_handles(P2DNetSetupFiles *s, const char *relative_name);
bool p2d_net_setup_files_stat(P2DNetSetupFiles *s, bool directory, struct stat *st);
void p2d_net_setup_files_cleanup(P2DNetSetupFiles *s);
#endif
