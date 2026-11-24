"""The GPT (read only) UEFI Tools plugin (patches/unixnu/0007): its scan core GptScan.c, taken from the patch and built for
the host exactly as the firmware builds it, against tools/pipa_gpt.py on synthetic tables; and the plugin source can only
read (BlockIo ReadBlocks, no write, flush, Disk I/O or file system protocol)."""
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import gpt_capacity  # noqa: E402
import pipa_gpt  # noqa: E402
from test_pipa_gpt import make_gpt, stock, MIB_4K, TOTAL  # noqa: E402

PATCH = ROOT / 'patches/unixnu/0007-gpt-view-read-only-tools-plugin.patch'
CC = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
GIT = shutil.which('git')
DIR = 'package/UniXNUPkg/Driver/GptViewDxe'


def backup_of(head, sector, lbas):
    hdr = bytearray(head[sector:sector + 92])
    struct.pack_into('<QQ', hdr, 24, lbas - 1, 1)
    struct.pack_into('<Q', hdr, 72, lbas - 5)
    struct.pack_into('<I', hdr, 16, 0)
    struct.pack_into('<I', hdr, 16, zlib.crc32(bytes(hdr)) & 0xffffffff)
    return bytes(hdr).ljust(sector, b'\0')


@unittest.skipUnless(CC and GIT, 'no C compiler or git')
class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        subprocess.run([GIT, 'init', '-q', str(cls.tmp)], check=True)
        subprocess.run([GIT, 'apply', str(PATCH)], cwd=cls.tmp, check=True)
        cls.src = cls.tmp / DIR
        cls.exe = cls.tmp / 'gptview'
        subprocess.run([CC, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-DGPT_SCAN_HOST', '-I', str(cls.src),
                        str(ROOT / 'tests/host/gpt_view_host.c'), str(cls.src / 'GptScan.c'), '-o', str(cls.exe)], check=True)

    def scan(self, head, backup=None, lbas=TOTAL, sector=4096, need=gpt_capacity.need()):
        h = self.tmp / 'head.bin'
        h.write_bytes(head)
        b = '-'
        if backup is not None:
            (self.tmp / 'backup.bin').write_bytes(backup)
            b = str(self.tmp / 'backup.bin')
        out = subprocess.run([str(self.exe), str(h), b, str(sector), str(lbas), str(need)], capture_output=True, text=True,
                             check=True).stdout
        fields, lines = {}, []
        for line in out.splitlines():
            k, _, v = line.partition('=')
            (lines.append(v) if k == 'line' else fields.__setitem__(k, v))
        return fields, lines

    def compare(self, parts, lbas=TOTAL):
        head = make_gpt(parts, 4096, lbas)
        fields, lines = self.scan(head, backup_of(head, 4096, lbas), lbas)
        table = pipa_gpt.parse_gpt(head, 'sda.bin')
        free = pipa_gpt.free_ranges(table)
        self.assertEqual(int(fields['flags']), 0, lines)
        self.assertEqual(int(fields['partitions']), len(table['partitions']))
        self.assertEqual(int(fields['free']), sum(b - a + 1 for a, b in free))
        self.assertEqual(int(fields['ranges']), len(free))
        largest = max(free, key=lambda r: r[1] - r[0], default=(0, -1))
        self.assertEqual(int(fields['largest']), largest[1] - largest[0] + 1 if free else 0)
        return fields, lines

    def test_userdata_to_the_end(self):
        fields, lines = self.compare(stock(free_tail=False))
        self.assertEqual((fields['userdata'], fields['last'], fields['free']), ('1', 'userdata', '0'))
        self.assertTrue(lines[0].startswith('LUN 0 (userdata): '))
        self.assertIn('no room without resizing userdata', lines[4])

    def test_free_tail_fits_design_a(self):
        parts = stock(free_tail=False)
        name, first, last, attrs = parts[-1]
        parts[-1] = (name, first, last - 24 * 1024 * MIB_4K, attrs)
        fields, lines = self.compare(parts)
        self.assertEqual(int(fields['largest']), 24 * 1024 * MIB_4K)
        self.assertIn('DESIGN A FITS', lines[4])

    def test_holes_between_partitions(self):
        parts = stock()
        parts.insert(3, ('gap_maker', parts[2][2] + 1000, parts[2][2] + 2000, 0))
        parts = [(n, f, l, a) for n, f, l, a in parts if n != 'boot_b']
        self.compare(parts)

    def test_damage_is_reported_not_trusted(self):
        head = bytearray(make_gpt(stock(free_tail=False)))
        backup = backup_of(bytes(head), 4096, TOTAL)
        head[2 * 4096 + 40] ^= 1                                       # an entry's last LBA: the entry CRC breaks
        fields, lines = self.scan(bytes(head), backup)
        self.assertTrue(int(fields['flags']) & 4)                       # GPT_SCAN_BAD_ENTRIES
        self.assertIn('UNKNOWN', lines[4])
        good = make_gpt(stock(free_tail=False))
        fields, _ = self.scan(good, None)
        self.assertTrue(int(fields['flags']) & 8)                       # no backup read: GPT_SCAN_BAD_BACKUP
        bad = bytearray(backup_of(good, 4096, TOTAL))
        bad[30] ^= 1
        fields, _ = self.scan(good, bytes(bad))
        self.assertTrue(int(fields['flags']) & 8)

    def test_no_gpt_and_bad_header(self):
        fields, lines = self.scan(b'\0' * 8192)
        self.assertEqual(int(fields['flags']), 1)
        self.assertTrue(lines[0].startswith('no GPT'))
        head = bytearray(make_gpt(stock()))
        head[4096 + 20] ^= 1
        self.assertEqual(int(self.scan(bytes(head))[0]['flags']), 2)

    def test_backup_lba_not_at_the_disk_end(self):
        head = make_gpt(stock(free_tail=False), 4096, TOTAL)
        fields, _ = self.scan(head, backup_of(head, 4096, TOTAL + 8), TOTAL + 8)
        self.assertTrue(int(fields['flags']) & 16)

    def test_existing_ipados_is_seen(self):
        parts = stock(free_tail=True)
        last_usable = TOTAL - 6
        parts.append(('ipados', last_usable - 4096 * MIB_4K + 1, last_usable, 0))
        fields, lines = self.compare(parts)
        self.assertEqual(fields['ipados'], '1')
        self.assertIn('ipados: present', lines[4])


@unittest.skipUnless(GIT, 'no git')
class ReadOnlySource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp())
        subprocess.run([GIT, 'init', '-q', str(tmp)], check=True)
        subprocess.run([GIT, 'apply', str(PATCH)], cwd=tmp, check=True)
        cls.src = '\n'.join((tmp / DIR / f).read_text() for f in ('GptViewDxe.c', 'GptScan.c'))
        cls.inf = (tmp / DIR / 'GptViewDxe.inf').read_text()

    def test_only_readblocks(self):
        code = re.sub(r'/\*.*?\*/|//[^\n]*', '', self.src, flags=re.S)
        self.assertIn('->ReadBlocks (', code)
        for forbidden in ('WriteBlocks', 'FlushBlocks', 'DiskIo', 'SimpleFileSystem', 'EraseBlocks', 'SetVariable', 'ResetSystem'):
            self.assertNotIn(forbidden, code, forbidden)

    def test_protocols_declared(self):
        protocols = set(re.findall(r'^\s*(g\w+ProtocolGuid)', self.inf, re.M))
        self.assertEqual(protocols, {'gEfiBlockIoProtocolGuid', 'gUniXNUMenuPluginProtocolGuid'})

    def test_need_matches_the_capacity_tool(self):
        self.assertIn(f'{gpt_capacity.need()}ULL', self.src)


if __name__ == '__main__':
    unittest.main()
