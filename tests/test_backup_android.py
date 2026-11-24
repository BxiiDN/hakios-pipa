"""scripts/backup-android.sh: never writes to the tablet (restore commands are only printed), never into the repository or a
Windows drive, compares every file with its hash on the tablet, and verify catches a changed file. A fake adb stands in
for the tablet."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts/backup-android.sh'

# fake adb: a "tablet" whose /sdcard is $FAKE_SDCARD; pull copies from it; shell runs a few read-only commands there
FAKE_ADB = r'''#!/usr/bin/env bash
case "$1" in
get-state) echo device ;;
shell)
  cmd="${*:2}"
  case "$cmd" in
    "getprop ro.product.device") echo pipa ;;
    getprop*|uname*) echo x ;;
    "pm list packages -f -3") echo "package:/data/app/~~a/com.example-b/base.apk=com.example" ;;
    "pm list packages -f") echo "package:/data/app/~~a/com.example-b/base.apk=com.example" ;;
    "pm path com.example") echo "package:/data/app/~~a/com.example-b/base.apk" ;;
    settings*) echo "a=b" ;;
    "dumpsys user") echo "    State: ${FAKE_USER_STATE:-RUNNING_UNLOCKED}" ;;
    "ls -A /sdcard/ 2>/dev/null | wc -l") ls -A "$FAKE_SDCARD" | wc -l ;;
    sha256sum*) sha256sum "$FAKE_APK" ;;
    "cd /sdcard/ && find . -type f -exec sha256sum {} + 2>/dev/null") (cd "$FAKE_SDCARD" && find . -type f -exec sha256sum {} +) ;;
    *) echo "unexpected: $cmd" >&2; exit 9 ;;
  esac ;;
pull)
  src=$2; dst=$(wslpath -u "$3" 2>/dev/null || echo "$3")
  if [ "$src" = /sdcard/. ]; then cp -a "$FAKE_SDCARD"/. "$dst"/; [ -n "$FAKE_BREAK" ] && : > "$dst/$FAKE_BREAK"; else cp "$FAKE_APK" "$dst"; fi ;;
*) echo "unexpected adb $1" >&2; exit 9 ;;
esac
'''


class BackupScript(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'bin').mkdir()
        adb = self.tmp / 'bin/adb'
        adb.write_text(FAKE_ADB)
        adb.chmod(0o755)
        self.sd = self.tmp / 'tablet-sdcard'
        (self.sd / 'DCIM').mkdir(parents=True)
        (self.sd / 'DCIM/a.jpg').write_bytes(b'photo')
        (self.sd / 'Download').mkdir()
        (self.sd / 'Download/doc one.pdf').write_bytes(b'pdf')
        (self.tmp / 'base.apk').write_bytes(b'apk')
        self.env = dict(os.environ, PATH=f'{self.tmp / "bin"}:{os.environ["PATH"]}', FAKE_SDCARD=str(self.sd),
                        FAKE_APK=str(self.tmp / 'base.apk'), HAKIOS_PRIVATE=str(self.tmp / 'private'))

    def run_script(self, *args, **extra):
        return subprocess.run(['bash', str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                              env=dict(self.env, **extra))

    def test_device_commands_only_read(self):
        code = '\n'.join(l for l in SCRIPT.read_text().splitlines()
                         if not l.lstrip().startswith('#') and not re.match(r'\s*(echo|printf)\b', l))
        for bad in (r'adb\s+push', r'adb\s+install', r'pm\s+(uninstall|clear|install|disable)', r'settings\s+put',
                    r'su\s+-c', r'adb\s+reboot', r'fastboot', r'adb_sh\s+"?[^"\n]*\b(rm|mv|dd|cp|touch|mkdir)\b'):
            self.assertIsNone(re.search(bad, code), bad)

    def test_refuses_the_repository_and_windows_drives(self):
        for target in (ROOT / 'backup-here', Path('/mnt/c/backup')):
            r = self.run_script('verify', target)
            self.assertNotEqual(r.returncode, 0)
            self.assertRegex(r.stdout + r.stderr, 'inside the repository|Windows drive')

    def test_backup_compares_with_the_tablet_and_verify(self):
        out = self.tmp / 'backup'
        r = self.run_script('backup', out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('BACKUP COMPLETE', r.stdout + r.stderr)
        self.assertEqual((out / 'sdcard/Download/doc one.pdf').read_bytes(), b'pdf')
        self.assertEqual(self.run_script('verify', out).returncode, 0)
        (out / 'sdcard/DCIM/a.jpg').write_bytes(b'changed')
        self.assertNotEqual(self.run_script('verify', out).returncode, 0)

    def test_a_failed_pull_is_caught(self):
        r = self.run_script('backup', self.tmp / 'backup2', FAKE_BREAK='DCIM/a.jpg')    # the PC copy ends up 0 bytes
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('BACKUP INCOMPLETE', r.stdout + r.stderr)

    def test_locked_user_storage_is_refused(self):
        r = self.run_script('backup', self.tmp / 'backup4', FAKE_USER_STATE='RUNNING_LOCKED')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('locked', r.stdout + r.stderr)
        self.assertFalse((self.tmp / 'backup4').exists())

    def test_restore_plan_only_prints(self):
        out = self.tmp / 'backup3'
        self.assertEqual(self.run_script('backup', out).returncode, 0)
        r = self.run_script('restore-plan', out)
        self.assertEqual(r.returncode, 0)
        self.assertIn('adb push', r.stdout)
        self.assertIn('adb install-multiple', r.stdout)


if __name__ == '__main__':
    unittest.main()
