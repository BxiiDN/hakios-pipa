"""Integration: the menu and kernel command line that UniXNU's own payload builder writes for the pipa board, with
hakios-pipa's patches applied (scripts/fetch-unixnu.sh), judged by tools/storage_safety.py. Needs the pinned trees in
$HAKIOS_WORK (default ../hakios-work); skipped without them. Not a test of the firmware on the tablet."""
import os
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
WORK = Path(os.environ.get('HAKIOS_WORK', ROOT.parent / 'hakios-work'))
UNIXNU, PORT = WORK / 'UniXNU', WORK / 'UniXNU-pipa'
READY = (UNIXNU / 'scripts/unixnu/dualboot.py').is_file() and (PORT / 'board.toml').is_file()
# scripts/build.sh sets this: there a missing tree is a failure, never a skip that reads as a pass
if os.environ.get('HAKIOS_REQUIRE_INTEGRATION') == '1' and not READY:
    raise RuntimeError(f'integration trees missing in {WORK}: run scripts/fetch-unixnu.sh')


@unittest.skipUnless(READY, f'pinned UniXNU trees with hakios-pipa patches not in {WORK}')
class RealPayloadMenu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from unixnu_payload_menu import build_menu
        import storage_safety
        cls.build_menu, cls.safety = staticmethod(build_menu), storage_safety
        cls.built = build_menu(UNIXNU, PORT)

    def test_safe_offline(self):
        verdict, hardware, findings = self.safety.judge(self.built)
        self.assertEqual(verdict, 'PASS', [f for f in findings if f[0] == 'FAIL'])
        self.assertIsNone(hardware)

    def test_menu_order_default_timeout(self):
        menu = self.built['menu']
        self.assertEqual([e['id'] for e in menu['entry']], ['android', 'xnu', 'recovery', 'reset', 'shutdown', 'tools'])
        self.assertEqual((menu['boot']['default'], menu['boot']['timeout']), ('android', 10))
        self.assertNotIn('confirm', ''.join(menu['entry'][0]))

    def test_kernel_arguments_are_the_boards_exactly(self):
        board_args = self.built['board']['payload']['kernel_args']
        self.assertEqual(self.built['kernel_args'], board_args)
        xnu = next(e for e in self.built['menu']['entry'] if e['id'] == 'xnu')
        self.assertEqual(xnu['args'].split(), board_args)
        self.assertNotIn('sheng-data-reset', xnu['args'])
        self.assertIn('native-ufs-root-part=ipados', board_args)

    def test_payload_files(self):
        self.assertIn('EFI/UniXNU/unixnu.toml', self.built['files'])
        self.assertIn('EFI/UniXNU/Payloads/kernel.macho', self.built['files'])
        self.assertIn('EFI/UniXNU/Payloads/kernel.macho.adt', self.built['files'])

    def test_a_dangerous_board_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = Path(tmp)
            text = (PORT / 'board.toml').read_text()
            text = text.replace('"native-ufs-root-part=ipados",\n', '"sheng-data-persist=2",\n')
            text = text.replace('[payload.dualboot]', '[payload.install]\ntitle = "Install and boot"\nconfirm = "ERASE?"\n'
                                'confirm_titles = ["a"]\nconfirm_args = ["sheng-data-reset=1"]\n\n[payload.dualboot]')
            (port / 'board.toml').write_text(text)
            verdict, _, findings = self.safety.judge(self.build_menu(UNIXNU, port))
        self.assertEqual(verdict, 'FAIL')
        reasons = ' '.join(t for level, t in findings if level == 'FAIL')
        for needle in ('data-reset', 'data-persist=2', "Android's userdata", 'install'):
            self.assertIn(needle, reasons)

    def test_both_spellings_are_refused(self):
        for bad in ('sheng-data-persist=2', 'data-persist=2', 'sheng-data-reset=1', 'data-reset=2', 'sheng-log=1', 'log=1'):
            menu = {'boot': {'default': 'android', 'timeout': 10}, 'entry': [
                {'id': 'android', 'type': 'action', 'action': 'reset'},
                {'id': 'xnu', 'type': 'xnu', 'args': f'native-ufs-root=1 native-ufs-root-part=ipados {bad}'},
                {'id': 'recovery', 'type': 'action', 'action': 'reset'}]}
            self.assertEqual(self.safety.judge({'menu': menu, 'board': {}})[0], 'FAIL', bad)

    def test_tablet_gpt(self):
        userdata = {'name': 'userdata', 'first_lba': 0x293000, 'last_lba': 0x3b037fa}
        without = [{'source': 'sda', 'partitions': [userdata]}]
        verdict, hardware, _ = self.safety.judge(self.built, without)
        self.assertEqual((verdict, hardware), ('PASS', 'BLOCKED'))
        clear = [{'source': 'sda', 'partitions': [dict(userdata, last_lba=0x2b00000),
                                                  {'name': 'ipados', 'first_lba': 0x2b00100, 'last_lba': 0x3b037fa}]}]
        self.assertEqual(self.safety.judge(self.built, clear)[1], 'PASS')
        overlap = [{'source': 'sda', 'partitions': [userdata, {'name': 'ipados', 'first_lba': 0x3b00000, 'last_lba': 0x3b037fa}]}]
        self.assertEqual(self.safety.judge(self.built, overlap)[1], 'FAIL')


if __name__ == '__main__':
    unittest.main()
