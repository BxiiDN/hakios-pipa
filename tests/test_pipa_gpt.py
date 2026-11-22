"""Tests of tools/pipa_gpt.py on GPTs built here, byte for byte, with valid CRCs. No device, no real dump."""
import json
import struct
import sys
import tempfile
import unittest
import uuid
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import pipa_gpt  # noqa: E402

LINUX_DATA = uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4')
MIB_4K = 256  # 4096-byte sectors in a MiB
TOTAL = 62_000_000  # LBAs: about 254 GB of 4096-byte sectors, the size of a 256 GB LUN


def make_gpt(parts, sector=4096, total_lbas=TOTAL, entries=128):
    """parts: (name, first, last, attributes). Returns the bytes of LBA 0 .. end of the entry array."""
    table = bytearray(entries * 128)
    for i, (name, first, last, attrs) in enumerate(parts):
        entry = (LINUX_DATA.bytes_le + uuid.uuid4().bytes_le + struct.pack('<QQQ', first, last, attrs) +
                 name.encode('utf-16-le').ljust(72, b'\0'))
        table[i * 128:(i + 1) * 128] = entry
    entries_lba = 2
    entry_sectors = -(-len(table) // sector)
    first_usable = entries_lba + entry_sectors
    header = bytearray(struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 0x10000, 92, 0, 0, 1, total_lbas - 1,
                                   first_usable, total_lbas - 1 - entry_sectors - 1, uuid.uuid4().bytes_le,
                                   entries_lba, entries, 128, zlib.crc32(bytes(table)) & 0xffffffff))
    struct.pack_into('<I', header, 16, zlib.crc32(bytes(header)) & 0xffffffff)
    data = bytearray(sector * entries_lba + len(table))
    data[510:512] = b'\x55\xaa'
    data[sector:sector + 92] = header
    data[sector * entries_lba:] = table
    return bytes(data)


A_ACTIVE = pipa_gpt.ATTR_ACTIVE | pipa_gpt.ATTR_SUCCESSFUL


def stock(free_tail=True):
    """A made-up layout shaped like a Qualcomm A/B tablet: not pipa's real one (that is read from the tablet)."""
    parts, lba = [], 6
    for name, mib, attrs in (('xbl_a', 8, 0), ('abl_a', 8, 0), ('boot_a', 96, A_ACTIVE), ('boot_b', 96, 0),
                             ('vendor_boot_a', 96, 0), ('vendor_boot_b', 96, 0), ('vbmeta_a', 1, 0),
                             ('persist', 64, 0), ('super', 9000, 0), ('metadata', 16, 0)):
        parts.append((name, lba, lba + mib * MIB_4K - 1, attrs))
        lba += mib * MIB_4K
    last = TOTAL - 6  # the last usable LBA: before the backup header and its four sectors of entries
    end = last - (4096 * MIB_4K if free_tail else 0)
    parts.append(('userdata', lba, end, 0))
    return parts


class Tables(unittest.TestCase):
    def tables(self, parts=None):
        return [pipa_gpt.parse_gpt(make_gpt(parts or stock()), 'sda')]

    def test_reads_names_slots_and_sector_size(self):
        table = self.tables()[0]
        self.assertEqual(table['sector_size'], 4096)
        self.assertIn('userdata', [p['name'] for p in table['partitions']])
        self.assertEqual(pipa_gpt.active_slot([table]), 'a')

    def test_512_byte_sectors(self):
        table = pipa_gpt.parse_gpt(make_gpt([('boot_a', 40, 100, A_ACTIVE)], sector=512), 'x')
        self.assertEqual(table['sector_size'], 512)

    def test_damaged_header_and_entries_are_refused(self):
        data = bytearray(make_gpt(stock()))
        data[4096 + 40] ^= 1
        with self.assertRaisesRegex(pipa_gpt.GptError, 'header CRC32'):
            pipa_gpt.parse_gpt(bytes(data))
        data = bytearray(make_gpt(stock()))
        data[2 * 4096 + 60] ^= 1
        with self.assertRaisesRegex(pipa_gpt.GptError, 'entries CRC32'):
            pipa_gpt.parse_gpt(bytes(data))
        with self.assertRaisesRegex(pipa_gpt.GptError, 'no GPT header'):
            pipa_gpt.parse_gpt(b'\0' * 9000)

    def verdict(self, plan, parts=None):
        return pipa_gpt.check_plan(plan, self.tables(parts))

    def test_ram_boot_writes_nothing_and_passes(self):
        self.assertEqual(self.verdict({'mode': 'ram-boot'})[0], 'PASS')
        self.assertEqual(self.verdict({'mode': 'ram-boot', 'writes': [{'partition': 'boot_a'}]})[0], 'FAIL')

    def test_firmware_and_android_partitions_are_never_written(self):
        for name in ('xbl_a', 'abl_a', 'persist', 'super', 'userdata', 'vbmeta_a', 'vendor_boot_a'):
            verdict, _ = self.verdict({'mode': 'flash', 'writes': [{'partition': name, 'backup_sha256': 'x' * 64}],
                                       'android_fallback_tested': True})
            self.assertEqual(verdict, 'FAIL', name)

    def test_inactive_slot_is_refused(self):
        verdict, findings = self.verdict({'mode': 'flash', 'android_fallback_tested': True,
                                          'writes': [{'partition': 'boot_b', 'backup_sha256': 'x' * 64}]})
        self.assertEqual(verdict, 'FAIL')
        self.assertTrue(any('next OTA' in text for _, text in findings))

    def test_active_boot_needs_backup_then_a_tested_fallback(self):
        self.assertEqual(self.verdict({'mode': 'flash', 'writes': [{'partition': 'boot_a'}]})[0], 'FAIL')
        self.assertEqual(self.verdict({'mode': 'flash',
                                       'writes': [{'partition': 'boot_a', 'backup_sha256': 'a' * 64}]})[0], 'BLOCKED')
        self.assertEqual(self.verdict({'mode': 'flash', 'android_fallback_tested': True,
                                       'writes': [{'partition': 'boot_a', 'backup_sha256': 'a' * 64}]})[0], 'PASS')

    def test_unknown_slot_blocks_boot_plans(self):
        parts = [(n, f, l, 0) for n, f, l, _ in stock()]
        self.assertEqual(self.verdict({'mode': 'ram-boot'}, parts)[0], 'BLOCKED')

    def test_new_partition_in_free_space_is_aligned(self):
        plan = {'mode': 'partition', 'create': [{'name': 'hakios', 'size_mib': 2048, 'lun': 'sda'}]}
        verdict, findings = self.verdict(plan)
        self.assertEqual(verdict, 'PASS', findings)
        first = plan['create'][0]['_fit'][0]
        self.assertEqual(first % MIB_4K, 0)
        layout = pipa_gpt.simulate(plan, self.tables())
        self.assertIn('hakios', [p['name'] for p in layout[0]['partitions']])

    def test_no_room_without_shrinking_userdata_blocks(self):
        plan = {'mode': 'partition', 'create': [{'name': 'hakios', 'size_mib': 2048}]}
        verdict, findings = self.verdict(plan, stock(free_tail=False))
        self.assertEqual(verdict, 'BLOCKED')
        self.assertTrue(any('erases' in text for _, text in findings))

    def test_userdata_resize_needs_both_consents(self):
        plan = {'mode': 'partition', 'resize': [{'partition': 'userdata', 'size_mib': 100000}]}
        self.assertEqual(self.verdict(plan)[0], 'FAIL')
        plan.update(userdata_erase_confirmed=True)
        self.assertEqual(self.verdict(plan)[0], 'FAIL')
        plan.update(backup_verified=True)
        self.assertEqual(self.verdict(plan)[0], 'PASS')
        self.assertEqual(self.verdict({'resize': [{'partition': 'super'}], 'mode': 'x'})[0], 'FAIL')

    def test_overlap_is_found(self):
        parts = stock()
        name, first, last, attrs = parts[1]
        parts[1] = (name, first - 10, last, attrs)
        self.assertEqual(self.verdict({'mode': 'ram-boot'}, parts)[0], 'FAIL')

    def test_command_line_read_then_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump, plan, as_json = Path(tmp, 'sda.bin'), Path(tmp, 'plan.json'), Path(tmp, 'sda.json')
            dump.write_bytes(make_gpt(stock()))
            plan.write_text(json.dumps({'mode': 'ram-boot'}))
            self.assertEqual(pipa_gpt.main(['check', str(plan), str(dump)]), 0)
            import contextlib
            import io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                pipa_gpt.main(['read', str(dump)])
            as_json.write_text(out.getvalue())
            self.assertEqual(pipa_gpt.main(['check', str(plan), str(as_json)]), 0)
            plan.write_text(json.dumps({'mode': 'flash', 'writes': [{'partition': 'xbl_a'}]}))
            self.assertEqual(pipa_gpt.main(['check', str(plan), str(dump)]), 1)


if __name__ == '__main__':
    unittest.main()
