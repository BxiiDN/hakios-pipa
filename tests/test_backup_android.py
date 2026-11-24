"""scripts/backup-android.sh: never writes to the tablet, never into the repository, and verify catches a changed file."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts/backup-android.sh'


class BackupScript(unittest.TestCase):
    def test_device_commands_only_read(self):
        src = SCRIPT.read_text()
        code = '\n'.join(l for l in src.splitlines() if not l.lstrip().startswith('#'))
        for bad in (r'adb\s+push', r'adb\s+install', r'pm\s+(uninstall|clear|install|disable)', r'settings\s+put',
                    r'\brm\s+-', r'su\s+-c', r'adb\s+reboot', r'fastboot', r'adb\s+shell[^\n]*\b(rm|mv|dd|cp)\b'):
            self.assertIsNone(re.search(bad, code), bad)
        self.assertRegex(code, r'adb pull /sdcard/')

    def test_refuses_a_directory_inside_the_repository(self):
        r = subprocess.run(['bash', str(SCRIPT), 'verify', str(ROOT / 'backup-here')], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('inside the repository', r.stdout + r.stderr)

    def test_verify(self):
        d = Path(tempfile.mkdtemp())
        (d / 'sdcard').mkdir()
        (d / 'sdcard/a.jpg').write_bytes(b'photo')
        sums = subprocess.run('find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum', shell=True, cwd=d,
                              capture_output=True, text=True, check=True).stdout
        (d / 'SHA256SUMS').write_text(sums)
        self.assertEqual(subprocess.run(['bash', str(SCRIPT), 'verify', str(d)], capture_output=True).returncode, 0)
        (d / 'sdcard/a.jpg').write_bytes(b'changed')
        self.assertNotEqual(subprocess.run(['bash', str(SCRIPT), 'verify', str(d)], capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
