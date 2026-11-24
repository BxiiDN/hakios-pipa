"""tools/rom_match.py on synthetic images: the kernel is the installed one only with the same banner and the same embedded
config; the device tree and dtbo checks; and the real OS2.0.16 images (when present) never match the port ROM's kernel."""
import gzip
import shutil
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import rom_match  # noqa: E402

R, V = '5.10.241', '#18 SMP PREEMPT Thu Oct 29 19:56:25 CST 2026'
CONFIG = b'CONFIG_LOCALVERSION="-perf"\nCONFIG_IKCONFIG=y\nCONFIG_SCSI_UFS_QCOM=y\n'
DTC = shutil.which('dtc')


def kernel(release=R, version=V, config=CONFIG):
    k = bytearray(0x100)
    k[56:60] = b'ARMd'
    k += f'Linux version {release} (builder@host) (clang) {version}\n'.encode()
    k += b'IKCFG_ST' + gzip.compress(config, mtime=0) + b'IKCFG_ED'
    return bytes(k)


def boot_v4(k, gz=False):
    if gz:
        k = gzip.compress(k, mtime=0)
    h = bytearray(4096)
    h[:8] = b'ANDROID!'
    struct.pack_into('<II', h, 8, len(k), 0)
    struct.pack_into('<I', h, 40, 4)
    return bytes(h) + k + b'\0' * (-len(k) % 4096)


def dtb(msm):
    src = f'/dts-v1/; / {{ qcom,msm-id = <{msm[0]:#x} {msm[1]:#x}>; }};'
    return subprocess.run([DTC, '-I', 'dts', '-O', 'dtb'], input=src.encode(), capture_output=True, check=True).stdout


def vendor_v4(dtbs):
    blob = b''.join(dtbs)
    h = bytearray(4096)
    h[:8] = b'VNDRBOOT'
    struct.pack_into('<III', h, 8, 4, 4096, 0)
    struct.pack_into('<I', h, 24, 0)
    struct.pack_into('<II', h, 2096, 2128, len(blob))
    return bytes(h) + blob


def dtbo(n):
    return struct.pack('>8I', 0xd7b7ab1e, 32 + 32 * n, 32, 32, n, 32, 4096, 0) + b'\0' * (32 * n)


def fails(res):
    return [t for level, t in res if level == 'FAIL']


class Kernel(unittest.TestCase):
    def run_check(self, k, gz=False):
        return rom_match.check(boot=boot_v4(k, gz), config=gzip.compress(CONFIG), uname_r=R, uname_v=V)

    def test_same_kernel_passes_raw_and_gzip(self):
        self.assertEqual(fails(self.run_check(kernel())), [])
        self.assertEqual(fails(self.run_check(kernel(), gz=True)), [])

    def test_other_build_of_the_same_release_fails(self):
        self.assertTrue(fails(self.run_check(kernel(version='#19 SMP PREEMPT Fri Oct 30 10:00:00 CST 2026'))))

    def test_other_config_fails(self):
        self.assertTrue(any('config' in t for t in fails(self.run_check(kernel(config=CONFIG + b'CONFIG_X=y\n')))))

    def test_printf_format_before_the_banner_is_skipped(self):
        k = bytearray(kernel())
        k[0x40:0x40] = b'Linux version %s (%s) codec registered (%s)\0'
        self.assertEqual(fails(self.run_check(bytes(k))), [])

    def test_proc_version_is_the_real_banner(self):
        k = kernel(release='4.19.325-cip136-st20-N0-kernel++', version='#18 SMP PREEMPT Thu Oct 29 19:56:25 CST 2026')
        pv = 'Linux version 4.19.325-cip136-st20-N0-kernel++ (builder@host) (clang) #18 SMP PREEMPT Thu Oct 29 19:56:25 CST 2026\n'
        ok = rom_match.check(boot=boot_v4(k), config=gzip.compress(CONFIG), proc_version=pv)
        self.assertEqual(fails(ok), [])
        other = kernel(release='4.19.325-cip135-st19-pipa-hyperos4-perf+')      # same config, another build
        self.assertTrue(fails(rom_match.check(boot=boot_v4(other), config=gzip.compress(CONFIG), proc_version=pv)))

    def test_no_ikconfig_fails(self):
        k = kernel().replace(b'IKCFG_ST', b'XXXXXXXX')
        self.assertTrue(any('IKCONFIG' in t for t in fails(self.run_check(k))))


@unittest.skipUnless(DTC, 'dtc not available')
class Trees(unittest.TestCase):
    def test_device_tree_for_the_soc(self):
        ok = rom_match.check(vendor=vendor_v4([dtb((0x164, 0x20000)), dtb((0x164, 0x20001))]))
        self.assertEqual(fails(ok), [])
        self.assertTrue(fails(rom_match.check(vendor=vendor_v4([dtb((0x164, 0x10000))]))))

    def test_dtbo_index(self):
        self.assertEqual(fails(rom_match.check(dtbo=dtbo(29))), [])
        self.assertTrue(fails(rom_match.check(dtbo=dtbo(9))))


STOCK = Path.home() / 'pipa-inputs/stock/payload-out/boot.img'


@unittest.skipUnless(STOCK.is_file(), 'OS2.0.16 boot.img not present')
class StockIsNotThePort(unittest.TestCase):
    def test_os2_kernel_is_not_the_installed_port_kernel(self):
        res = rom_match.check(boot=STOCK.read_bytes(), config=gzip.compress(CONFIG), uname_r=R, uname_v=V)
        self.assertEqual(len(fails(res)), 3)


if __name__ == '__main__':
    unittest.main()
