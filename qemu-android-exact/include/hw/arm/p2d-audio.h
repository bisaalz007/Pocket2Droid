/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef P2D_AUDIO_H
#define P2D_AUDIO_H
#include <stdbool.h>
#include <stdint.h>
#define P2D_AUDIO_SIZE 67648u
#define P2D_AUDIO_FRAMES 2048u
typedef struct P2DAudioOutput P2DAudioOutput;
P2DAudioOutput *p2d_audio_open(const char *path);
bool p2d_audio_publish(P2DAudioOutput *a, const int16_t *stereo,
                       uint32_t frames, uint32_t rate, uint32_t epoch);
bool p2d_audio_reset(P2DAudioOutput *a, uint32_t status, uint32_t epoch);
void p2d_audio_close(P2DAudioOutput *a);
#endif
