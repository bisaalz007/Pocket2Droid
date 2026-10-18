"""Deterministic register/event tests via upstream QTest protocol."""
import os
import signal
from pathlib import Path
import socket
import subprocess
import time
import unittest
import uuid
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run_probe import QMP
BINARY = os.environ.get('P2D_QEMU', '/opt/pocket2droid-tcg-build/host/qemu-system-arm')


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.path = Path('/tmp') / ('p2d-qtest-' + uuid.uuid4().hex + '.sock')
        self.qmp_path = Path('/tmp') / ('p2d-qmp-' + uuid.uuid4().hex + '.sock')
        fixture = ROOT / 'results/test-inputs/idle.bin'
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(bytes.fromhex('feffffea'))  # ARM b .; no guest MMIO.
        late = '_late_' in self._testMethodName
        self.process = subprocess.Popen([BINARY, '-M', 'p2d-devemu', '-accel', 'tcg' if late else 'qtest',
                                         *(['-S'] if late else []), '-bios', str(fixture),
                                         '-display', 'none', '-serial', 'none', '-monitor', 'none',
                                         '-qtest', f'unix:{self.path},server=on,wait=off',
                                         '-qmp', f'unix:{self.qmp_path},server=on,wait=off',
                                         '-qtest-log', '/dev/null'], stderr=subprocess.PIPE)
        self.addCleanup(self.cleanup)
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(3)
        for _ in range(100):
            try:
                self.sock.connect(str(self.path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if self.process.poll() is not None:
                    self.fail(self.process.stderr.read().decode())
                time.sleep(0.03)
        else:
            self.fail('QTest socket not ready')
        self.stream = self.sock.makefile('rwb')
        self.irq_levels = {}
        self.qmp = QMP(self.qmp_path, self.process)

    def cleanup(self):
        if hasattr(self, 'stream'):
            self.stream.close()
        if hasattr(self, 'qmp'):
            self.qmp.close()
        if hasattr(self, 'sock'):
            self.sock.close()
        self.process.terminate()
        self.process.wait(timeout=5)
        self.process.stderr.close()
        self.path.unlink(missing_ok=True)
        self.qmp_path.unlink(missing_ok=True)

    def request(self, text):
        self.stream.write((text + '\n').encode())
        self.stream.flush()
        while True:
            response = self.stream.readline().decode().strip()
            if not response.startswith('IRQ '):
                break
            _, level, number = response.split()
            self.irq_levels[int(number)] = level == 'raise'
        self.assertTrue(response.startswith('OK'), response)
        return response.split()[1:]

    def read(self, addr):
        return int(self.request(f'readl 0x{addr:x}')[0], 0)

    def write(self, addr, value):
        self.request(f'writel 0x{addr:x} 0x{value:x}')

    def test_uart_transmit_ready(self):
        self.assertEqual(self.read(0x50004010), 6)
        self.assertEqual(self.read(0x50004018), 0)

    def test_gpio_identity_and_pending_w1c(self):
        self.assertEqual(self.read(0x560000b0), 0x32410000)
        self.write(0x560000a8, 0x800)
        self.assertEqual(self.read(0x560000a8), 0)

    def test_timer4_reload_pending_mask_and_ack(self):
        self.write(0x5100003c, 1000)
        self.write(0x51000008, (1 << 21) | (1 << 22))
        self.assertEqual(self.read(0x51000040), 1000)
        self.write(0x51000008, (1 << 20) | (1 << 22))
        self.request('clock_step 1000000')
        self.assertEqual(self.read(0x4a000000) & (1 << 14), 1 << 14)
        self.assertEqual(self.read(0x4a000010), 0)
        self.write(0x4a000008, 0xffffffff ^ (1 << 14))
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.write(0x51000008, 0)
        self.write(0x4a000000, 1 << 14)
        self.write(0x4a000010, 1 << 14)
        self.assertEqual(self.read(0x4a000000), 0)
        self.assertEqual(self.read(0x4a000010), 0)

    def test_lcd_renders_guest_rgb565_pixels(self):
        self.request('writew 0x33f00000 0xf800')
        self.request('writew 0x33f00002 0x07e0')
        self.request('writew 0x33f00004 0x001f')
        self.request('writew 0x33f00006 0xffff')
        self.write(0x4d000004, 0)
        self.write(0x4d000008, 3 << 8)
        self.write(0x4d000010, 1 << 11)
        self.write(0x4d000014, 0x33f00000 >> 1)
        self.write(0x4d00001c, 4)
        self.write(0x4d000000, 0x79)
        path = ROOT / 'results/test-inputs/lcd.ppm'
        path.unlink(missing_ok=True)
        self.qmp.request('screendump', {'filename': str(path), 'format': 'ppm'})
        # Width4 avoids upstream PPM's4-byte line-padding ambiguity at width3.
        self.assertEqual(path.read_bytes(), b'P6\n4 1\n255\n\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff')

    def test_lcd_wvga_native_height(self):
        self.request('writew 0x33f00000 0xf800')
        last = 0x33f00000 + (480 * 800 - 1) * 2
        self.request(f'writew 0x{last:x} 0x001f')
        self.write(0x4d000004, 799 << 14)
        self.write(0x4d000008, 479 << 8)
        self.write(0x4d000010, 1 << 11)
        self.write(0x4d000014, 0x33f00000 >> 1)
        self.write(0x4d00001c, 480)
        self.write(0x4d000000, 0x79)
        path = ROOT / 'results/test-inputs/lcd-wvga.ppm'
        self.qmp.request('screendump', {'filename': str(path), 'format': 'ppm'})
        data = path.read_bytes()
        self.assertTrue(data.startswith(b'P6\n480 800\n255\n'))
        self.assertEqual(len(data), len(b'P6\n480 800\n255\n') + 480 * 800 * 3)
        self.assertEqual(data[-3:], b'\x00\x00\xff')

    def test_lcd_large_frame_exceeds_old_transport_dimensions(self):
        self.request('writew 0x33000000 0xf800')
        last=0x33000000+(1280*960-1)*2
        self.request(f'writew 0x{last:x} 0x001f')
        self.write(0x4d000004,959<<14)
        self.write(0x4d000008,1279<<8)
        self.write(0x4d000010,1<<11)
        self.write(0x4d000014,0x33000000>>1)
        self.write(0x4d00001c,1280)
        self.write(0x4d000000,0x79)
        path=ROOT/'results/test-inputs/lcd-large.ppm'
        self.qmp.request('screendump',{'filename':str(path),'format':'ppm'})
        data=path.read_bytes();header=b'P6\n1280 960\n255\n'
        self.assertEqual(len(data),len(header)+1280*960*3)
        self.assertTrue(data.startswith(header))
        self.assertEqual(data[len(header):len(header)+3],b'\xff\x00\x00')
        self.assertEqual(data[-3:],b'\x00\x00\xff')

    def test_timer_fiq_route_mask_and_ack(self):
        self.request('irq_intercept_out /machine/p2d-soc sysbus-irq')
        self.write(0x4a000004, 1 << 14)
        self.write(0x4a000008, 0xffffffff ^ (1 << 14))
        self.write(0x5100003c, 100)
        self.write(0x51000008, 1 << 21)
        self.write(0x51000008, 1 << 20)
        self.request('clock_step 1000000')
        self.assertTrue(self.irq_levels.get(1, False))
        self.assertFalse(self.irq_levels.get(0, False))
        self.assertEqual(self.read(0x4a000010), 0)
        self.write(0x4a000008, 0xffffffff)
        self.assertFalse(self.irq_levels.get(1, False))
        self.write(0x4a000000, 1 << 14)
        self.write(0x4a000008, 0xffffffff ^ (1 << 14))
        self.assertFalse(self.irq_levels.get(1, False))

    def test_touch_adc_conversion_and_subinterrupt_ack(self):
        self.write(0x4a00001c, 0x7ff ^ (1 << 9) ^ (1 << 10))
        self.write(0x4a000008, 0x7fffffff)
        self.write(0x58000004, 0xd3)
        self.qmp.request('input-send-event', {'events': [
            {'type': 'abs', 'data': {'axis': 'x', 'value': 0x7fff}},
            {'type': 'abs', 'data': {'axis': 'y', 'value': 0}},
            {'type': 'btn', 'data': {'button': 'left', 'down': True}}]})
        self.assertEqual(self.read(0x5800000c) & 0x83ff, 920)
        self.assertEqual(self.read(0x58000010) & 0x83ff, 965)
        self.assertEqual(self.read(0x4a000018) & (1 << 9), 1 << 9)
        self.assertEqual(self.read(0x4a000010), 1 << 31)
        self.write(0x4a000018, 1 << 9)
        self.write(0x4a000000, 1 << 31)
        self.write(0x4a000010, 1 << 31)
        self.assertEqual(self.read(0x4a000010), 0)
        self.write(0x58000000, 0x3fc1)
        self.assertTrue(self.read(0x58000000) & (1 << 15))
        self.assertTrue(self.read(0x4a000018) & (1 << 10))
        self.qmp.request('input-send-event', {'events': [
            {'type': 'btn', 'data': {'button': 'left', 'down': False}}]})
        self.assertTrue(self.read(0x58000010) & (1 << 15))

    def test_iis_dma_prefill_stop_and_serial_completion(self):
        self.write(0x300ac000, 0x11223344)
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000084, 0)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        # Halfword HW IIS TX, IRQ, no reload,64 transfer units.
        self.write(0x4b000090, 0xa0d00040)
        self.write(0x55000000, 0x20)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.request('clock_step 10000')
        self.assertEqual(self.read(0x4b000094) & 0xfffff, 32)
        self.assertEqual(self.read(0x4b000098), 0x300ac040)
        self.assertEqual((self.read(0x5500000c) >> 6) & 63, 32)
        self.assertTrue(self.read(0x55000000) & 0x80)
        self.request('clock_step 10000000')
        self.assertEqual(self.read(0x4b000094) & 0xfffff, 32)
        self.write(0x55000000, 0x21)
        # QTest advances through intermediate deadlines. This verifies ordinary
        # clocked events; late host servicing is covered separately under TCG.
        for _ in range(64):
            self.request('clock_step')
        self.assertEqual(self.read(0x4b000094) & 0xfffff, 0)
        self.assertEqual(self.read(0x4b000098), 0x300ac080)
        self.assertTrue(self.read(0x4a000000) & (1 << 19))
        self.write(0x4b0000a0, 4)
        self.assertEqual(self.read(0x4b0000a0), 0)

    def test_rearming_same_audio_deadline_preserves_timer_irq_tie_order(self):
        self.write(0x4a000008, 0xffffffff ^ (1 << 14) ^ (1 << 19))
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d00021)
        self.write(0x55000000, 0x21)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.request('clock_step 1')  # Prefill32 at1ns;33rd sample completes DMA.
        self.write(0x55000000, 0x21)  # Serial deadline now1068ns.
        self.write(0x5100003c, 64)  #ceil64*1e9/60MHz=1067ns.
        self.write(0x51000008, 1 << 21)
        self.write(0x51000008, 1 << 20)  # Timer4 also expires1068ns.
        # Full FIFO ignores this payload, but scheduling retains baseline
        # delete/reinsert semantics: already-queued Timer4 wins the equal tie.
        self.request('writew 0x55000010 0x1234')
        self.request('clock_step 1067')
        self.assertEqual(self.read(0x4a000000), (1 << 14) | (1 << 19))
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertEqual(self.read(0x4a000014), 14)

    def test_batched_dma_completion_keeps_later_registered_timer_tie_order(self):
        self.write(0x4a000008, 0xffffffff ^ (1 << 14) ^ (1 << 19))
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d00040)
        self.write(0x55000000, 0x21)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.request('clock_step 1')
        self.request('clock_step 809')  #now810ns, before first serial sample.
        self.write(0x5100003c, 2000)  #ceil2000*1e9/60MHz=33334ns.
        self.write(0x51000008, 1 << 21)
        self.write(0x51000008, 1 << 20)  #Timer4 expires34144ns.
        self.request('clock_step 33334')  #DMA also ends at32*1067=34144ns.
        self.assertEqual(self.read(0x4a000000), (1 << 14) | (1 << 19))
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertEqual(self.read(0x4a000014), 14)

    def test_dma_timer_autoreload_chain_preserves_irq_tie_order(self):
        self.write(0x4a000008, 0xffffffff ^ (1 << 14) ^ (1 << 19))
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d00040)
        self.write(0x55000000, 0x21)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.request('clock_step 1')
        self.request('clock_step 809')
        self.write(0x5100003c, 1936)  # First timer4 IRQ at33077ns.
        self.write(0x51000008, (1 << 21) | (1 << 22))
        self.write(0x51000008, (1 << 20) | (1 << 22))
        self.write(0x5100003c, 64)  # Reload reaches DMA completion34144ns.
        self.request('clock_step 32267')
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.write(0x4a000000, 1 << 14)
        self.write(0x4a000010, 1 << 14)
        self.request('clock_step 1067')
        self.assertEqual(self.read(0x4a000000), (1 << 14) | (1 << 19))
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertEqual(self.read(0x4a000014), 14)

    def test_iis_tracks_changed_peripheral_clock(self):
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0x2000)
        self.request('writew 0x55000010 0x1234')
        self.write(0x55000000, 1)
        start = int(self.request('clock_step 1')[0], 0)
        self.write(0x4c000014, 3)
        end = int(self.request('clock_step')[0], 0)
        self.assertEqual(end - start, 4267)
        self.assertEqual((self.read(0x5500000c) >> 6) & 63, 0)

    def test_pending_selection_survives_source_ack_and_new_source(self):
        self.request('irq_intercept_out /machine/p2d-soc sysbus-irq')
        self.write(0x4a000008, 0xffffffff ^ (1 << 14) ^ (1 << 19))
        self.write(0x5100003c, 100)
        self.write(0x51000008, 1 << 21)
        self.write(0x51000008, 1 << 20)
        self.request('clock_step 1000000')
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.write(0x4a000000, 1 << 14)
        self.assertEqual(self.read(0x4a000000), 0)
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertTrue(self.irq_levels.get(0, False))
        # A DMA completion is independently pending while timer14 remains selected.
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d00001)
        self.write(0x55000000, 0x20)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.request('clock_step 10000')
        self.assertEqual(self.read(0x4a000000), 1 << 19)
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertEqual(self.read(0x4a000014), 14)
        self.write(0x4a000010, 1 << 14)
        self.assertEqual(self.read(0x4a000010), 1 << 19)
        self.assertEqual(self.read(0x4a000014), 19)
        self.write(0x4a000000, 1 << 19)
        self.assertEqual(self.read(0x4a000010), 1 << 19)
        self.write(0x4a000010, 1 << 19)
        self.assertEqual(self.read(0x4a000010), 0)
        self.assertFalse(self.irq_levels.get(0, False))

    def test_iis_late_host_service_keeps_guest_clock(self):
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d01900)  #6400 halfwords, nominal6.83ms.
        self.write(0x55000000, 0x21)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.qmp.request('cont')
        # Suspend only our disposable child. Virtual time continues to advance;
        # unlike QTest's clock_step, callbacks cannot run at intermediate times.
        os.kill(self.process.pid, signal.SIGSTOP)
        try:
            time.sleep(0.05)
        finally:
            os.kill(self.process.pid, signal.SIGCONT)
        time.sleep(0.005)
        self.qmp.request('stop')
        self.assertEqual(self.read(0x4b000094) & 0xfffff, 0)
        self.assertEqual(self.read(0x4b000098), 0x300af200)
        self.assertEqual((self.read(0x5500000c) >> 6) & 63, 0)
        self.assertTrue(self.read(0x4a000000) & (1 << 19))

    def run_late_host_service(self):
        self.qmp.request('cont')
        os.kill(self.process.pid, signal.SIGSTOP)
        try:
            time.sleep(0.05)
        finally:
            os.kill(self.process.pid, signal.SIGCONT)
        time.sleep(0.005)
        self.qmp.request('stop')

    def test_late_timer_and_dma_keep_interrupt_deadline_order(self):
        self.write(0x4a000008, 0xffffffff ^ (1 << 14) ^ (1 << 19))
        self.write(0x5100003c, 6000)  #100us at reset60MHz.
        self.write(0x51000008, 1 << 21)
        self.write(0x51000008, 1 << 20)
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d000c8)  #200 halfwords; complete after179us.
        self.write(0x55000000, 0x21)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.run_late_host_service()
        self.assertEqual(self.read(0x4a000000), (1 << 14) | (1 << 19))
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertEqual(self.read(0x4a000014), 14)
        self.write(0x4a000000, 1 << 14)
        self.write(0x4a000010, 1 << 14)
        self.assertEqual(self.read(0x4a000010), 1 << 19)

    def test_timer4_late_host_service_preserves_reload_phase(self):
        self.write(0x5100003c, 65535)
        self.write(0x51000008, (1 << 21) | (1 << 22))
        self.write(0x51000008, (1 << 20) | (1 << 22))
        def property(name):
            return self.qmp.request('qom-get', {'path': '/machine/p2d-soc', 'property': name})
        original = property('timer4-deadline-ns')
        period = 1092250  #ceil65535*1e9/60MHz.
        self.run_late_host_service()
        now, deadline = property('virtual-clock-ns'), property('timer4-deadline-ns')
        self.assertGreater(now, 50_000_000)
        self.assertGreater(deadline, original + 40 * period)
        self.assertEqual((deadline - original) % period, 0)
        # A callback can be at most one period behind the final QMP stop.
        self.assertLessEqual(abs(deadline - now), period)
        elapsed = now - (deadline - period)
        expected_count = max(0, 65535 - elapsed * 60_000_000 // 1_000_000_000)
        self.assertEqual(self.read(0x51000040), expected_count)
        self.assertTrue(self.read(0x4a000000) & (1 << 14))

    def test_late_prefill_does_not_consume_a_later_serial_deadline(self):
        self.write(0x4a000008, 0xffffffff ^ (1 << 14) ^ (1 << 19))
        self.write(0x5100003c, 30)  #500ns, between prefill1ns and sample1067ns.
        self.write(0x51000008, 1 << 21)
        self.write(0x51000008, 1 << 20)
        self.write(0x4b000080, 0x300ac000)
        self.write(0x4b000088, 0x55000010)
        self.write(0x4b00008c, 3)
        self.write(0x4b000090, 0xa0d00021)  #33halfwords, IRQ on first refill.
        self.write(0x55000000, 0x21)
        self.write(0x55000004, 0x89)
        self.write(0x5500000c, 0xa000)
        self.write(0x4b0000a0, 2)
        self.run_late_host_service()
        self.assertEqual(self.read(0x4a000000), (1 << 14) | (1 << 19))
        self.assertEqual(self.read(0x4a000010), 1 << 14)
        self.assertEqual(self.read(0x4a000014), 14)


if __name__ == '__main__':
    unittest.main()
