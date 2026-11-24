"""GPT export (QR): GptExport.c from patches/unixnu/0007, built for the host, makes the frames the firmware shows; the
host decoder (tools/gpt_export_decode.py) turns them back into the exact sectors and checks primary and backup. Frames
in any order, repeated, or one missing, and damaged bytes are handled or refused."""
import random
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
import gpt_export_decode as dec  # noqa: E402
from test_gpt_view import backup_of, PATCH, DIR  # noqa: E402
from test_measured_lun0 import PARTS, DISK_LBAS  # noqa: E402
from test_pipa_gpt import make_gpt  # noqa: E402

CC = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
GIT = shutil.which('git')


@unittest.skipUnless(CC and GIT, 'no C compiler or git')
class Export(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        subprocess.run([GIT, 'init', '-q', str(cls.tmp)], check=True)
        subprocess.run([GIT, 'apply', str(PATCH)], cwd=cls.tmp, check=True)
        src = cls.tmp / DIR
        cls.exe = cls.tmp / 'gptexport'
        subprocess.run([CC, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-DGPT_SCAN_HOST', '-I', str(src),
                        str(ROOT / 'tests/host/gpt_export_host.c'), str(src / 'GptExport.c'), '-o', str(cls.exe)], check=True)
        # the measured LUN 0 (tests/data/pipa-lun0-layout.json) with its backup: head = LBA 0..5, tail = last 5 LBAs
        cls.head = make_gpt([(p['name'], p['first_lba'], p['last_lba'], 0) for p in PARTS], 4096, DISK_LBAS)
        cls.head += b'\0' * (6 * 4096 - len(cls.head))
        cls.tail = cls.head[2 * 4096:6 * 4096] + backup_of(cls.head, 4096, DISK_LBAS)

    def export(self):
        (self.tmp / 'h').write_bytes(self.head)
        (self.tmp / 't').write_bytes(self.tail)
        out = subprocess.run([str(self.exe), self.tmp / 'h', self.tmp / 't', '4096', str(DISK_LBAS), self.tmp / 'frames',
                              self.tmp / 'env'], capture_output=True, text=True, check=True).stdout
        return (self.tmp / 'frames').read_bytes(), (self.tmp / 'env').read_bytes(), out

    def test_round_trip_is_byte_exact(self):
        frames, env, out = self.export()
        self.assertIn('frames=63', out)                   # 44 KiB of sectors: 63 QR frames of 720 bytes
        r = dec.decode(frames)
        self.assertEqual(r['problems'], [])
        self.assertEqual((r['head'], r['tail'], r['name']), (self.head, self.tail, 'pipa-lun0-gpt.hkgpt'))
        self.assertEqual(r['table']['last_usable_lba'], 61880314)
        self.assertEqual(dec.decode(env)['head'], self.head)          # what a receiver saves as the envelope
        self.assertEqual(dec.decode(dec.envelope_data(env)[1])['tail'], self.tail)   # or as the file inside it

    def test_order_and_repeats_do_not_matter(self):
        frames, _, _ = self.export()
        f = [frames[i:i + dec.FRAME] for i in range(0, len(frames), dec.FRAME)]
        shuffled = f + f[:10]
        random.Random(7).shuffle(shuffled)
        self.assertEqual(dec.decode(b''.join(shuffled))['head'], self.head)

    def test_missing_or_damaged_frames_are_refused(self):
        frames, _, _ = self.export()
        with self.assertRaisesRegex(dec.ExportError, 'missing'):
            dec.decode(frames[:-dec.FRAME])
        bad = bytearray(frames)
        bad[dec.FRAME * 3 + 100] ^= 1
        with self.assertRaisesRegex(dec.ExportError, 'CRC32'):
            dec.decode(bytes(bad))

    def test_unsound_backup_is_reported(self):
        frames, env, _ = self.export()
        name, data = dec.envelope_data(env)
        body = bytearray(data[32:])
        body[len(body) - 4096 + 30] ^= 1                 # inside the backup header
        c = bytearray(data[:32])
        struct.pack_into('<I', c, 28, zlib.crc32(bytes(body)) & 0xffffffff)
        r = dec.decode(bytes(c) + bytes(body))
        self.assertTrue(r['problems'])

    def test_cli_writes_the_dump(self):
        frames, _, _ = self.export()
        (self.tmp / 'scan.bin').write_bytes(frames)
        out = self.tmp / 'decoded'
        r = subprocess.run([sys.executable, ROOT / 'tools/gpt_export_decode.py', self.tmp / 'scan.bin', '--out', out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('VERIFIED', r.stdout)
        self.assertEqual((out / 'sda.bin').read_bytes(), self.head)


if __name__ == '__main__':
    unittest.main()
