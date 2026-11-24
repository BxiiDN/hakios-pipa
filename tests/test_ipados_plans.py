"""plans/ipados-*.json, checked by tools/pipa_gpt.py on synthetic LUN 0 tables: design A passes only where free space exists;
design B (shrinking userdata) fails until the owner sets both consents, and the committed file must keep them false."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import gpt_capacity  # noqa: E402
import pipa_gpt  # noqa: E402
from test_pipa_gpt import make_gpt, stock  # noqa: E402

A = json.loads((ROOT / 'plans/ipados-free-space.json').read_text())
B = json.loads((ROOT / 'plans/ipados-shrink-userdata.json').read_text())


def table(free_gib):
    parts = stock(free_tail=False)
    name, first, last, attrs = parts[-1]
    parts[-1] = (name, first, last - free_gib * 1024 * 256, attrs)
    return pipa_gpt.parse_gpt(make_gpt(parts), 'sda.bin')


class Plans(unittest.TestCase):
    def test_size_covers_the_minimum(self):
        for plan in (A, B):
            self.assertGreaterEqual(plan['create'][0]['size_mib'] << 20, gpt_capacity.need())
            self.assertEqual(plan['create'][0]['name'], 'ipados')       # board.toml native-ufs-root-part=ipados

    def test_design_a_needs_free_space(self):
        self.assertEqual(pipa_gpt.check_plan(json.loads(json.dumps(A)), [table(0)])[0], 'BLOCKED')
        self.assertEqual(pipa_gpt.check_plan(json.loads(json.dumps(A)), [table(19)])[0], 'BLOCKED')
        self.assertEqual(pipa_gpt.check_plan(json.loads(json.dumps(A)), [table(24)])[0], 'PASS')

    def test_design_a_never_resizes_or_writes(self):
        self.assertNotIn('resize', A)
        self.assertNotIn('writes', A)

    def test_design_b_fails_without_both_consents(self):
        self.assertIs(B['userdata_erase_confirmed'], False)
        self.assertIs(B['backup_verified'], False)
        self.assertEqual(pipa_gpt.check_plan(json.loads(json.dumps(B)), [table(0)])[0], 'FAIL')
        one = dict(json.loads(json.dumps(B)), userdata_erase_confirmed=True)
        self.assertEqual(pipa_gpt.check_plan(one, [table(0)])[0], 'FAIL')


if __name__ == '__main__':
    unittest.main()
