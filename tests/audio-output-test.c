/* Exercise the actual standalone audio transport in a separate process. */
#include "hw/arm/p2d-audio.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int argc, char **argv)
{
    assert(argc == 3);
    P2DAudioOutput *a = p2d_audio_open(argv[1]);
    if (!a) { puts("OPEN_FAILED"); return 2; }
    int count = atoi(argv[2]);
    bool oversized = count == -1;
    if (oversized) count = 1;
    int16_t samples[4096];
    for (int i = 0; i < 2048; i++) { samples[2*i] = i ? 123 : 32767; samples[2*i+1] = i ? -456 : -32768; }
    int published = 0;
    for (int i = 0; i < count; i++) {
        published += p2d_audio_publish(a, samples, oversized ? 2048 : (count == 1 ? 2 : 480), oversized ? 8000 : 48000, 7);
    }
    p2d_audio_close(a);
    printf("PUBLISHED %d\n", published);
    return 0;
}
