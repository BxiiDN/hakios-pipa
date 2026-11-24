"""tools/gpt_rewrite.py on the LUN 0 measured on 2026-11-24: the new GPT is sound, mirrors in the backup, has exactly the
planned boundaries, and differs from the original only in userdata's end, the new entry and the CRCs. Doubtful inputs
are refused. The tool has no device access at all."""
import re
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import gpt_rewrite as g  # noqa: E402
import pipa_gpt  # noqa: E402
from test_gpt_view import backup_of  # noqa: E402
from test_measured_lun0 import PARTS, DISK_LBAS  # noqa: E402
from test_pipa_gpt import make_gpt  # noqa: E402


def measured(parts=None):
    head = make_gpt([(p['name'], p['first_lba'], p['last_lba'], 0) for p in (parts or PARTS)], 4096, DISK_LBAS)
    head += b'\0' * (6 * 4096 - len(head))
    head = head[:0x1c2] + b'\xee' + head[0x1c3:]                       # protective MBR entry, as on the tablet
    tail = head[2 * 4096:6 * 4096] + backup_of(head, 4096, DISK_LBAS)
    return head, tail


class Rewrite(unittest.TestCase):
    def test_planned_layout(self):
        head, tail = measured()
        new_head, new_tail, diff = g.rewrite(head, tail)
        t = pipa_gpt.parse_gpt(new_head, 'new')
        parts = {p['name']: p for p in t['partitions']}
        self.assertEqual((parts['userdata']['first_lba'], parts['userdata']['last_lba']), (0x293000, 56637183))
        self.assertEqual((parts['ipados']['first_lba'], parts['ipados']['last_lba']), (56637184, 61880314))
        self.assertEqual(parts['ipados']['type'], str(g.APFS))
        self.assertEqual(diff['partitions_after'], diff['partitions_before'] + 1)
        self.assertEqual(diff['free_after'], [])
        old = {p['name']: (p['first_lba'], p['last_lba'], p['guid']) for p in pipa_gpt.parse_gpt(head, 'old')['partitions']}
        for name, v in old.items():
            if name != 'userdata':
                self.assertEqual((parts[name]['first_lba'], parts[name]['last_lba'], parts[name]['guid']), v, name)

    def test_only_planned_bytes_change(self):
        head, tail = measured()
        new_head, new_tail, diff = g.rewrite(head, tail)
        self.assertLessEqual(diff['head_bytes_changed'], 8 + 128 + 8)
        self.assertEqual(new_head[:4096], head[:4096])                       # protective MBR untouched
        # undoing the planned fields gives back the original exactly
        h = bytearray(new_head)
        h[4096 + 16:4096 + 20] = head[4096 + 16:4096 + 20]
        h[4096 + 88:4096 + 92] = head[4096 + 88:4096 + 92]
        slot, ud = diff['entry_slot'], next(i for i in range(128) if head[8192 + i * 128 + 56:8192 + i * 128 + 72] == 'userdata'.encode('utf-16-le'))
        h[8192 + ud * 128 + 40:8192 + ud * 128 + 48] = head[8192 + ud * 128 + 40:8192 + ud * 128 + 48]
        h[8192 + slot * 128:8192 + (slot + 1) * 128] = head[8192 + slot * 128:8192 + (slot + 1) * 128]
        self.assertEqual(bytes(h), head)

    def test_refusals(self):
        head, tail = measured()
        new_head, new_tail, _ = g.rewrite(head, tail)
        with self.assertRaisesRegex(g.RewriteError, 'exists already'):
            g.rewrite(new_head, new_tail)                                     # never twice
        bad = bytearray(tail)
        bad[100] ^= 1
        with self.assertRaisesRegex(g.RewriteError, 'original backup'):
            g.rewrite(head, bytes(bad))
        broken = bytearray(head)
        broken[8192 + 40] ^= 1
        with self.assertRaises(pipa_gpt.GptError):
            g.rewrite(bytes(broken), tail)
        with self.assertRaisesRegex(g.RewriteError, 'smaller than'):
            g.rewrite(head, tail, ipados_mib=1024)
        with self.assertRaisesRegex(g.RewriteError, 'less than'):
            g.rewrite(head, tail, min_userdata_gib=400)

    def test_abl_image_rules(self):
        head, tail = measured()
        new_head, new_tail, _ = g.rewrite(head, tail)
        both = new_head + new_tail
        self.assertEqual((both[510:512], both[0x1c2], both[4096:4104]), (b'\x55\xaa', 0xee, b'EFI PART'))
        self.assertGreater(len(both), 2 * 4096)
        no_mbr = head[:0x1c2] + b'\0' + head[0x1c3:]
        with self.assertRaisesRegex(g.RewriteError, 'protective MBR'):
            g.rewrite(no_mbr, tail)

    def test_userdata_must_be_last(self):
        parts = [dict(p) for p in PARTS]
        parts[-1], parts[-2] = dict(parts[-1], name='rescue'), dict(parts[-2], name='userdata')
        head, tail = measured(parts)
        with self.assertRaisesRegex(g.RewriteError, 'not the last'):
            g.rewrite(head, tail)

    def test_no_device_access_in_the_tool(self):
        code = (ROOT / 'tools/gpt_rewrite.py').read_text().split('"""', 2)[2]   # the code after the docstring
        self.assertNotRegex(code, r'subprocess|\badb\b|fastboot|/dev/|os\.system|socket|open\(')


if __name__ == '__main__':
    unittest.main()
