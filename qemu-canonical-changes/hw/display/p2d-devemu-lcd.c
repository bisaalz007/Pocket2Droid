/* SPDX-License-Identifier: GPL-2.0-or-later
 * Local Device Emulator LCD register/framebuffer prototype.
 */
#include "qemu/osdep.h"
#include "hw/core/sysbus.h"
#include "hw/arm/pocket2droid-devemu.h"
#include "hw/arm/p2d-frame.h"
#include "hw/core/qdev-properties.h"
#include "qapi/error.h"
#include "qemu/timer.h"
#include "ui/console.h"
#include "system/address-spaces.h"
#include "system/runstate.h"

typedef struct P2DLcd {
    SysBusDevice parent;
    MemoryRegion mmio;
    QemuConsole *console;
    uint32_t regs[32];
    char *frame_path;
    P2DFrame frame;
    QEMUTimer *frame_timer;
} P2DLcd;
OBJECT_DECLARE_SIMPLE_TYPE(P2DLcd, P2D_LCD)

static bool lcd_update(void *opaque)
{
    P2DLcd *s = opaque;
    DisplaySurface *surface;
    unsigned width = ((s->regs[2] >> 8) & 0x7ff) + 1;
    unsigned height = ((s->regs[1] >> 14) & 0x3ff) + 1;
    unsigned stride = (s->regs[7] & 0x7ff) + ((s->regs[7] >> 11) & 0x7ff);
    hwaddr base = (hwaddr)(s->regs[5] & 0x3fffffff) << 1;
    uint8_t row[2048];
    unsigned x, y;

    if (!(s->regs[0] & 1) || ((s->regs[0] >> 1) & 15) != 12 ||
        width > P2D_FRAME_WIDTH || height > P2D_FRAME_HEIGHT || !stride || stride < width ||
        base < 0x30000000 || base + (hwaddr)stride * height * 2 > 0x38000000) {
        return true;
    }
    qemu_console_resize(s->console, width, height);
    surface = qemu_console_surface(s->console);
    for (y = 0; y < height; ++y) {
        uint32_t *dest = (uint32_t *)(surface_data(surface) + y * surface_stride(surface));
        if (address_space_read(&address_space_memory, base + y * stride * 2,
                               MEMTXATTRS_UNSPECIFIED, row, width * 2) != MEMTX_OK) {
            return true;
        }
        for (x = 0; x < width; ++x) {
            uint16_t pixel = lduw_le_p(row + x * 2);
            unsigned r, g, b;
            if (s->regs[4] & (1u << 11)) {
                r = (pixel >> 11) & 31;
                g = (pixel >> 5) & 63;
                b = pixel & 31;
                g = (g << 2) | (g >> 4);
            } else {
                r = (pixel >> 10) & 31;
                g = (pixel >> 5) & 31;
                b = pixel & 31;
                g = (g << 3) | (g >> 2);
            }
            r = (r << 3) | (r >> 2);
            b = (b << 3) | (b >> 2);
            dest[x] = (r << 16) | (g << 8) | b;
        }
    }
    qemu_console_update(s->console, 0, 0, width, height);
    if (s->frame.map) {
        p2d_frame_publish(&s->frame, (uint32_t *)surface_data(surface),
                          width, height, surface_stride(surface));
    }
    return true;
}

static void lcd_frontend_refresh(void *opaque)
{
    P2DLcd *s = opaque;
    if (runstate_is_running()) { lcd_update(s); }
    timer_mod(s->frame_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 16);
}

static const GraphicHwOps lcd_gfx = {
    .gfx_update = lcd_update,
};

static uint64_t lcd_read(void *opaque, hwaddr addr, unsigned size)
{
    P2DLcd *s = opaque;
    return s->regs[addr / 4];
}

static void lcd_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    P2DLcd *s = opaque;
    if (addr == 0x54 || addr == 0x58) {
        s->regs[addr / 4] &= ~value;
    } else {
        s->regs[addr / 4] = value;
    }
}

static const MemoryRegionOps lcd_ops = {
    .read = lcd_read, .write = lcd_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 4, .valid.max_access_size = 4,
};

static void lcd_reset(DeviceState *dev)
{
    P2DLcd *s = P2D_LCD(dev);
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x5c / 4] = 3;
    qemu_console_resize(s->console, 240, 320);
}

static void lcd_realize(DeviceState *dev, Error **errp)
{
    P2DLcd *s = P2D_LCD(dev);
    s->frame.fd = -1;
    if (s->frame_path) {
        if (!p2d_frame_open(&s->frame, s->frame_path)) {
            error_setg(errp, "p2d frame-file must be an existing regular file of exactly %u bytes", P2D_FRAME_SIZE);
            return;
        }
        s->frame_timer = timer_new_ms(QEMU_CLOCK_REALTIME, lcd_frontend_refresh, s);
        timer_mod(s->frame_timer, qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + 16);
    }
    s->console = qemu_graphic_console_create(dev, 0, &lcd_gfx, s);
}

static const Property lcd_properties[] = {
    DEFINE_PROP_STRING("frame-file", P2DLcd, frame_path),
};

static void lcd_init(Object *obj)
{
    P2DLcd *s = P2D_LCD(obj);
    memory_region_init_io(&s->mmio, obj, &lcd_ops, s, "p2d.lcd", 0x80);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->mmio);
}

static void lcd_class(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    dc->realize = lcd_realize;
    dc->user_creatable = false;
    device_class_set_props(dc, lcd_properties);
    device_class_set_legacy_reset(dc, lcd_reset);
}

static const TypeInfo lcd_type = {
    .name = TYPE_P2D_LCD, .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(P2DLcd), .instance_init = lcd_init, .class_init = lcd_class,
};
static void lcd_register(void)
{
    type_register_static(&lcd_type);
}
type_init(lcd_register)
