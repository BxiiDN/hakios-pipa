"""tools/cmdline_budget.py, and the guards the Data initialisation relies on (patches/unixnu-pipa/0002, 0013)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import cmdline_budget as cb  # noqa: E402

BASE = 'native-ufs-root=1 native-ufs-root-part=ipados sheng-data-persist=2 ' + 'x' * 900


def fails(menu):
    return [t for level, t in cb.check(menu) if level == 'FAIL']


class Budget(unittest.TestCase):
    def test_fits_and_guards(self):
        menu = {'entry': [{'id': 'xnu', 'args': BASE},
                          {'id': 'install', 'args': BASE, 'confirm_args': ['sheng-data-reset=1', 'sheng-data-reset=2']}]}
        self.assertEqual(fails(menu), [])

    def test_too_long(self):
        menu = {'entry': [{'id': 'install', 'args': BASE + 'y' * 80, 'confirm_args': ['sheng-data-reset=1']}]}
        self.assertTrue(any('of 1023' in t for t in fails(menu)))

    def test_reset_on_userdata_or_without_persistence_fails(self):
        on_userdata = BASE.replace('native-ufs-root-part=ipados', 'native-ufs-root-part=userdata')
        self.assertTrue(fails({'entry': [{'id': 'i', 'args': on_userdata, 'confirm_args': ['sheng-data-reset=1']}]}))
        no_part = BASE.replace('native-ufs-root-part=ipados ', '')
        self.assertTrue(fails({'entry': [{'id': 'i', 'args': no_part, 'confirm_args': ['sheng-data-reset=1']}]}))
        volatile = BASE.replace('sheng-data-persist=2 ', '')
        self.assertTrue(fails({'entry': [{'id': 'i', 'args': volatile, 'confirm_args': ['sheng-data-reset=1']}]}))


class Guards(unittest.TestCase):
    def test_driver_refuses_a_store_on_userdata(self):
        p2 = (ROOT / 'patches/unixnu-pipa/0002-storage-isolate-root-from-android-userdata.patch').read_text()
        self.assertIn('+  else if (rootPartitionIsAndroidUserdata ()) reason = "refused: the root partition is Android\'s userdata";', p2)
        self.assertIn('+  "native-ufs-root-part=ipados",', p2)

    def test_0013_restores_persistence_and_the_install_entry(self):
        p13 = (ROOT / 'patches/unixnu-pipa/0013-ipados-data-persistent-and-one-time-initialisation.patch').read_text()
        self.assertIn('+  "sheng-data-persist=2",', p13)
        self.assertIn('+[payload.install]', p13)
        self.assertIn('+confirm_args = ["sheng-data-reset=1", "sheng-data-reset=2"]', p13)


if __name__ == '__main__':
    unittest.main()
