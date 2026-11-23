"""tools/userland_check.py on a made-up root with Mach-O files written here (no Apple file): required programs,
arm64 slices, libraries on disk or in a shared cache's image list, launchd jobs."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import userland_check as uc  # noqa: E402


def macho(libs, cpu=uc.ARM64, weak=()):
    cmds = b''
    for lib in list(libs) + list(weak):
        name = lib.encode() + b'\0'
        size = (24 + len(name) + 7) & ~7
        cmd = uc.LC_LOAD_WEAK_DYLIB if lib in weak else uc.LC_LOAD_DYLIB
        cmds += struct.pack('<IIIIII', cmd, size, 24, 0, 0, 0) + name.ljust(size - 24, b'\0')
    n = len(libs) + len(weak)
    return struct.pack('<IIIIIIII', 0xfeedfacf, cpu, 0, 2, n, len(cmds), 0, 0) + cmds


def fat(*parts):
    out, offset = bytearray(struct.pack('>II', 0xcafebabe, len(parts))), 4096
    body = b''
    for cpu, data in parts:
        out += struct.pack('>IIIII', cpu, 0, offset + len(body), len(data), 12)
        body += data.ljust(4096, b'\0')
    return bytes(out.ljust(4096, b'\0')) + body


def make_root(tmp, drop=None, cpu=uc.ARM64, cache_libs=('/usr/lib/libSystem.B.dylib',)):
    root = Path(tmp)
    for _, rel in uc.REQUIRED:
        path = uc.binary_of(root, rel) if not rel.endswith('.framework') else root / rel / Path(rel).stem
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(macho(['/usr/lib/libSystem.B.dylib', '/usr/lib/libobjc.A.dylib'], cpu, weak=['/usr/lib/libnope.dylib']))
    (root / 'usr/lib').mkdir(parents=True, exist_ok=True)
    (root / 'usr/lib/libobjc.A.dylib').write_bytes(macho([]))
    cache = root / uc.CACHE_DIRS[1]
    cache.mkdir(parents=True, exist_ok=True)
    (cache / 'dyld_shared_cache_arm64e').write_bytes(b'dyld_v1  arm64e\0' + b''.join(b'\0' + l.encode() + b'\0' for l in cache_libs))
    for plist in uc.LAUNCH_DAEMONS:
        (root / plist).parent.mkdir(parents=True, exist_ok=True)
        (root / plist).write_bytes(b'bplist00' + b'\0' * 32)
    if drop:
        target = root / drop
        if target.is_file():
            target.unlink()
    return root


def fails(findings):
    return [t for level, t in findings if level == 'FAIL']


class Userland(unittest.TestCase):
    def test_complete_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fails(uc.check(make_root(tmp))[0]), [])

    def test_missing_springboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = fails(uc.check(make_root(tmp, drop='System/Library/CoreServices/SpringBoard.app/SpringBoard'))[0])
            self.assertTrue(any('SpringBoard' in t and 'missing' in t for t in bad), bad)

    def test_wrong_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = fails(uc.check(make_root(tmp, cpu=0x01000007))[0])
            self.assertTrue(any('no arm64' in t for t in bad), bad)

    def test_library_neither_on_disk_nor_in_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = fails(uc.check(make_root(tmp, cache_libs=()))[0])
            self.assertTrue(any('libSystem.B.dylib' in t for t in bad), bad)

    def test_fat_binary_and_launchd_job(self):
        data = fat((0x01000007, macho([], 0x01000007)), (uc.ARM64, macho(['/a.dylib'])))
        self.assertEqual([c for c, _ in uc.slices(data)], [0x01000007, uc.ARM64])
        self.assertEqual(uc.dylibs(data, uc.slices(data)[1][1]), [('/a.dylib', False)])
        with tempfile.TemporaryDirectory() as tmp:
            bad = fails(uc.check(make_root(tmp, drop=uc.LAUNCH_DAEMONS[0]))[0])
            self.assertTrue(any('launchd job missing' in t for t in bad), bad)


if __name__ == '__main__':
    unittest.main()


class FrameworkInSharedCache(unittest.TestCase):
    """iOS 17: a framework's binary exists only as a shared-cache image; its bundle directory stays on disk."""
    QC = 'System/Library/Frameworks/QuartzCore.framework'

    def root(self, tmp, listed):
        libs = ['/usr/lib/libSystem.B.dylib'] + (['/' + self.QC + '/QuartzCore'] if listed else [])
        root = make_root(tmp, cache_libs=libs)
        (root / self.QC / 'QuartzCore').unlink()
        return root

    def test_framework_image_in_cache_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = uc.check(self.root(tmp, True))[0]
            self.assertEqual(fails(findings), [])
            self.assertTrue(any('QuartzCore' in t and 'image of the shared cache' in t for _, t in findings))

    def test_framework_image_not_in_cache_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = fails(uc.check(self.root(tmp, False))[0])
            self.assertTrue(any('QuartzCore' in t and 'neither on disk' in t for t in bad), bad)

    def test_framework_bundle_missing_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp, True)
            (root / self.QC).rmdir()
            self.assertTrue(any('QuartzCore' in t and 'missing' in t for t in fails(uc.check(root)[0])))


class SevenZipListing(unittest.TestCase):
    """The --dmg backend's reading of `7z l -slt` (synthetic text, no image)."""
    TEXT = ('Path = System/Library/Frameworks/QuartzCore.framework\nSize = \nMode = drwxr-xr-x\nMethod = \n\n'
            'Path = usr/lib/libz.dylib\nMode = lrwxr-xr-x\nMethod = symlink\n\n'
            'Path = usr/libexec/backboardd\nMode = -rwxr-xr-x\nMethod = ZLIB-rsrc\n\n'
            'Path = usr/libexec/backboardd:com.apple.ResourceFork\nMode = -rwxr-xr-x\nAlternate Stream = +\n\n')

    def test_kinds_and_streams(self):
        rows = {p: (k, m) for p, k, m in uc.parse_slt(self.TEXT)}
        self.assertEqual(rows['System/Library/Frameworks/QuartzCore.framework'][0], 'dir')
        self.assertEqual(rows['usr/lib/libz.dylib'][0], 'link')
        self.assertEqual(rows['usr/libexec/backboardd'], ('file', 'ZLIB-rsrc'))
        self.assertNotIn('usr/libexec/backboardd:com.apple.ResourceFork', rows)
