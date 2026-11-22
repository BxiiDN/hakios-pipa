"""tools/verify_bootimg.py --unixnu and tools/fat_reader.py on boot images built here the way UniXNU packs one for
pipa: gzip(BootShim + firmware) as the kernel, a FAT32 payload volume as the ramdisk, page 2048, kernel at
0x10008000. The menu inside is the one UniXNU's builder writes when the pinned trees are present, else a copy of its
form. Fixtures only: no Apple file, no firmware."""
import gzip
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import fatimage  # noqa: E402
import verify_bootimg as vb  # noqa: E402
from fat_reader import Fat  # noqa: E402

WORK = Path(os.environ.get('HAKIOS_WORK', ROOT.parent / 'hakios-work'))
SAFE_MENU = '''version = 1
[boot]
timeout = 10
default = "android"
[[entry]]
id = "android"
title = "Android / HyperOS"
type = "action"
action = "reset"
[[entry]]
id = "xnu"
title = "Xiaomi Pad 6 (iPadOS 17.7.11)"
type = "xnu"
path = "Payloads/kernel.macho"
args = "-v native-ufs-root=1 native-ufs-root-part=ipados"
[[entry]]
id = "recovery"
title = "Recovery or Fastboot (hold Vol+ or Vol- while it restarts)"
type = "action"
action = "reset"
'''


def real_menu():
    try:
        from unixnu_payload_menu import build_menu
        return build_menu(WORK / 'UniXNU', WORK / 'UniXNU-pipa')['menu_text']
    except Exception:  # trees absent: the form above
        return SAFE_MENU


def image(menu, macho=b'\xcf\xfa\xed\xfe' + b'\0' * 60, shim_arm64=True, leave_out=()):
    shim = bytearray(4096)
    if shim_arm64:
        shim[56:60] = b'ARM\x64'
    files = {'EFI/UniXNU/unixnu.toml': menu.encode(), 'EFI/UniXNU/Payloads/kernel.macho': macho,
             'EFI/UniXNU/Payloads/kernel.macho.adt': b'ADT'}
    for name in leave_out:
        files.pop(name)
    return vb.build_v0(gzip.compress(bytes(shim) + b'FV' * 100, mtime=0), fatimage.build(files), page=2048,
                       kernel_addr=0x10008000)


def verdict(data):
    fields, problems = vb.check(data)
    more, menu = vb.check_unixnu(data, fields)
    return problems + more, menu


class UniXNUImage(unittest.TestCase):
    def test_fat_reader_long_names_and_content(self):
        fat = Fat(fatimage.build({'EFI/UniXNU/unixnu.toml': b'abc', 'a/b/c/long-name.macho': b'x' * 5000}))
        self.assertEqual(fat.kind, 32)
        self.assertEqual(fat.files(), {'EFI/UniXNU/unixnu.toml': 3, 'a/b/c/long-name.macho': 5000})
        self.assertEqual(fat.read('a/b/c/long-name.macho'), b'x' * 5000)

    def test_a_safe_image_passes(self):
        problems, menu = verdict(image(real_menu()))
        self.assertEqual(problems, [])
        self.assertEqual(menu['boot']['default'], 'android')

    def test_an_install_entry_inside_the_image_fails(self):
        bad = real_menu() + ('[[entry]]\nid = "install"\ntitle = "Install and boot"\nconfirm = "ERASE?"\n'
                             'confirm_titles = ["x"]\nconfirm_args = ["sheng-data-reset=1"]\ntype = "xnu"\n'
                             'path = "Payloads/kernel.macho"\nargs = "native-ufs-root=1 sheng-data-persist=2"\n')
        problems, _ = verdict(image(bad))
        self.assertTrue(any('sheng-data-reset' in p for p in problems), problems)
        self.assertTrue(any('sheng-data-persist=2' in p for p in problems), problems)

    def test_root_on_userdata_inside_the_image_fails(self):
        problems, _ = verdict(image(SAFE_MENU.replace(' native-ufs-root-part=ipados', '')))
        self.assertTrue(any("Android's userdata" in p for p in problems), problems)

    def test_structure(self):
        self.assertTrue(any('lacks EFI/UniXNU/Payloads/kernel.macho' in p
                            for p in verdict(image(SAFE_MENU, leave_out=['EFI/UniXNU/Payloads/kernel.macho']))[0]))
        self.assertTrue(any('Mach-O' in p for p in verdict(image(SAFE_MENU, macho=b'ELF!'))[0]))
        self.assertTrue(any('ARM64' in p for p in verdict(image(SAFE_MENU, shim_arm64=False))[0]))
        wrong = vb.build_v0(gzip.compress(b'x'), fatimage.build({'a': b'b'}), page=4096)
        self.assertTrue(any('uefi-pipa packs' in p for p in verdict(wrong)[0]))


if __name__ == '__main__':
    unittest.main()
