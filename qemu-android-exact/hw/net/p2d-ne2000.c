/* SPDX-License-Identifier: GPL-2.0-or-later
 * Stock SDK single-slot PC Card aperture. NE2000 packet/DMA logic is upstream.
 * No hotplug or general ExCA address translation is claimed.
 */
#include "qemu/osdep.h"
#include "hw/core/sysbus.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/irq.h"
#include "hw/net/p2d-ne2000.h"
#include "qemu/module.h"
#include "ne2000.h"

OBJECT_DECLARE_SIMPLE_TYPE(P2DNet, P2D_NE2000)
struct P2DNet {
    SysBusDevice parent_obj;
    MemoryRegion memory, ports;
    NE2000State net;
    qemu_irq card_irq, management_irq;
    uint8_t index, pd[0x45], chip, cor, fcsr;
    bool nic_level;
};

static const uint8_t cis[] = {
    0x01, 0x03, 0xd9, 0x01, 0xff,
    0x15, 0x19, 0x04, 0x01,
    'P','C','M','C','I','A',0,
    'E','t','h','e','r','n','e','t',' ','C','a','r','d',0,0,0xff,
    0x20, 0x04, 0x01, 0x8a, 0x00, 0x01,
    0x21, 0x02, 0x06, 0x03,
    0x1a, 0x05, 0x01, 0x24, 0xf8, 0x03, 0x03,
    0x1b, 0x0b, 0xe0, 0x81, 0x18, 0xca, 0x60, 0x00, 0x03, 0x1f, 0x30, 0xff, 0xff,
    0x14, 0, 0xff,
};

static bool powered(P2DNet *s) { return (s->pd[2] & 0x90) == 0x90; }
static bool socket_ready(P2DNet *s) { return powered(s) && (s->pd[3] & 0x40); }
static void update_irq(P2DNet *s)
{
    qemu_set_irq(s->card_irq, socket_ready(s) && (s->pd[3] & 15) && s->nic_level);
    qemu_set_irq(s->management_irq, (s->pd[4] & s->pd[5] & 8) != 0);
}
static void nic_irq(void *opaque, int n, int level)
{
    P2DNet *s = opaque;
    s->nic_level = level;
    if (level) { s->fcsr |= 2; }
    update_irq(s);
}
static void chip_reset(P2DNet *s)
{
    NE2000State *n = &s->net;
    /* Do not clear the MemoryRegion, NIC configuration, IRQ or NIC owner. */
    n->cmd = 0x21; n->start = n->stop = 0; n->boundary = n->tsr = n->tpsr = 0;
    n->tcnt = n->rcnt = 0; n->rsar = 0; n->rsr = n->rxcr = 0;
    n->dcfg = n->imr = n->curpag = 0;
    memset(n->phys, 0, sizeof(n->phys)); memset(n->mult, 0, sizeof(n->mult));
    memset(n->mem, 0, sizeof(n->mem));
    ne2000_reset(n);
    s->nic_level = false; s->fcsr = 0;
    if (n->nic) { qemu_purge_queued_packets(qemu_get_queue(n->nic)); }
    update_irq(s);
}
static ssize_t receive(NetClientState *nc, const uint8_t *buf, size_t size)
{
    NE2000State *n = qemu_get_nic_opaque(nc);
    P2DNet *s = container_of(n, P2DNet, net);
    ssize_t result;
    if (!socket_ready(s) || (n->cmd & 1) || size < 14) { return size; }
    result = ne2000_receive(nc, buf, size);
    if (n->isr & 1) { s->fcsr |= 2; }
    return result;
}
static NetClientInfo net_info = {
    .type = NET_CLIENT_DRIVER_NIC, .size = sizeof(NICState), .receive = receive,
};

static uint8_t pd_read(P2DNet *s)
{
    uint8_t value;
    switch (s->index) {
    case 0: return 0x83;
    case 1: return 0x0c | (powered(s) ? 0x60 : 0);
    case 4:
        value = s->pd[4]; s->pd[4] = 0; update_irq(s); return value;
    case 0x16: return 1;
    case 0x17: case 0x1e: return 0;
    case 0x1f: value = s->chip; s->chip = 0; return value;
    default: return s->index < sizeof(s->pd) ? s->pd[s->index] : 0;
    }
}
static void pd_write(P2DNet *s, uint8_t value)
{
    bool was_powered = powered(s);
    bool was_reset_released = s->pd[3] & 0x40;
    if (s->index == 0x1f) { s->chip = 0xc0; return; }
    if (s->index < 2 || s->index == 4 || s->index >= sizeof(s->pd)) { return; }
    s->pd[s->index] = value;
    if (was_powered != powered(s) || was_reset_released != !!(s->pd[3] & 0x40)) {
        chip_reset(s);
    }
    update_irq(s);
}
static bool io_offset(P2DNet *s, hwaddr addr, unsigned size, unsigned *offset)
{
    unsigned w;
    if (!powered(s) || !(s->pd[3] & 0x40) || !(s->cor & 0x3f) || (s->cor & 0x80)) { return false; }
    for (w = 0; w < 2; w++) {
        unsigned r = 8 + 4 * w;
        unsigned start = s->pd[r] | (s->pd[r+1] << 8);
        unsigned end = s->pd[r+2] | (s->pd[r+3] << 8);
        if ((s->pd[6] & (0x40 << w)) && addr >= start && addr + size - 1 <= end && end - start >= 31) {
            *offset = addr & 31;
            return *offset + size <= 32;
        }
    }
    return false;
}
static uint64_t port_read(void *opaque, hwaddr addr, unsigned size)
{
    P2DNet *s = opaque;
    unsigned off;
    uint64_t value = 0;
    if (addr <= 0x3e1 && addr + size > 0x3e0) {
        for (unsigned i = 0; i < size; i++) {
            value |= (uint64_t)(addr+i == 0x3e0 ? s->index : addr+i == 0x3e1 ? pd_read(s) : 0xff) << (8*i);
        }
        return value;
    }
    if (!io_offset(s, addr, size, &off)) { return MAKE_64BIT_MASK(0, size*8); }
    if (off == 0x1f && size == 1) { chip_reset(s); return 0; }
    if (off == 7 && size == 1 && (s->net.cmd & 1)) { s->net.isr |= 0x80; }
    return ne2000_pio_read(&s->net, off, size);
}
static void port_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    P2DNet *s = opaque;
    unsigned off;
    if (addr <= 0x3e1 && addr + size > 0x3e0) {
        for (unsigned i = 0; i < size; i++) {
            if (addr+i == 0x3e0) { s->index = value >> (8*i); }
            if (addr+i == 0x3e1) { pd_write(s, value >> (8*i)); }
        }
        return;
    }
    if (!io_offset(s, addr, size, &off)) { return; }
    if (off == 0x1f && size == 1) { chip_reset(s); return; }
    ne2000_pio_write(&s->net, off, value, size);
    if (off == 0 && (value & 1)) { s->net.isr |= 0x80; }
    if (s->net.isr & 0x7f) { s->fcsr |= 2; }
}
static uint64_t mem_read(void *opaque, hwaddr addr, unsigned size)
{
    P2DNet *s = opaque;
    uint64_t value = 0;
    for (unsigned i = 0; i < size; i++) {
        hwaddr a = addr+i;
        uint8_t b = 0;
        if (a == 0x3f8) { b = s->cor; }
        else if (a == 0x3fa) { b = s->fcsr; }
        else if (a >= 0x4000 && a < 0x8000 && powered(s)) { b = s->net.mem[a]; }
        else if (a/2 < sizeof(cis)) { b = cis[a/2]; }
        value |= (uint64_t)b << (8*i);
    }
    return value;
}
static void mem_write(void *opaque, hwaddr addr, uint64_t value, unsigned size)
{
    P2DNet *s = opaque;
    for (unsigned i = 0; i < size; i++) {
        hwaddr a = addr+i;
        uint8_t b = value >> (8*i);
        if (a == 0x3f8) { s->cor = b; if (b & 0x80) { chip_reset(s); } }
        else if (a == 0x3fa) { s->fcsr = (b & ~3) | ((b & 1) ? 0 : (s->fcsr & 2)); }
        else if (a >= 0x4000 && a < 0x8000 && powered(s)) { s->net.mem[a] = b; }
    }
}
static const MemoryRegionOps port_ops = {
    .read = port_read, .write = port_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1, .valid.max_access_size = 4,
};
static const MemoryRegionOps mem_ops = {
    .read = mem_read, .write = mem_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1, .valid.max_access_size = 4,
};
static void reset(DeviceState *dev)
{
    P2DNet *s = P2D_NE2000(dev);
    memset(s->pd, 0, sizeof(s->pd)); s->pd[4] = 8;
    s->index = 0; s->chip = 0xc0; s->cor = 0;
    chip_reset(s);
}
static void realize(DeviceState *dev, Error **errp)
{
    P2DNet *s = P2D_NE2000(dev);
    s->net.irq = qemu_allocate_irq(nic_irq, s, 0);
    qemu_macaddr_default_if_unset(&s->net.c.macaddr);
    s->net.nic = qemu_new_nic(&net_info, &s->net.c, "ne2k_pcmcia", dev->id,
                             &dev->mem_reentrancy_guard, &s->net);
    qemu_format_nic_info_str(qemu_get_queue(s->net.nic), s->net.c.macaddr.a);
}
static void unrealize(DeviceState *dev)
{
    P2DNet *s = P2D_NE2000(dev);
    qemu_del_nic(s->net.nic); qemu_free_irq(s->net.irq);
}
static void init(Object *obj)
{
    P2DNet *s = P2D_NE2000(obj);
    memory_region_init_io(&s->memory, obj, &mem_ops, s, "p2d.card-memory", 0x10000);
    memory_region_init_io(&s->ports, obj, &port_ops, s, "p2d.card-ports", 0x10000);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->memory);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->ports);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->card_irq);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->management_irq);
}
static const Property properties[] = { DEFINE_NIC_PROPERTIES(P2DNet, net.c) };
static void class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    dc->realize = realize; dc->unrealize = unrealize; dc->user_creatable = false;
    device_class_set_legacy_reset(dc, reset); device_class_set_props(dc, properties);
    set_bit(DEVICE_CATEGORY_NETWORK, dc->categories);
}
static const TypeInfo type = {
    .name = TYPE_P2D_NE2000, .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(P2DNet), .instance_init = init, .class_init = class_init,
};
static void register_types(void) { type_register_static(&type); }
type_init(register_types)
