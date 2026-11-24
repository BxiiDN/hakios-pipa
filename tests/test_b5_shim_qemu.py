"""The B5 shim (package/b5-shim) as code: shim.c built for the host decides exactly as tools/b5_shim_model.py on many
device trees (the stock Android tree among them); and the real AArch64 binary, composed by tools/b5_compose.py around a
stand-in Image and menu, runs in QEMU's virt machine, whose /chosen is filled from -append and -initrd the way ABL fills
it: normal and charger boots reach the Image's own code with the tree untouched, a recovery boot reaches the menu with
linux,initrd-start/-end naming the payload, and a recovery boot without initrd falls back to Android."""
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import b5_compose  # noqa: E402
import b5_shim_model as model  # noqa: E402
from test_mode_b import dtb, NORMAL, RECOVERY, INITRD8, INITRD4, STOCK  # noqa: E402

CC = shutil.which('cc') or shutil.which('gcc')
CLANG, LLD, OBJCOPY = shutil.which('clang'), shutil.which('ld.lld'), shutil.which('llvm-objcopy')
QEMU = shutil.which('qemu-system-aarch64')
DTC = shutil.which('dtc')
SHIM = ROOT / 'package/b5-shim'


@unittest.skipUnless(CC and DTC, 'no C compiler or dtc')
class Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.exe = cls.tmp / 'shim-host'
        subprocess.run([CC, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(SHIM),
                        str(ROOT / 'tests/host/b5_shim_host.c'), str(SHIM / 'shim.c'), '-o', str(cls.exe)], check=True)

    def both(self, tree, addr=0xA35F2000, size=96 << 20):
        i, o = self.tmp / 'in.dtb', self.tmp / 'out.dtb'
        i.write_bytes(tree)
        r = subprocess.run([str(self.exe), str(i), str(o), str(addr), str(size)], capture_output=True, text=True, check=True)
        c_path = 'menu' if r.stdout.strip() == '1' else 'android'
        path, _, patched = model.decide(tree, addr, size)
        self.assertEqual(c_path, path)
        self.assertEqual(o.read_bytes(), patched if patched is not None else tree)

    def test_cases(self):
        cases = [NORMAL + INITRD8, RECOVERY + INITRD8, RECOVERY + INITRD4, RECOVERY,
                 'bootargs = "androidboot.mode=charger x";' + INITRD8, 'foo = <1>;',
                 'bootargs = "xandroidboot.force_normal_boot=1";' + INITRD8,          # not the word: menu
                 'bootargs = "androidboot.force_normal_boot=10";' + INITRD8]          # not the word: menu
        for c in cases:
            self.both(dtb(c))
        self.both(dtb(None))
        self.both(b'\0' * 64)
        self.both(dtb(RECOVERY + INITRD8)[:50])
        self.both(dtb(RECOVERY + INITRD8), size=(96 << 20) + 1)
        self.both(dtb(RECOVERY + INITRD4), addr=0x1_0000_0000)

    @unittest.skipUnless((STOCK / 'vendor_boot.img').is_file(), 'stock vendor_boot not present')
    def test_stock_android_tree(self):
        v = (STOCK / 'vendor_boot.img').read_bytes()
        page, ramdisk = struct.unpack_from('<I', v, 12)[0], struct.unpack_from('<I', v, 24)[0]
        header = struct.unpack_from('<I', v, 2096)[0]
        off = -(-header // page) * page + -(-ramdisk // page) * page
        first = v[off:off + struct.unpack_from('>I', v, off + 4)[0]]
        p = self.tmp / 'stock.dtb'
        p.write_bytes(first)
        for args in ('console=ttyMSM0 androidboot.slot_suffix=_b', 'androidboot.force_normal_boot=1 a=b'):
            subprocess.run(['fdtput', '-c', str(p), '/chosen'], capture_output=True)
            subprocess.run(['fdtput', '-ts', str(p), '/chosen', 'bootargs', args], check=True)
            subprocess.run(['fdtput', '-tx', str(p), '/chosen', 'linux,initrd-start', '0', 'aecc4000'], check=True)
            subprocess.run(['fdtput', '-tx', str(p), '/chosen', 'linux,initrd-end', '0', 'b0000000'], check=True)
            self.both(p.read_bytes())


def flat(src, define, out, work):
    o = work / f'{define}.o'
    subprocess.run([CLANG, '--target=aarch64-none-elf', '-c', f'-D{define}', str(src), '-o', str(o)], check=True)
    ld = work / f'{define}.ld'
    ld.write_text('SECTIONS { . = 0; .t : { *(.text*) } /DISCARD/ : { *(.comment) *(.note*) } }\n')
    elf = work / f'{define}.elf'
    subprocess.run([LLD, '-T', str(ld), str(o), '-o', str(elf)], check=True)
    subprocess.run([OBJCOPY, '-O', 'binary', '--only-section=.t', str(elf), str(out)], check=True)
    return out.read_bytes()


@unittest.skipUnless(QEMU and CLANG and LLD and OBJCOPY, 'no qemu-system-aarch64 or LLVM')
class Qemu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, str(SHIM / 'build-shim.py'), '--out', str(cls.tmp / 'shim.bin')], check=True,
                       capture_output=True)
        image = flat(ROOT / 'tests/host/b5_stubs.S', 'IMAGE', cls.tmp / 'image.bin', cls.tmp)
        menu = flat(ROOT / 'tests/host/b5_stubs.S', 'MENU', cls.tmp / 'menu.bin', cls.tmp)
        h = bytearray(4096)
        h[:8] = b'ANDROID!'
        ramdisk = b'RAMDISK!' * 64
        struct.pack_into('<IIII', h, 8, len(image), len(ramdisk), 0, 1580)
        struct.pack_into('<I', h, 40, 3)
        pad = lambda b: b + b'\0' * (-len(b) % 4096)
        boot = bytes(h) + pad(image) + pad(ramdisk)
        cls.payload = b'\0' * (1 << 20)
        out, cls.info = b5_compose.compose(boot, menu, cls.payload, (cls.tmp / 'shim.bin').read_bytes())
        ks = struct.unpack_from('<I', out, 8)[0]
        (cls.tmp / 'kernel.bin').write_bytes(out[4096:4096 + ks])
        (cls.tmp / 'initrd.bin').write_bytes(b'stock-ramdisk' * 100)

    def boot(self, append, initrd=True):
        for f in ('android.out', 'menu.out'):
            (self.tmp / f).unlink(missing_ok=True)
        cmd = [QEMU, '-M', 'virt', '-cpu', 'cortex-a57', '-m', '1024', '-nographic', '-no-reboot', '-monitor', 'none',
               '-serial', 'none', '-semihosting-config', 'enable=on,target=native', '-kernel', 'kernel.bin',
               '-append', append]
        if initrd:
            cmd += ['-initrd', 'initrd.bin']
        r = subprocess.run(cmd, cwd=self.tmp, capture_output=True, timeout=60)
        name = {0x10: 'android.out', 0x20: 'menu.out'}.get(r.returncode)
        self.assertIsNotNone(name, f'QEMU exit {r.returncode}: {r.stderr[-300:]}')
        data = (self.tmp / name).read_bytes()
        where = struct.unpack_from('<Q', data)[0]
        return name, where, data[8:]

    def initrd(self, tree):
        props = model.chosen_props(tree)
        val = lambda n: int.from_bytes(tree[props[n][0]:props[n][0] + props[n][1]], 'big')
        return val('linux,initrd-start'), val('linux,initrd-end')

    def test_normal_boot_runs_android_untouched(self):
        name, _, tree = self.boot('console=ttyAMA0 androidboot.force_normal_boot=1')
        self.assertEqual(name, 'android.out')
        start, end = self.initrd(tree)
        self.assertEqual(end - start, len(b'stock-ramdisk' * 100))       # QEMU's own initrd, not the payload

    def test_charger_runs_android(self):
        self.assertEqual(self.boot('androidboot.mode=charger')[0], 'android.out')

    def test_recovery_opens_the_menu_with_the_payload(self):
        name, where, tree = self.boot('console=ttyAMA0 androidboot.slot_suffix=_b')
        self.assertEqual(name, 'menu.out')
        base = where - self.info['bootshim_offset']                     # the Image's load address
        start, end = self.initrd(tree)
        self.assertEqual((start, end), (base + self.info['payload_offset'], base + self.info['payload_offset'] + len(self.payload)))

    def test_recovery_without_initrd_falls_back_to_android(self):
        self.assertEqual(self.boot('androidboot.slot_suffix=_b', initrd=False)[0], 'android.out')


if __name__ == '__main__':
    unittest.main()
