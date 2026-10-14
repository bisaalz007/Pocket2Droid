/* SPDX-License-Identifier: GPL-2.0-or-later
 * Local S3C2410 DMA2/IIS TX compatibility model, optional host-only PCM export.
 * Samsung S3C2410A manual, chapters8 and21 (keil.com/dd/docs/datashts/samsung/s3c2410_um.pdf).
 * Only the proven halfword, fixed IISFIFO, hardware TX request is implemented.
 * Unsupported transfers are reported; no completion is fabricated.
 */
#include "qemu/osdep.h"
#include "hw/core/sysbus.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-clock.h"
#include "hw/arm/pocket2droid-devemu.h"
#include "hw/arm/p2d-audio.h"
#include "hw/core/qdev-properties.h"
#include "qemu/error-report.h"
#include "qemu/timer.h"
#include "qemu/log.h"
#include "qemu/bitops.h"
#include "system/replay.h"
#include "exec/icount.h"
#include "system/address-spaces.h"

typedef struct P2DMedia {
    SysBusDevice parent;
    MemoryRegion dma_mr, iis_mr;
    Clock *pclk;
    QEMUTimer *event;
    qemu_irq irq;
    uint32_t dma[9], iis[5];
    uint16_t fifo[32];
    unsigned head, level;
    bool loaded;
    int64_t serial_next, event_next, serial_period;
    char *audio_path;
    P2DAudioOutput *audio;
    bool output_enabled, output_half;
    unsigned output_phase, output_frames, output_target, output_status;
    uint32_t output_rate, output_epoch;
    int16_t output_left, output_pcm[4096];
} P2DMedia;
OBJECT_DECLARE_SIMPLE_TYPE(P2DMedia, P2D_MEDIA)

static bool dma_supported(P2DMedia *s)
{
    uint32_t c = s->dma[4];
    return (c & BIT(23)) && ((c >> 24) & 7) == 0 &&
           ((c >> 20) & 3) == 1 && !(c & (BIT(28) | BIT(27))) &&
           s->dma[2] == 0x55000010 && (s->dma[3] & 3) == 3;
}

static bool transmit_mode(P2DMedia *s)
{
    return (s->iis[1] & 0x80) && (s->iis[3] & BIT(13)) && !(s->iis[0] & BIT(3));
}

static bool dma_request(P2DMedia *s)
{
    return (s->dma[8] & 2) && dma_supported(s) && transmit_mode(s) &&
           (s->iis[0] & BIT(5)) && (s->iis[3] & BIT(15)) && s->level < 32 &&
           (s->loaded ? s->dma[5] != 0 : (s->dma[4] & 0xfffff) != 0);
}

static int64_t sample_period(P2DMedia *s)
{
    uint64_t hz = clock_get_hz(s->pclk);
    unsigned div = (s->iis[1] & 4) ? 384 : 256;
    if (s->iis[0] & 2) {
        div *= ((s->iis[2] >> 5) & 31) + 1;
    }
    /* Two halfword samples per stereo frame. Slave clock is not wired. */
    if (!hz || (s->iis[1] & BIT(8))) {
        return 0;
    }
    return MAX(1, (NANOSECONDS_PER_SECOND * div + 2 * hz - 1) / (2 * hz));
}

static void media_output_flush(P2DMedia *s)
{
    if (s->output_frames && s->audio && s->output_enabled) {
        p2d_audio_publish(s->audio, s->output_pcm, s->output_frames,
                          s->output_rate, s->output_epoch);
    }
    s->output_frames = 0;
}

/* Host discontinuities never reset the serial channel phase. */
static void media_output_boundary(P2DMedia *s, bool reset_phase)
{
    media_output_flush(s);
    s->output_half = false;
    if (reset_phase) {
        s->output_phase = 0;
    }
    if (!++s->output_epoch) {
        s->output_epoch = 1;
    }
    uint64_t hz = clock_get_hz(s->pclk);
    unsigned div = (s->iis[1] & 4) ? 384 : 256;
    if (s->iis[0] & 2) {
        div *= ((s->iis[2] >> 5) & 31) + 1;
    }
    uint64_t rate = (hz + div / 2) / div;
    bool supported = (s->iis[1] & BIT(3)) && !(s->iis[1] & BIT(8)) &&
                     rate >= 8000 && rate <= 192000;
    s->output_rate = supported ? rate : 0;
    s->output_target = supported ? (rate + 99) / 100 : 0;
    bool active = transmit_mode(s) && (s->iis[0] & 1);
    s->output_status = !s->audio ? (s->audio_path ? 3 : 0) :
                       !s->output_enabled || !active ? 0 : supported ? 1 : 2;
    p2d_audio_reset(s->audio, s->output_status, s->output_epoch);
}

static void media_output_sample(P2DMedia *s, uint16_t value)
{
    unsigned phase = s->output_phase;
    s->output_phase ^= 1;
    if (!s->output_enabled || !s->audio || !s->output_rate) {
        return;
    }
    if (!phase) {
        s->output_left = value;
        s->output_half = true;
    } else if (s->output_half) {
        unsigned i = s->output_frames * 2;
        s->output_pcm[i] = s->output_left;
        s->output_pcm[i + 1] = value;
        s->output_half = false;
        if (++s->output_frames >= s->output_target) {
            media_output_flush(s);
        }
    }
}

static void media_next(P2DMedia *s, int64_t now, int64_t period)
{
    bool serial = (s->iis[0] & 1) && transmit_mode(s) && period &&
                  (s->level || dma_request(s));
    s->event_next = 0;
    if (!serial) {
        s->serial_next = 0;
    } else if (!s->serial_next) {
        s->serial_next = now + period;
    }
    if (dma_request(s)) {
        s->event_next = serial ? MIN(s->serial_next, now + 1) : now + 1;
    } else if (serial) {
        s->event_next = s->serial_next;
    }
}

/*
 * Keep the next logical deadline in the normal timer queue. A separate wake
 * hint may postpone only the host poll; peers and forced MMIO synchronization
 * still drain logical deadlines in their original order.
 */
static void media_arm(P2DMedia *s)
{
    int64_t wake = s->event_next;
    int64_t period = s->serial_period;
    if (!wake) {
        timer_del(s->event);
        return;
    }
    if (replay_mode == REPLAY_MODE_NONE && !icount_enabled() && period &&
        wake == s->serial_next && s->level && !dma_request(s)) {
        unsigned units = MIN(32, s->level);
        if ((s->dma[8] & 2) && dma_supported(s) && transmit_mode(s) &&
            (s->iis[0] & BIT(5)) && (s->iis[3] & BIT(15))) {
            unsigned left = s->loaded ? s->dma[5] : s->dma[4] & 0xfffff;
            if (left) {
                units = MIN(units, left);
            }
        }
        wake += (units - 1) * period;
    }
    timer_mod_coalesced_ns(s->event, s->event_next, wake);
}

static void media_sync(P2DMedia *s)
{
    if (replay_mode == REPLAY_MODE_NONE && !icount_enabled() &&
        s->event_next &&
        s->event_next <= qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)) {
        /* Drain peers too: direct catch-up would bypass equal-deadline IRQs. */
        qemu_clock_run_timers(QEMU_CLOCK_VIRTUAL);
    }
}

static void media_schedule(P2DMedia *s)
{
    s->serial_period = sample_period(s);
    media_next(s, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL), s->serial_period);
    media_arm(s);
}

static void media_fill(P2DMedia *s)
{
    if (dma_request(s)) {
        if (!s->loaded) {
            s->dma[5] = s->dma[4] & 0xfffff;
            s->dma[6] = s->dma[0] & 0x7fffffff;
            s->dma[7] = s->dma[2] & 0x7fffffff;
            s->loaded = true;
        }
        while (s->level < 32 && s->dma[5]) {
            uint8_t bytes[2];
            uint32_t addr = s->dma[6];
            /* Read actual mapped bytes. Do not recurse into arbitrary MMIO. */
            if (!((addr < 96 * 1024 * 1024 - 1) ||
                  (addr >= 0x30000000 && addr < 0x37ffffff)) ||
                address_space_read(&address_space_memory, addr, MEMTXATTRS_UNSPECIFIED,
                                   bytes, 2) != MEMTX_OK) {
                qemu_log_mask(LOG_UNIMP, "p2d DMA2 invalid source 0x%08x\n", addr);
                s->dma[8] = 0;
                break;
            }
            s->fifo[(s->head + s->level) & 31] = lduw_le_p(bytes);
            s->level++;
            if (!(s->dma[1] & 1)) {
                s->dma[6] += 2;
            }
            s->dma[5]--;
            if (!s->dma[5]) {
                if (s->dma[4] & BIT(29)) {
                    qemu_irq_pulse(s->irq);
                }
                s->loaded = false;
                if (s->dma[4] & BIT(22)) {
                    s->dma[8] = 0;
                }
                break;
            }
        }
    }
}

static void media_event(void *opaque)
{
    P2DMedia *s = opaque;
    int64_t period = s->serial_period;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    int64_t limit = s->event_next;
    unsigned budget = 1;

    /*
     * The main-loop callback holds BQL: guest MMIO and the other board timers
     * cannot interleave inside it. Batch only deadlines already due at entry,
     * strictly before the next queued callback (ties retain queue ordering).
     * Preserve every sample/DMA read, FIFO transition and IRQ in that interval.
     * Record/replay retains the ordinary one-event path. Bound each callback
     * to limit work in one callback; the timer list may invoke it again.
     */
    if (replay_mode == REPLAY_MODE_NONE) {
        int64_t other = timerlist_next_deadline_ns(s->event->timer_list);
        limit = other < 0 ? now : MIN(now, other - 1);
        budget = 1024;
    }
    do {
        int64_t fired = s->event_next;
        media_fill(s);
        if (period && s->serial_next && fired >= s->serial_next && s->level) {
            media_output_sample(s, s->fifo[s->head]);
            s->head = (s->head + 1) & 31;
            s->level--;
            s->serial_next += period;
            media_fill(s);
        }
        media_next(s, now, period);
    } while (--budget && s->event_next && s->event_next <= limit);
    if (!s->event_next) {
        media_output_flush(s);
    }
    media_arm(s);
}

static uint64_t dma_read(void *opaque, hwaddr addr, unsigned size)
{
    P2DMedia *s = opaque;
    media_sync(s);
    return s->dma[addr / 4];
}

static void dma_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    P2DMedia *s = opaque;
    unsigned slot = addr / 4;
    media_sync(s);
    if (slot >= 5 && slot <= 7) {
        return;
    }
    if (slot == 8) {
        s->dma[8] = (value & 4) ? 0 : (value & 2);
        if (!s->dma[8]) {
            s->dma[5] = 0;
            s->loaded = false;
        } else if (!dma_supported(s)) {
            qemu_log_mask(LOG_UNIMP, "p2d DMA2 unsupported DCON=0x%08x DIDST=0x%08x\n",
                          s->dma[4], s->dma[2]);
        }
    } else {
        s->dma[slot] = value;
    }
    media_schedule(s);
}

static uint64_t iis_read(void *opaque, hwaddr addr, unsigned size)
{
    P2DMedia *s = opaque;
    uint32_t value;
    unsigned slot = addr / 4;
    media_sync(s);
    if (slot == 0) {
        value = s->iis[0] | 0x100 | (s->level ? 0x80 : 0);
    } else if (slot == 3) {
        value = s->iis[3] | (s->level << 6);
    } else {
        value = s->iis[slot];
    }
    return (value >> ((addr & 3) * 8)) & (size == 4 ? UINT32_MAX : (1u << (size * 8)) - 1);
}

static void iis_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    P2DMedia *s = opaque;
    unsigned slot = addr / 4;
    static const uint32_t masks[5] = { 0x3f, 0x1ff, 0x3ff, 0xf000, 0 };
    media_sync(s);
    if (slot == 4) {
        if ((s->iis[3] & BIT(13)) && s->level < 32) {
            s->fifo[(s->head + s->level) & 31] = value;
            s->level++;
        }
    } else {
        uint32_t previous = s->iis[slot];
        unsigned shift = (addr & 3) * 8;
        uint32_t mask = size == 4 ? UINT32_MAX : ((1u << (size * 8)) - 1) << shift;
        s->iis[slot] = ((s->iis[slot] & ~mask) | ((value << shift) & mask)) & masks[slot];
        if (slot == 3 && !(s->iis[3] & BIT(13))) {
            s->level = s->head = 0;
        }
        s->serial_next = 0;
        if (s->iis[slot] != previous) {
            bool reset_phase = (slot == 3 && !(s->iis[3] & BIT(13))) ||
                               (slot == 0 && ((previous ^ s->iis[0]) & 1)) ||
                               (slot == 1 && ((previous ^ s->iis[1]) & (BIT(3) | BIT(7) | BIT(8))));
            media_output_boundary(s, reset_phase);
        }
    }
    media_schedule(s);
}

static const MemoryRegionOps dma_ops = {
    .read = dma_read, .write = dma_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4, .valid.max_access_size = 4,
};
static const MemoryRegionOps iis_ops = {
    .read = iis_read, .write = iis_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1, .valid.max_access_size = 4,
};

static void media_clock(void *opaque, ClockEvent event)
{
    P2DMedia *s = opaque;
    media_sync(s);
    media_output_boundary(s, false);
    s->serial_next = 0;
    media_schedule(s);
}

static void media_reset(DeviceState *dev)
{
    P2DMedia *s = P2D_MEDIA(dev);
    memset(s->dma, 0, sizeof(s->dma));
    memset(s->iis, 0, sizeof(s->iis));
    s->level = s->head = 0;
    s->loaded = false;
    s->serial_next = s->event_next = s->serial_period = 0;
    timer_del(s->event);
    media_output_boundary(s, true);
}

static void media_realize(DeviceState *dev, Error **errp)
{
    P2DMedia *s = P2D_MEDIA(dev);
    s->audio = p2d_audio_open(s->audio_path);
    if (s->audio_path && !s->audio) {
        error_report("p2d sound output unavailable; guest continues without playback");
    }
    media_output_boundary(s, true);
}

static void media_unrealize(DeviceState *dev)
{
    P2DMedia *s = P2D_MEDIA(dev);
    p2d_audio_close(s->audio);
    s->audio = NULL;
}

static bool media_get_enabled(Object *obj, Error **errp)
{
    return P2D_MEDIA(obj)->output_enabled;
}

static void media_set_enabled(Object *obj, bool value, Error **errp)
{
    P2DMedia *s = P2D_MEDIA(obj);
    media_sync(s);
    if (s->output_enabled != value) {
        s->output_enabled = value;
        media_output_boundary(s, false);
    }
}

static char *media_get_status(Object *obj, Error **errp)
{
    static const char * const names[] = { "inactive", "ready", "unsupported-format", "output-failed" };
    return g_strdup(names[P2D_MEDIA(obj)->output_status]);
}

static void media_init(Object *obj)
{
    P2DMedia *s = P2D_MEDIA(obj);
    SysBusDevice *bus = SYS_BUS_DEVICE(obj);
    s->event = timer_new_ns(QEMU_CLOCK_VIRTUAL, media_event, s);
    s->pclk = qdev_init_clock_in(DEVICE(obj), "pclk", media_clock, s, ClockUpdate);
    memory_region_init_io(&s->dma_mr, obj, &dma_ops, s, "p2d.dma2", 36);
    memory_region_init_io(&s->iis_mr, obj, &iis_ops, s, "p2d.iis", 20);
    sysbus_init_mmio(bus, &s->dma_mr);
    sysbus_init_mmio(bus, &s->iis_mr);
    sysbus_init_irq(bus, &s->irq);
}

static void media_class(ObjectClass *oc, const void *data)
{
    static const Property props[] = {
        DEFINE_PROP_STRING("audio-file", P2DMedia, audio_path),
    };
    DeviceClass *dc = DEVICE_CLASS(oc);
    dc->realize = media_realize;
    dc->unrealize = media_unrealize;
    device_class_set_props(dc, props);
    device_class_set_legacy_reset(dc, media_reset);
    dc->user_creatable = false;
    object_class_property_add_bool(oc, "output-enabled", media_get_enabled, media_set_enabled);
    object_class_property_add_str(oc, "output-status", media_get_status, NULL);
}
static const TypeInfo media_type = {
    .name = TYPE_P2D_MEDIA, .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(P2DMedia), .instance_init = media_init,
    .class_init = media_class,
};
static void media_register(void)
{
    type_register_static(&media_type);
}
type_init(media_register)
