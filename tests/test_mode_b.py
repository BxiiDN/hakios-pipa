"""MODE B route B5, offline: the shim's decision model (tools/b5_shim_model.py), ABL's placement rules
(tools/abl_layout.py), the OTA extractor (tools/ota_extract.py) and the power-on simulation (tools/mode_b_sim.py).
Fixtures are built here; the stock images are used only when they are present on this machine (never in Git)."""
import hashlib
import itertools
import lzma
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import abl_layout  # noqa: E402
import b5_shim_model as shim  # noqa: E402
import mode_b_sim  # noqa: E402
import ota_extract  # noqa: E402

DTC = shutil.which('dtc')
FDTPUT = shutil.which('fdtput')
FDTGET = shutil.which('fdtget')
STOCK = Path.home() / 'pipa-inputs/stock/payload-out'
PAYLOAD = 0xA35F2000, 112 << 20


def dtb(chosen):
    src = '/dts-v1/;\n/ { #address-cells = <2>; #size-cells = <2>;\n memory@80000000 { device_type = "memory"; ' \
          'reg = <0 0x80000000 0 0x3bb00000>; };\n' + (f' chosen {{ {chosen} }};\n' if chosen is not None else '') + '};\n'
    return subprocess.run([DTC, '-I', 'dts', '-O', 'dtb', '-o', '-'], input=src.encode(), capture_output=True,
                          check=True).stdout


NORMAL = 'bootargs = "console=ttyMSM0 androidboot.force_normal_boot=1 androidboot.slot_suffix=_b";'
RECOVERY = 'bootargs = "console=ttyMSM0 androidboot.slot_suffix=_b";'
INITRD8 = 'linux,initrd-start = <0x0 0xaecc4000>; linux,initrd-end = <0x0 0xb0000000>;'
INITRD4 = 'linux,initrd-start = <0xaecc4000>; linux,initrd-end = <0xb0000000>;'


@unittest.skipUnless(DTC, 'dtc not available')
class ShimDecision(unittest.TestCase):
    def decide(self, tree, addr=PAYLOAD[0], size=PAYLOAD[1]):
        return shim.decide(tree, addr, size)

    def test_normal_boot_goes_to_android_untouched(self):
        self.assertEqual(self.decide(dtb(NORMAL + INITRD8))[:2], ('android', 'normal boot'))

    def test_charger_goes_to_android(self):
        t = dtb('bootargs = "androidboot.mode=charger androidboot.slot_suffix=_b";' + INITRD8)
        self.assertEqual(self.decide(t)[0], 'android')

    def test_recovery_boot_opens_the_menu_with_the_payload_as_initrd(self):
        tree = dtb(RECOVERY + INITRD8)
        path, _, patched = self.decide(tree)
        self.assertEqual(path, 'menu')
        self.assertEqual(len(patched), len(tree))
        props = shim.chosen_props(patched)
        o, _ = props['linux,initrd-start']
        self.assertEqual(struct.unpack_from('>Q', patched, o)[0], PAYLOAD[0])
        o, _ = props['linux,initrd-end']
        self.assertEqual(struct.unpack_from('>Q', patched, o)[0], PAYLOAD[0] + PAYLOAD[1])
        self.assertEqual(sum(a != b for a, b in zip(tree, patched)) <= 16, True)   # only the two values

    def test_32_bit_initrd_cells_are_rewritten_in_place(self):
        path, _, patched = self.decide(dtb(RECOVERY + INITRD4))
        self.assertEqual(path, 'menu')
        o, n = shim.chosen_props(patched)['linux,initrd-start']
        self.assertEqual((n, struct.unpack_from('>I', patched, o)[0]), (4, PAYLOAD[0]))
        self.assertEqual(self.decide(dtb(RECOVERY + INITRD4), addr=0x1_0000_0000)[0], 'android')

    def test_every_doubt_is_android(self):
        for tree, why in ((b'\0' * 64, 'garbage'), (dtb(None), 'no chosen'), (dtb('foo = <1>;'), 'no bootargs'),
                          (dtb(RECOVERY), 'no initrd'), (dtb(RECOVERY + INITRD8)[:60], 'truncated')):
            self.assertEqual(self.decide(tree)[0], 'android', why)
        self.assertEqual(self.decide(dtb(RECOVERY + INITRD8), size=PAYLOAD[1] + 1)[0], 'android')

    @unittest.skipUnless(FDTPUT and FDTGET and (STOCK / 'vendor_boot.img').is_file(), 'stock vendor_boot not present')
    def test_the_stock_android_device_tree_as_abl_would_pass_it(self):
        v = (STOCK / 'vendor_boot.img').read_bytes()
        page, ramdisk = struct.unpack_from('<I', v, 12)[0], struct.unpack_from('<I', v, 24)[0]
        header, dtb_size = struct.unpack_from('<II', v, 2096)
        off = abl_layout.align(header, page) + abl_layout.align(ramdisk, page)
        first = v[off:off + struct.unpack_from('>I', v, off + 4)[0]]
        self.assertEqual(struct.unpack_from('>I', first)[0], shim.FDT_MAGIC)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'android.dtb'
            p.write_bytes(first)
            subprocess.run([FDTPUT, '-c', str(p), '/chosen'], check=False, capture_output=True)
            subprocess.run([FDTPUT, '-ts', str(p), '/chosen', 'bootargs', 'console=ttyMSM0 androidboot.slot_suffix=_b'], check=True)
            subprocess.run([FDTPUT, '-tx', str(p), '/chosen', 'linux,initrd-start', '0', 'aecc4000'], check=True)
            subprocess.run([FDTPUT, '-tx', str(p), '/chosen', 'linux,initrd-end', '0', 'b0000000'], check=True)
            path, _, patched = self.decide(p.read_bytes())
            self.assertEqual(path, 'menu')
            p.write_bytes(patched)
            got = subprocess.run([FDTGET, '-tx', str(p), '/chosen', 'linux,initrd-start'], capture_output=True, text=True, check=True)
            self.assertEqual(got.stdout.split(), ['0', f'{PAYLOAD[0]:x}'])
            subprocess.run([FDTPUT, '-ts', str(p), '/chosen', 'bootargs', 'androidboot.force_normal_boot=1'], check=True)
            self.assertEqual(self.decide(p.read_bytes())[0], 'android')


def boot_v3(kernel, ramdisk):
    page = 4096
    h = bytearray(page)
    h[:8] = b'ANDROID!'
    struct.pack_into('<IIII', h, 8, len(kernel), len(ramdisk), 0, 1580)
    struct.pack_into('<I', h, 40, 3)
    pad = lambda b: b + b'\0' * (abl_layout.align(len(b), page) - len(b))
    return bytes(h) + pad(kernel) + pad(ramdisk)


def image(file_bytes, image_size):
    k = bytearray(file_bytes)
    struct.pack_into('<QQ', k, 8, 0x80000, image_size)
    k[56:60] = b'ARMd'
    return bytes(k)


def vendor_v3(vendor_ramdisk=0x945):
    v = bytearray(4096)
    v[:8] = b'VNDRBOOT'
    struct.pack_into('<II', v, 8, 3, 4096)
    struct.pack_into('<I', v, 24, vendor_ramdisk)
    return bytes(v)


class AblLayout(unittest.TestCase):
    def test_android_image_within_the_region_passes(self):
        b = abl_layout.parse_boot(boot_v3(image(b'\0' * 0x10000, 0x3d44000), b'R' * 0x1339de3))
        r = abl_layout.layout(b, abl_layout.parse_vendor_boot(vendor_v3()))
        self.assertTrue(all(level == 'PASS' for level, _ in r['checks']), r['checks'])
        self.assertEqual((r['kernel_addr'], r['dtb_addr']), (0xA0080000, 0xAEAC3000))   # the stock image's values

    def test_runtime_size_past_the_device_tree_fails(self):
        b = abl_layout.parse_boot(boot_v3(image(b'\0' * 0x10000, 0xEA44000), b'R' * 0x1339de3))
        r = abl_layout.layout(b, abl_layout.parse_vendor_boot(vendor_v3()))
        self.assertTrue(any(level == 'FAIL' and 'image_size' in t for level, t in r['checks']))

    def test_image_larger_than_the_partition_fails(self):
        b = abl_layout.parse_boot(boot_v3(image(b'\0' * 0x10000, 0x20000), b'R' * 0x1000))
        r = abl_layout.layout(b, None, partition=0x1000)
        self.assertTrue(any(level == 'FAIL' and 'boot partition' in t for level, t in r['checks']))

    def test_b5_budget_of_this_unit(self):
        b = abl_layout.parse_boot(boot_v3(image(b'\0' * 52826128, 0x3d44000), b'R' * 20159971))
        v = abl_layout.parse_vendor_boot(vendor_v3())
        ok = abl_layout.b5_budget(b, v, 3145728, 112 << 20)
        self.assertTrue(ok['fits_partition'] and ok['fits_abl'])
        self.assertEqual(ok['max_payload'], 0x7700000)                        # 119 MiB
        self.assertFalse(abl_layout.b5_budget(b, v, 3145728, 128 << 20)['fits_partition'])   # the session-10 128 MiB

    @unittest.skipUnless((STOCK / 'boot.img').is_file(), 'stock boot.img not present')
    def test_stock_boot_image(self):
        b = abl_layout.parse_boot((STOCK / 'boot.img').read_bytes())
        r = abl_layout.layout(b, abl_layout.parse_vendor_boot((STOCK / 'vendor_boot.img').read_bytes()))
        self.assertEqual((b['version'], r['kind'], r['image_size']), (3, 'Image', 0x3d44000))
        self.assertTrue(all(level == 'PASS' for level, _ in r['checks']))


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field(num, value):
    if isinstance(value, int):
        return varint(num << 3) + varint(value)
    return varint(num << 3 | 2) + varint(len(value)) + value


def payload_bin(ops, size, block=4096, final_hash=None):
    data, encoded = b'', b''
    for kind, blob, start, n in ops:
        op = field(1, kind)
        if blob is not None:
            op += field(2, len(data)) + field(3, len(blob)) + field(8, hashlib.sha256(blob).digest())
            data += blob
        op += field(6, field(1, start) + field(2, n))
        encoded += field(8, op)
    info = field(1, size) + (field(2, final_hash) if final_hash else b'')
    manifest = field(3, block) + field(13, field(1, b'abl') + field(7, info) + encoded)
    return b'CrAU' + struct.pack('>QQI', 2, len(manifest), 0) + manifest + data


class OtaExtract(unittest.TestCase):
    def run_extract(self, blob):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'payload.bin'
            p.write_bytes(blob)
            f, base = ota_extract.open_payload(p)
            with f:
                m, data_base = ota_extract.manifest(f, base)
                part = ota_extract.partitions(m)['abl']
                out = Path(d) / 'abl.img'
                ota_extract.extract(f, data_base, part, out)
                return out.read_bytes()

    def test_replace_xz_and_zero(self):
        a, b = os.urandom(4096), os.urandom(4096)
        want = a + b'\0' * 4096 + b
        blob = payload_bin([(0, a, 0, 1), (6, None, 1, 1), (8, lzma.compress(b), 2, 1)], 3 * 4096,
                           final_hash=hashlib.sha256(want).digest())
        self.assertEqual(self.run_extract(blob), want)

    def test_wrong_partition_hash_and_delta_ops_are_refused(self):
        a = os.urandom(4096)
        with self.assertRaises(ValueError):
            self.run_extract(payload_bin([(0, a, 0, 1)], 4096, final_hash=b'\1' * 32))
        with self.assertRaises(ValueError):
            self.run_extract(payload_bin([(4, a, 0, 1)], 4096))   # SOURCE_COPY


class Simulation(unittest.TestCase):
    def test_scenarios_pass(self):
        self.assertEqual(mode_b_sim.main(), 0)

    def test_b5_never_loops_and_fastboot_is_always_reachable(self):
        for key, charger, choice, root, accepted in itertools.product(
                (None, 'vol+', 'vol-'), (False, True), ('timeout', 'android', 'ipados', 'recovery'), (False, True), (False, True)):
            trace, outcome = mode_b_sim.run('b5', key, charger, choice, root, accepted)
            self.assertNotEqual(outcome, 'LOOP', (key, charger, choice, root, accepted, trace))
            self.assertEqual(mode_b_sim.abl('b5', 'vol-', charger, accepted), 'FASTBOOT')

    def test_android_recovery_after_b5(self):
        # with B5 a recovery request opens the menu and ends in Android, never in a loop; restoring the original boot_b
        # (always possible from fastboot, which ABL keeps in its own partition) gives stock recovery back
        self.assertEqual(mode_b_sim.run('b5', 'vol+')[1], 'ANDROID')
        self.assertEqual(mode_b_sim.abl('b5', 'vol-', False), 'FASTBOOT')
        self.assertEqual(mode_b_sim.run('stock', 'vol+')[1], 'RECOVERY')

    def test_the_mode_a_image_in_flash_loops(self):
        self.assertEqual(mode_b_sim.run('mode_a')[1], 'LOOP')


if __name__ == '__main__':
    unittest.main()
