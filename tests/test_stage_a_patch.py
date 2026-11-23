"""patches/stage-a: the reference kernel only turns things off, and only what docs/BOOTSTRAP.md lists."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/stage-a/0001-reference-kernel-without-hid-and-legacy-display.patch'
OFF = {'NATIVE_LEGACY_DISPLAY', 'NATIVE_ADRENO', 'NATIVE_UFS', 'BOOT_PROGRESS', 'BOOT_PROGRESS_STANDALONE',
       'NATIVE_RAM_BLOCK', 'NATIVE_VIRTIO_BLOCK', 'VERIFIED_ROOT_PROBE', 'OWNER_DATA_MOUNT', 'OWNER_ROOT_AUDIT',
       'OWNER_ROOT_TRUST', 'OWNER_CACHE_MOUNT', 'OWNER_CACHE_STARTUP', 'OWNER_BOOT_MANIFEST', 'OWNER_UNION_SYSTEMOS'}


class StageAPatch(unittest.TestCase):
    def setUp(self):
        self.text = PATCH.read_text()
        self.added = [l[1:] for l in self.text.splitlines() if l.startswith('+') and not l.startswith('+++')]
        self.removed = [l[1:] for l in self.text.splitlines() if l.startswith('-') and not l.startswith('---')]

    def test_only_board_and_defconfig(self):
        self.assertEqual(set(re.findall(r'^\+\+\+ b/(\S+)', self.text, re.M)), {'board.toml', 'configs/pipa_defconfig'})

    def test_configs_only_turned_off(self):
        turned_off = {m.group(1) for l in self.added for m in [re.match(r'CONFIG_XNU_(\w+)=n$', l)] if m}
        self.assertEqual(turned_off, OFF)
        self.assertFalse([l for l in self.added if re.match(r'CONFIG_\w+=(y|")', l)], 'stage A turns nothing on')

    def test_archives_removed_are_exactly_two(self):
        archive_lines = [l.strip() for l in self.removed if l.strip().startswith('"') and l.strip().endswith('",')]
        self.assertEqual(archive_lines, ['"component:ShengHidInput",', '"build-gop-legacy-display.py",'])
        self.assertFalse([l for l in self.added if l.strip().startswith('"')], 'stage A adds no archive')

    def test_marked_never_a_boot_candidate(self):
        self.assertIn('never a boot candidate', self.text)


if __name__ == '__main__':
    unittest.main()
