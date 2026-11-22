"""The pipa boot manager's environment (uefi-profiles/xiaomi/pipa/u-boot/files/board/xiaomi/pipa.env), held to the
rules of U-Boot v2026.07's own code. These test the configuration, not U-Boot on the tablet.

What U-Boot does with it, from its source at hakios-uefi's BASE_COMMIT (ece349ad):
- cmd/bootmenu.c: entries are bootmenu_0, bootmenu_1, ... read until the first missing one; each is "title=command",
  the title ending at the first '='; `bootmenu` without an argument takes its delay from bootmenu_delay; the entry
  highlighted first is bootmenu_default; a delay of 0 runs that entry without a menu.
- common/menu.c: the delay counts down once a second; any key stops it; at 0 the highlighted entry runs.
- drivers/button/button-uclass.c (BUTTON_REMAP_PHONE_KEYS): volume up -> KEY_UP, volume down -> KEY_DOWN,
  power -> KEY_ENTER; they reach the menu through stdin "button-kbd".
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / 'uefi-profiles' / 'xiaomi' / 'pipa' / 'u-boot' / 'files' / 'board' / 'xiaomi' / 'pipa.env'

# Commands that write storage, change slots, or expose the tablet's storage: none may appear in any variable.
WRITERS = re.compile(r'\b(fastboot|ums|saveenv|env\s+save|erase|dfu|gpt\s+write|mmc\s+write|scsi\s+write|ufs|'
                     r'nand|sf\s+write|part\s+set|abootimg\s+set|bcb\s+set|bcb\s+store)\b')


def read_env(path):
    """U-Boot's text environment format: name=value per line, '#' comments, '\\' continues a line."""
    env, pending = {}, ''
    for raw in path.read_text().splitlines():
        line = pending + raw.strip()
        pending = ''
        if line.endswith('\\'):
            pending = line[:-1] + ' '
            continue
        if not line or line.startswith('#'):
            continue
        name, _, value = line.partition('=')
        env[name.strip()] = value
    return env


def menu_entries(env):
    entries, n = [], 0
    while f'bootmenu_{n}' in env:
        title, _, command = env[f'bootmenu_{n}'].partition('=')
        entries.append((title, command))
        n += 1
    return entries


def after_timeout(env):
    """What runs when nobody presses anything (cmd/bootmenu.c + common/menu.c): the default entry's command."""
    entries = menu_entries(env)
    default = int(env.get('bootmenu_default', '0'))
    return entries[default]


class BootManagerEnv(unittest.TestCase):
    env = read_env(ENV)

    def test_autoboot_goes_straight_to_the_menu(self):
        self.assertEqual(self.env['bootdelay'], '0')
        self.assertEqual(self.env['bootcmd'].strip(), 'bootmenu')

    def test_ten_second_timeout(self):
        self.assertEqual(int(self.env['bootmenu_delay']), 10)

    def test_android_is_the_default_and_restarts_into_android(self):
        title, command = after_timeout(self.env)
        self.assertIn('Android', title)
        self.assertEqual(command.strip(), 'reset')

    def test_menu_has_android_hakios_recovery_in_order(self):
        titles = [t for t, _ in menu_entries(self.env)]
        self.assertTrue(titles[0].startswith('Android'))
        self.assertTrue(titles[1].startswith('HakiOS'))
        self.assertTrue(titles[2].startswith('Recovery or Fastboot'))

    def test_entries_are_contiguous_and_titles_have_no_equals(self):
        numbers = sorted(int(k.split('_')[1]) for k in self.env if re.fullmatch(r'bootmenu_\d+', k))
        self.assertEqual(numbers, list(range(len(numbers))))  # bootmenu.c stops at the first gap
        for title, command in menu_entries(self.env):
            self.assertTrue(title and command, title)

    def test_keys_reach_the_menu(self):
        self.assertIn('button-kbd', self.env['stdin'].split(','))

    def test_hakios_entry_falls_back_to_a_message_not_a_hang(self):
        _, command = menu_entries(self.env)[1]
        self.assertIn('hakios load', command)
        self.assertIn('else', command)
        self.assertIn('pause', command)

    def test_nothing_writes_the_tablet(self):
        for name, value in self.env.items():
            self.assertIsNone(WRITERS.search(value), f'{name}={value}')

    def test_writer_pattern_catches_writers(self):
        for bad in ('fastboot 0', 'ums 0 scsi 0', 'saveenv', 'env save', 'mmc write 0 0 0', 'ufs init'):
            self.assertIsNotNone(WRITERS.search(bad), bad)

    def test_shell_entry_stops_retry(self):
        titles = dict(menu_entries(self.env))
        self.assertIn('setenv bootretry -1', titles['U-Boot shell'])


if __name__ == '__main__':
    unittest.main()
