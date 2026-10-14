/* SPDX-License-Identifier: GPL-2.0-or-later
 * Local S3C2410 DMA2/IIS TX compatibility model. No host audio output.
 * Samsung S3C2410A manual, chapters8 and21 (keil.com/dd/docs/datashts/samsung/s3c2410_um.pdf).
 * Only the proven halfword, fixed IISFIFO, hardware TX request is implemented.
 * Unsupported transfers are reported; no completion is fabricated.
 */
#include "qemu/osdep.h"
#include "hw/core/sysbus.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-clock.h"
#include "hw/arm/pocket2droid-devemu.h"
#include "qemu/timer.h"
#include "qemu/log.h"
#include "qemu/bitops.h"
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
    int64_t serial_next, event_next;
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

static void media_schedule(P2DMedia *s)
{
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    int64_t period = sample_period(s);
    bool serial = (s->iis[0] & 1) && transmit_mode(s) && period &&
                  (s->level || dma_request(s));
    timer_del(s->event);
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
    if (s->event_next) {
        timer_mod(s->event, s->event_next);
    }
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
    int64_t fired = s->event_next;
    int64_t period = sample_period(s);
    media_fill(s);
    /* Keep the original serial phase. Consume one deadline per callback so
     * overdue expiries remain ordered against other devices in the timer list.
     * A late host callback must not advance a later DMA IRQ before timer4.
     */
    if (period && s->serial_next && fired >= s->serial_next && s->level) {
        s->head = (s->head + 1) & 31;
        s->level--;
        s->serial_next += period;
        media_fill(s);
    }
    media_schedule(s);
}

static uint64_t dma_read(void *opaque, hwaddr addr, unsigned size)
{
    P2DMedia *s = opaque;
    return s->dma[addr / 4];
}

static void dma_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    P2DMedia *s = opaque;
    unsigned slot = addr / 4;
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
    if (slot == 4) {
        if ((s->iis[3] & BIT(13)) && s->level < 32) {
            s->fifo[(s->head + s->level) & 31] = value;
            s->level++;
        }
    } else {
        unsigned shift = (addr & 3) * 8;
        uint32_t mask = size == 4 ? UINT32_MAX : ((1u << (size * 8)) - 1) << shift;
        s->iis[slot] = ((s->iis[slot] & ~mask) | ((value << shift) & mask)) & masks[slot];
        if (slot == 3 && !(s->iis[3] & BIT(13))) {
            s->level = s->head = 0;
        }
        s->serial_next = 0;
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
    s->serial_next = 0;
    timer_del(s->event);
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
    DeviceClass *dc = DEVICE_CLASS(oc);
    device_class_set_legacy_reset(dc, media_reset);
    dc->user_creatable = false;
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
