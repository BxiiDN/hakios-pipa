"""package/gpt-reader: the init as compiled (-DREADER_GPT, after the preprocessor) can only read the UFS disks. Every open that
may write names a RAM or configfs/sysfs path; every disk node is made r-- and opened O_RDONLY; BLKROSET comes before any pread
and a disk without BLKROGET=1 is skipped; nothing is mounted but the pseudo file systems."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'package/gpt-reader/init.c'
CLANG = shutil.which('clang')
ALLOWED_WRITES = ('GADGET', 'LUN', '"/sys/bus/platform/devices/a600000.ssusb/mode"')


@unittest.skipUnless(CLANG, 'clang not available')
class CompiledSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = subprocess.run([CLANG, '--target=aarch64-linux-gnu', '-E', '-P', '-DREADER_GPT', '-DGADGET_KEEP', str(SRC)],
                                 capture_output=True, text=True, check=True).stdout
        cls.raw = SRC.read_text()

    def test_data_mode_is_not_compiled(self):
        self.assertNotIn('copy_data', self.src)
        self.assertIn('copy_gpt', self.src)

    def test_writable_opens_are_ram_or_pseudo_files(self):
        opens = re.findall(r'SysOpenat, AtFdcwd, \(long\)([^,]+), (OWronly|ORdwr)', self.src)
        targets = {t for t, _ in opens}
        self.assertEqual(targets, {'path', '"/dev/pmsg0"', '"/dev/kmsg"', '"/log.img"'})
        # 'path' is write_file's parameter: each call names a gadget/configfs file or the USB controller's mode
        calls = re.findall(r'write_file\(([^,]+),', self.raw)
        self.assertTrue(calls)
        for c in calls:
            if c.strip() in ('const char *path',):
                continue
            self.assertTrue(c.strip().startswith(ALLOWED_WRITES), c)

    def test_pwrite_only_into_the_ram_image(self):
        for fd in re.findall(r'SysPwrite64, (\w+),', self.src):
            self.assertEqual(fd, 'image')

    def test_disks_are_read_only_before_the_first_read(self):
        body = self.raw[self.raw.index('static long copy_gpt'):]
        body = body[:body.index('\n}\n')]
        self.assertIn('060400', body)                                # block node, mode r--------
        self.assertNotRegex(body, r'OWronly|ORdwr|SysWrite\b|SysPwrite64, d')
        self.assertLess(body.index('BLKROSET_G'), body.index('SysPread64G'))
        self.assertLess(body.index('if (ro != 1)'), body.index('SysPread64G'))

    def test_ends_with_power_off_not_a_fastboot_restart(self):
        start = self.src[self.src.index('void start(void)'):]
        self.assertIn('power_off_unplugged();', start)
        self.assertNotIn('reboot_bootloader();', start)
        self.assertIn('0x4321fedc', self.src)                       # LINUX_REBOOT_CMD_POWER_OFF

    def test_only_pseudo_file_systems_are_mounted(self):
        mounts = re.findall(r'SysMount, \(long\)"([^"]+)"', self.src)
        self.assertEqual(set(mounts), {'devtmpfs', 'sysfs', 'proc', 'configfs', 'pstore'})


if __name__ == '__main__':
    unittest.main()
