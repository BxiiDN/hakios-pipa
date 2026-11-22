"""The iPadOS 17 boot manager: UniXNU's payload menu (\\EFI\\UniXNU\\unixnu.toml) after patches/unixnu/0001, on a
menu in exactly the form UniXNU 8542980's scripts/unixnu/payload.py writes it, read back with tomllib and held to
UniXNU's documented menu rules (docs/reference/boot-configuration.md at that commit):
- [boot] timeout: seconds before the default entry boots; any key stops the countdown;
- default: entry id; an entry with `confirm` never boots by countdown, and a default that needs confirmation
  falls back to the first entry that does not;
- `action = "reset"` restarts the machine (the stock bootloader then starts Android: the image was RAM-booted).
These test the configuration and the patch, not the firmware on the tablet.
"""
import importlib.util
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / 'patches' / 'unixnu' / '0001-payload-android-first-dual-boot-menu.patch'


def load_dualboot():
    """dualboot.py as the patch adds it (its + lines), loaded without UniXNU."""
    text = PATCH.read_text()
    block = text.split('+++ b/scripts/unixnu/dualboot.py', 1)[1].split('\ndiff --git', 1)[0]
    source = '\n'.join(line[1:] for line in block.splitlines() if line.startswith('+'))
    spec = importlib.util.spec_from_loader('dualboot', loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, 'dualboot.py', 'exec'), module.__dict__)
    return module


def generated(timeout=10, install=False):
    """The menu payload.py (UniXNU 8542980, lines 251-270) writes for the pipa board.toml [payload]."""
    line = '-v serial=3'
    config = (f'version = 1\n[boot]\ntimeout = {timeout}\ndefault = "xnu"\n[kits]\nautoload = false\n'
              f'[[entry]]\nid = "xnu"\ntitle = "Xiaomi Pad 6 (iPadOS 17.7.11)"\ntype = "xnu"\npath = "Payloads/kernel.macho"\n'
              f'args = "{line}"\n')
    if install:
        config += ('[[entry]]\nid = "install"\ntitle = "Install and boot"\nconfirm = "Reset Data?"\n'
                   'confirm_titles = ["Keep", "Reset"]\nconfirm_args = ["", "sheng-data-reset=1"]\n'
                   f'type = "xnu"\npath = "Payloads/kernel.macho"\nargs = "{line}"\n')
    config += ('[[entry]]\nid = "reset"\ntitle = "Restart"\ntype = "action"\naction = "reset"\n'
               '[[entry]]\nid = "shutdown"\ntitle = "Power off"\ntype = "action"\naction = "shutdown"\n')
    return config


def countdown_target(menu):
    entries = {e['id']: e for e in menu['entry']}
    target = entries[menu['boot']['default']]
    if 'confirm' in target:
        target = next(e for e in menu['entry'] if 'confirm' not in e)
    return target


class UniXNUMenu(unittest.TestCase):
    dualboot = load_dualboot()

    def menu(self, **kw):
        return tomllib.loads(self.dualboot.apply_dual_boot(generated(**kw), {'android_title': 'Android / HyperOS'}))

    def test_patch_touches_only_the_menu(self):
        files = re.findall(r'^\+\+\+ b/(\S+)', PATCH.read_text(), re.M)
        self.assertEqual(sorted(files), ['scripts/unixnu/dualboot.py', 'scripts/unixnu/payload.py'])
        self.assertIn('apply_dual_boot(config, spec.get(\'dualboot\'))', PATCH.read_text())

    def test_without_the_table_nothing_changes(self):
        self.assertEqual(self.dualboot.apply_dual_boot(generated(), None), generated())

    def test_android_first_default_and_timeout(self):
        menu = self.menu()
        self.assertEqual(menu['boot']['timeout'], 10)
        self.assertEqual(menu['boot']['default'], 'android')
        self.assertEqual(menu['entry'][0]['id'], 'android')
        self.assertEqual((menu['entry'][0]['type'], menu['entry'][0]['action']), ('action', 'reset'))
        self.assertEqual(countdown_target(menu)['id'], 'android')

    def test_order_android_ipados_recovery_then_builtins(self):
        ids = [e['id'] for e in self.menu(install=True)['entry']]
        self.assertEqual(ids, ['android', 'xnu', 'install', 'recovery', 'reset', 'shutdown'])
        xnu = self.menu()['entry'][1]
        self.assertEqual((xnu['type'], xnu['path']), ('xnu', 'Payloads/kernel.macho'))

    def test_unknown_menu_form_is_refused(self):
        with self.assertRaises(ValueError):
            self.dualboot.apply_dual_boot('version = 1\n[boot]\ndefault = "other"\n', {'x': 1})


if __name__ == '__main__':
    unittest.main()
