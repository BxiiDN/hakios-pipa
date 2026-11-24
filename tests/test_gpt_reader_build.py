"""package/gpt-reader/build-gpt-reader.py end to end on synthetic header v4 images: the reader keeps the installed kernel and
device trees byte for byte in its header v2 image, and refuses images that are not the installed ROM."""
import gzip
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tests'))
from test_rom_match import CONFIG, R, V, kernel, boot_v4, vendor_v4, dtb  # noqa: E402

BUILD = ROOT / 'package/gpt-reader/build-gpt-reader.py'
READY = all(shutil.which(t) for t in ('clang', 'ld.lld', 'mformat', 'mcopy', 'llvm-readelf', 'dtc'))


@unittest.skipUnless(READY, 'clang, lld, mtools or dtc missing')
class Build(unittest.TestCase):
    def build(self, k, trees, uname_v=V):
        d = Path(tempfile.mkdtemp())
        (d / 'boot.img').write_bytes(boot_v4(k))
        (d / 'vendor_boot.img').write_bytes(vendor_v4(trees))
        (d / 'config.gz').write_bytes(gzip.compress(CONFIG))
        r = subprocess.run([sys.executable, BUILD, '--boot', d / 'boot.img', '--vendor-boot', d / 'vendor_boot.img',
                            '--out', d / 'reader.img', '--config', d / 'config.gz', '--uname-r', R, '--uname-v', uname_v],
                           capture_output=True, text=True)
        return r, d / 'reader.img'

    def test_installed_kernel_and_trees_kept_byte_for_byte(self):
        k, trees = kernel(), [dtb((0x164, 0x20001)), dtb((0x164, 0x20000))]
        r, out = self.build(k, trees)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        img = out.read_bytes()
        ks, _, rs = struct.unpack_from('<III', img, 8)
        page, version = struct.unpack_from('<II', img, 36)
        dsz = struct.unpack_from('<I', img, 1648)[0]
        al = lambda n: (n + page - 1) // page * page
        self.assertEqual((version, page), (2, 4096))
        self.assertEqual(img[page:page + ks], k)
        self.assertEqual(img[page + al(ks) + al(rs):page + al(ks) + al(rs) + dsz], b''.join(trees))

    def test_other_kernel_is_refused(self):
        r, out = self.build(kernel(), [dtb((0x164, 0x20001))], uname_v='#19 SMP PREEMPT Fri Oct 30 10:00:00 CST 2026')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('refused', r.stdout + r.stderr)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
