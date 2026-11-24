"""LUN 0 of the owner's Xiaomi Pad 6 as measured on 2026-11-24 (tests/data/pipa-lun0-layout.json): the GPT (read only) plugin's
result on the tablet, checked against what the repository already recorded, and what design A and B mean for this table."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import gpt_capacity  # noqa: E402
import pipa_gpt  # noqa: E402
from test_pipa_gpt import make_gpt  # noqa: E402

LAYOUT = json.loads((ROOT / 'tests/data/pipa-lun0-layout.json').read_text())
PARTS = LAYOUT['partitions']
DISK_LBAS = 241720 * 256              # plugin: "LUN 0: 241720 MiB" with 4096-byte blocks


def table():
    raw = make_gpt([(p['name'], p['first_lba'], p['last_lba'], 0) for p in PARTS], 4096, DISK_LBAS)
    return pipa_gpt.parse_gpt(raw, 'sda.bin')


class Measured(unittest.TestCase):
    def test_matches_the_plugin_and_board_toml(self):
        t = table()
        self.assertEqual((t['first_usable_lba'], t['last_usable_lba']), (6, 61880314))   # plugin "usable LBA 6..61880314"
        self.assertEqual(len(PARTS), 34)                                                  # plugin "34 partitions"
        userdata = PARTS[-1]
        self.assertEqual((userdata['name'], userdata['number']), ('userdata', 34))
        self.assertEqual((userdata['first_lba'], userdata['last_lba']), (0x293000, 0x3b037fa))   # board.toml [userdata]
        self.assertEqual(pipa_gpt.free_ranges(t), [])                                     # plugin "free 0 MiB"
        self.assertEqual(gpt_capacity.need() >> 20, 18240)                                # plugin "need 18240 MiB"

    def test_design_a_is_blocked_on_this_table(self):
        plan = json.loads((ROOT / 'plans/ipados-free-space.json').read_text())
        verdict, findings = pipa_gpt.check_plan(plan, [table()])
        self.assertEqual(verdict, 'BLOCKED')
        self.assertTrue(any('largest gap 0 MiB' in text for _, text in findings))

    def test_nothing_but_userdata_could_hold_the_root(self):
        need = gpt_capacity.need()
        android = {'super', 'userdata', 'metadata', 'persist', 'persistbak', 'misc', 'frp', 'keystore', 'devinfo',
                   'vbmeta_system_a', 'vbmeta_system_b', 'splash'}
        spare = sum(p['bytes'] for p in PARTS if p['name'] not in android)
        self.assertLess(spare, need // 10)            # every other partition together: under 2 GiB
        self.assertLess(next(p['bytes'] for p in PARTS if p['name'] == 'super'), need)

    def test_design_b_boundaries(self):
        # 20 GiB off userdata's end, 1 MiB aligned: what plans/ipados-shrink-userdata.json would write (not written)
        plan = json.loads((ROOT / 'plans/ipados-shrink-userdata.json').read_text())
        size = plan['create'][0]['size_mib'] * 256
        last = LAYOUT['last_usable_lba']
        ipados_first = (last + 1 - size) // 256 * 256
        self.assertEqual(ipados_first % 256, 0)
        self.assertGreaterEqual((last - ipados_first + 1) * 4096, gpt_capacity.need())
        userdata_last = ipados_first - 1
        self.assertEqual((ipados_first, userdata_last), (56637184, 56637183))
        self.assertGreater((userdata_last - 0x293000 + 1) * 4096, 220 * 10**9)   # Android keeps ~221 GB
        self.assertEqual(pipa_gpt.check_plan(plan, [table()])[0], 'FAIL')         # until both consents are given


if __name__ == '__main__':
    unittest.main()
