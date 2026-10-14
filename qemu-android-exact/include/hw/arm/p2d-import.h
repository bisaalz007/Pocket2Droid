/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef P2D_IMPORT_H
#define P2D_IMPORT_H
#include "hw/core/cpu.h"
#include <dirent.h>

typedef struct P2DFolderFile {
    int fd;
    uint16_t mode;
    uint32_t position;
    char *name;
} P2DFolderFile;

typedef struct P2DFolderSearch {
    DIR *directory;
    char *pattern;
} P2DFolderSearch;

typedef struct P2DImport {
    CPUState *cpu;
    uint8_t *data;
    size_t size;
    bool handles[40], searches[40];
    uint16_t modes[40];
    uint32_t positions[40];
    unsigned trace_count;
    int root_fd;
    int move_state_fd, move_lock_fd;
    bool move_blocked;
    bool initialized;
    P2DFolderFile files[40];
    P2DFolderSearch find[40];
} P2DImport;

bool p2d_import_load(P2DImport *s, CPUState *cpu, const char *path,
                     const char *shared_folder, const char *move_state, Error **errp);
bool p2d_import_enabled(P2DImport *s);
void p2d_import_reset(P2DImport *s);
void p2d_import_cleanup(P2DImport *s);
uint32_t p2d_import_execute(P2DImport *s, uint32_t pb, uint32_t command);
#endif
