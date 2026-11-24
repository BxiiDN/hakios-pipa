"""scripts/windows/dump-pipa-usb.ps1 run by Windows PowerShell (only where WSL has it: never on the CI runner) against
synthetic disk images: a full-size LUN 0 (sparse) with the measured layout is recognised, a damaged one and a boot LUN
are told apart, only the proven disk is copied, and the copy is byte-identical with a SHA-256 line."""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tests'))
from test_gpt_view import backup_of  # noqa: E402
from test_measured_lun0 import PARTS, DISK_LBAS  # noqa: E402
from test_pipa_gpt import make_gpt  # noqa: E402

PS = shutil.which('powershell.exe') or '/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe'
HAVE = Path(PS).is_file() and shutil.which('wslpath')
SCRIPT = ROOT / 'scripts/windows/dump-pipa-usb.ps1'
S = 4096


def win(p):
    return subprocess.run(['wslpath', '-w', str(p)], capture_output=True, text=True, check=True).stdout.strip()


def disk(parts, total, path, damage=False):
    head = make_gpt(parts, S, total)
    head = head + b'\0' * (6 * S - len(head))
    if damage:
        head = head[:2 * S + 300] + bytes([head[2 * S + 300] ^ 1]) + head[2 * S + 301:]
    tail = head[2 * S:6 * S] + backup_of(head, S, total)
    with open(path, 'wb') as f:
        f.write(head)
        f.truncate(total * S)
        f.seek((total - 5) * S)
        f.write(tail)


@unittest.skipUnless(HAVE, 'Windows PowerShell is not reachable from here')
class DumpScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(dir=Path.home()))      # inside WSL's file system, reachable from Windows
        disk([(p['name'], p['first_lba'], p['last_lba'], 0) for p in PARTS], DISK_LBAS, cls.tmp / 'lun0.img')
        disk([(p['name'], p['first_lba'], p['last_lba'], 0) for p in PARTS], DISK_LBAS, cls.tmp / 'bad.img', damage=True)
        names = ['xbl_a', 'abl_a', 'boot_a', 'xbl_b', 'abl_b', 'boot_b', 'vendor_boot_b', 'dtbo_b', 'vbmeta_b']
        disk([(n, 6 + i * 8, 6 + i * 8 + 7, 0) for i, n in enumerate(names)], 512, cls.tmp / 'boot.img')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ps(self, *args):
        r = subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', win(SCRIPT), *args],
                           capture_output=True, text=True, timeout=300)
        return r.returncode, (r.stdout + r.stderr)

    def test_identities(self):
        rc, out = self.ps('-Check', '-Disk', '0', '-ImageFile', win(self.tmp / 'lun0.img'))
        self.assertIn('kind=lun0', out, out)
        rc, out = self.ps('-Check', '-Disk', '0', '-ImageFile', win(self.tmp / 'bad.img'))
        self.assertIn('entries CRC32 does not match', out, out)
        rc, out = self.ps('-Check', '-Disk', '0', '-ImageFile', win(self.tmp / 'boot.img'))
        self.assertIn('kind=boot', out, out)

    def test_only_the_proven_disk_is_copied(self):
        out_dir = self.tmp / 'out'
        rc, out = self.ps('-Disk', '0', '-Mode', 'lun0', '-Out', win(out_dir), '-ImageFile', win(self.tmp / 'boot.img'))
        self.assertNotEqual(rc, 0)
        self.assertIn('refusing', out)
        self.assertFalse((out_dir / 'lun0-head.img').exists())
        rc, out = self.ps('-Disk', '0', '-Mode', 'boot', '-Out', win(out_dir), '-ImageFile', win(self.tmp / 'boot.img'))
        self.assertEqual(rc, 0, out)
        self.assertEqual((out_dir / 'boot-lun.img').read_bytes(), (self.tmp / 'boot.img').read_bytes())
        sums = (out_dir / 'SHA256SUMS.txt').read_text(encoding='utf-8-sig')
        self.assertIn(hashlib.sha256((self.tmp / 'boot.img').read_bytes()).hexdigest() + '  boot-lun.img', sums)


if __name__ == '__main__':
    unittest.main()
