"""tools/gpt_capacity.py: the ipados size rule, and the report over a GPT reader LOG.BIN built here from synthetic LUNs
(primary and backup GPT); the GPT reader's init only records, so these fixtures are what the host sees."""
import struct
import sys
import unittest
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import gpt_capacity  # noqa: E402
from test_pipa_gpt import make_gpt, LINUX_DATA  # noqa: E402

SECTOR = 4096


def disk(parts, lbas):
    """(head = first 6 sectors, tail = last 5 sectors) of a disk of LBAS sectors with PARTS."""
    head = bytearray(make_gpt(parts, SECTOR, lbas))
    head += b'\0' * (6 * SECTOR - len(head))
    hdr = bytearray(head[SECTOR:SECTOR + 92])
    table = bytes(head[2 * SECTOR:6 * SECTOR])
    # the backup: header in the last LBA, its entries in the 4 before it, current/backup swapped
    struct.pack_into('<QQ', hdr, 24, lbas - 1, 1)
    struct.pack_into('<Q', hdr, 72, lbas - 5)
    struct.pack_into('<I', hdr, 16, 0)
    struct.pack_into('<I', hdr, 16, zlib.crc32(bytes(hdr)) & 0xffffffff)
    tail = bytearray(table) + bytes(hdr).ljust(SECTOR, b'\0')
    return bytes(head), bytes(tail)


def log(disks):
    out = bytearray()
    for name, (size, head, tail) in disks.items():
        for kind, data in (('info', f'bytes={size} sector={SECTOR}\n'.encode()), ('head', head), ('tail', tail)):
            h = bytearray(64)
            h[:8] = b'UXFILE01'
            struct.pack_into('<q', h, 8, len(data))
            h[16:16 + len(f'gpt/{name}.{kind}')] = f'gpt/{name}.{kind}'.encode()
            out += h + data + b'\0' * (-len(data) % 8)
    return bytes(out) + b'UXEND000'


LBAS = 62_000_000


def lun0(free_mib=0):
    last_usable = LBAS - 6
    end = last_usable - free_mib * 256
    return [('metadata', 6, 6 + 4095, 0), ('super', 4102, 4102 + 9000 * 256 - 1, 0), ('userdata', 4102 + 9000 * 256, end, 0)]


class Need(unittest.TestCase):
    def test_minimum_for_the_8_gib_seed(self):
        self.assertEqual(gpt_capacity.need(), 19_126_026_240)
        self.assertEqual(gpt_capacity.window_blocks(2_097_152), 2_097_217)      # the window session 1 read on the tablet


class Report(unittest.TestCase):
    def run_report(self, parts, lbas=LBAS, tamper=None, need=gpt_capacity.need()):
        head, tail = disk(parts, lbas)
        if tamper:
            head, tail = tamper(head, tail)
        return gpt_capacity.report(log({'sda': (lbas * SECTOR, head, tail)}), need_bytes=need)[0]

    def test_userdata_to_the_end_leaves_no_room(self):
        r = self.run_report(lun0())
        self.assertEqual(r['problems'], [])
        self.assertEqual((r['free_bytes'], r['fits'], r['last_partition']), (0, False, 'userdata'))

    def test_free_tail_is_measured(self):
        r = self.run_report(lun0(free_mib=20 * 1024))
        self.assertEqual(r['problems'], [])
        self.assertEqual(r['largest_free'], 20 * 1024 * 1024 * 1024)
        self.assertTrue(r['fits'])

    def test_damaged_backup_is_reported(self):
        def flip(head, tail):
            t = bytearray(tail)
            t[100] ^= 1                                   # inside the backup entries
            return head, bytes(t)
        r = self.run_report(lun0(), tamper=flip)
        self.assertTrue(any('backup entries' in p for p in r['problems']))

    def test_disk_size_other_than_the_header_says_is_reported(self):
        head, tail = disk(lun0(), LBAS)
        r = gpt_capacity.report(log({'sda': ((LBAS + 8) * SECTOR, head, tail)}))[0]
        self.assertTrue(any('disk ends at' in p for p in r['problems']))

    def test_missing_record_is_a_problem(self):
        head, tail = disk(lun0(), LBAS)
        blob = log({'sda': (LBAS * SECTOR, head, tail)}).replace(b'gpt/sda.tail', b'gpt/sdz.junk')
        r = gpt_capacity.report(blob)
        self.assertTrue(any(e['problems'] for e in r))


if __name__ == '__main__':
    unittest.main()
