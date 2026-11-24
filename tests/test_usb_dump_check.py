"""tools/usb_dump_check.py on synthetic dumps of the two read-only USB disks: the recovery set is accepted only when the
GPTs are sound, LUN 0 is the measured layout, super is a liblp image and boot_b is the installed kernel; any changed
byte or another ROM's kernel is refused. scripts/windows/dump-pipa-usb.ps1 opens the tablet's disk read only."""
import gzip
import hashlib
import json
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import usb_dump_check as u  # noqa: E402
from test_gpt_view import backup_of  # noqa: E402
from test_pipa_gpt import make_gpt  # noqa: E402
from test_rom_match import CONFIG, R, V, kernel, boot_v4, vendor_v4, dtb, dtbo  # noqa: E402

DTC = shutil.which('dtc')
S = 4096


def pad(b, blocks):
    return b + b'\0' * (blocks * S - len(b))


def disk(contents, total):
    """A whole disk image: GPT, the named contents (bytes, size in blocks), backup GPT."""
    parts, lba, body = [], 6, b''
    for name, data, blocks in contents:
        parts.append((name, lba, lba + blocks - 1, 0))
        body += pad(data, blocks)
        lba += blocks
    head = make_gpt(parts, S, total)
    head = pad(head, 6)
    img = bytearray(total * S)
    img[:len(head)] = head
    img[6 * S:6 * S + len(body)] = body
    img[(total - 5) * S:] = head[2 * S:6 * S] + backup_of(head, S, total)
    return bytes(img), parts


@unittest.skipUnless(DTC, 'dtc not available')
class Dump(unittest.TestCase):
    def build(self, boot_kernel=None):
        d = Path(tempfile.mkdtemp())
        k = boot_kernel or kernel()
        img, _ = disk([('boot_a', b'old', 8), ('boot_b', boot_v4(k), 8), ('vendor_boot_b', vendor_v4([dtb((0x164, 0x20001))]), 8),
                       ('dtbo_b', dtbo(13), 8), ('vbmeta_b', b'AVB0', 1)], 64)
        (d / 'boot-lun.img').write_bytes(img)
        super_img = b'\0' * 4096 + struct.pack('<I', u.LP_GEOMETRY_MAGIC)
        lun0, parts = disk([('super', super_img, 4), ('vbmeta_system_b', b'AVB0', 1), ('userdata', b'', 16)], 64)
        first = parts[-1][1]
        (d / 'lun0-head.img').write_bytes(lun0[:first * S])
        (d / 'lun0-tail.bin').write_bytes(lun0[-5 * S:])
        layout = {'partitions': [{'name': n, 'first_lba': f, 'last_lba': l} for n, f, l, _ in parts]}
        (d / 'layout.json').write_text(json.dumps(layout))
        (d / 'config.gz').write_bytes(gzip.compress(CONFIG))
        (d / 'proc-version.txt').write_text(f'Linux version {R} (builder@host) (clang) {V}\n')
        sums = ''.join(f'{hashlib.sha256((d / n).read_bytes()).hexdigest()}  {n}\n'
                       for n in ('boot-lun.img', 'lun0-head.img', 'lun0-tail.bin'))
        (d / 'SHA256SUMS.txt').write_text(sums)
        return d

    def run_check(self, d):
        return u.check(d, d / 'config.gz', d / 'proc-version.txt', layout_path=d / 'layout.json')

    def test_sound_dump_gives_the_recovery_set(self):
        d = self.build()
        r = self.run_check(d)
        self.assertEqual(r['problems'], [])
        for name in ('boot', 'vendor_boot', 'dtbo', 'vbmeta', 'vbmeta_system', 'super'):
            self.assertTrue((d / 'recovery' / f'{name}.img').is_file(), name)
        self.assertTrue((d / 'recovery/boot.img').read_bytes().startswith(b'ANDROID!'))

    def test_another_roms_kernel_is_refused(self):
        d = self.build(kernel(version='#1 SMP PREEMPT Mon Jan 1 00:00:00 UTC 2024'))
        r = self.run_check(d)
        self.assertTrue(any('rom_match' in p for p in r['problems']))
        self.assertFalse((d / 'recovery').exists())

    def test_a_changed_byte_is_refused(self):
        d = self.build()
        img = bytearray((d / 'boot-lun.img').read_bytes())
        img[7 * S] ^= 1
        (d / 'boot-lun.img').write_bytes(bytes(img))
        self.assertTrue(any('SHA256SUMS' in p for p in self.run_check(d)['problems']))

    def test_lun0_must_be_the_measured_layout(self):
        d = self.build()
        layout = json.loads((d / 'layout.json').read_text())
        layout['partitions'][0]['last_lba'] += 1
        (d / 'layout.json').write_text(json.dumps(layout))
        self.assertTrue(any('measured' in p for p in self.run_check(d)['problems']))


class WindowsScript(unittest.TestCase):
    def test_tablet_disk_is_opened_read_only(self):
        src = (ROOT / 'scripts/windows/dump-pipa-usb.ps1').read_text()
        opens = re.findall(r'\[System\.IO\.File\]::Open\(([^\n]+)', src)
        drive = [o for o in opens if 'PhysicalDrive' in o]
        self.assertEqual(len(drive), 1)
        self.assertIn('[System.IO.FileAccess]::Read,', drive[0])
        self.assertNotRegex(src, r'\$stream\.Write|SetLength|Initialize-Disk|Clear-Disk|Format-Volume|New-Partition|diskpart')
        self.assertIn("BusType -ne 'USB'", src)


if __name__ == '__main__':
    unittest.main()
