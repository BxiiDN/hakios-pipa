"""The ADT DRAM handoff (patch unixnu 0006, UniXNU scripts/unixnu/devicetree.py dram_span/generate).

Unit: DRAM banks from a hardware DTS become /chosen dram-base = first base, dram-size = span; overlapping, empty or
missing banks are refused; an owned window larger than every bank is refused. Integration: the real pipa DTS (two banks
around the bootloader's 0xbbb00000..0xc0000000 hole) compiled with dtc gives the span board.toml declares, and the
owned window fits in one bank. Needs the pinned UniXNU tree with hakios-pipa's patches ($HAKIOS_WORK) and dtc."""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get('HAKIOS_WORK', ROOT.parent / 'hakios-work'))
UNIXNU, PORT = WORK / 'UniXNU', WORK / 'UniXNU-pipa'
READY = (UNIXNU / 'scripts/unixnu/devicetree.py').is_file() and shutil.which('dtc') is not None
if os.environ.get('HAKIOS_REQUIRE_INTEGRATION') == '1' and not READY:
    raise RuntimeError(f'integration trees or dtc missing ({WORK})')
if READY:
    sys.path.insert(0, str(UNIXNU / 'scripts'))
    from unixnu import devicetree as dt   # noqa: E402
    from unixnu.util import Error         # noqa: E402

CPUS = '''cpus { #address-cells = <2>; #size-cells = <0>; timebase-frequency = <19200000>;
          cpu@0 { device_type = "cpu"; compatible = "arm,cortex-a55"; reg = <0 0>; }; };'''


def dtb(memory, tmp):
    src = Path(tmp) / 't.dts'
    src.write_text('/dts-v1/;\n/ { compatible = "t,t"; model = "t"; #address-cells = <2>; #size-cells = <2>;\n'
                   + CPUS + memory + '\n};\n')
    out = Path(tmp) / 't.dtb'
    subprocess.run(['dtc', '-q', '-I', 'dts', '-O', 'dtb', '-o', out, src], check=True)
    return out


def bank(base, size, name=None):
    return (f'memory@{base:x} {{ device_type = "memory"; reg = <{base >> 32:#x} {base & 0xffffffff:#x} '
            f'{size >> 32:#x} {size & 0xffffffff:#x}>; }};')


def chosen(adt):
    """/chosen properties of a flat ADT (node: <u32 nprops><u32 nchildren>, props <char[32]><u32 len> data pad4)."""
    def walk(at):
        nprops, nchildren = struct.unpack_from('<II', adt, at)
        at += 8
        props = {}
        for _ in range(nprops):
            key, length = struct.unpack_from('<32sI', adt, at)
            at += 36
            props[key.rstrip(b'\0').decode()] = adt[at:at + length]
            at += length + (-length % 4)
        kids = []
        for _ in range(nchildren):
            child, at = walk(at)
            kids.append(child)
        return (props, kids), at
    (props, kids), end = walk(0)
    assert end == len(adt)
    return next(p for p, _ in kids if p['name'] == b'chosen\0')


def u64(b):
    return struct.unpack('<Q', b)[0]


@unittest.skipUnless(READY, f'pinned UniXNU tree with hakios-pipa patches, or dtc, not available ({WORK})')
class DramSpan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def gen(self, memory, payload=None):
        return dt.generate(dtb(memory, self.tmp), {'payload': payload or {}, 'adt': {}})

    def test_single_bank_unchanged(self):
        c = chosen(self.gen(bank(0x80000000, 0x40000000)))
        self.assertEqual((u64(c['dram-base']), u64(c['dram-size'])), (0x80000000, 0x40000000))

    def test_two_banks_give_the_span(self):
        c = chosen(self.gen(bank(0xc0000000, 0x1c0000000) + bank(0x80000000, 0x3bb00000)))   # unsorted in the DTS
        self.assertEqual((u64(c['dram-base']), u64(c['dram-size'])), (0x80000000, 0x200000000))

    def test_overlap_refused(self):
        with self.assertRaisesRegex(Error, 'overlap'):
            self.gen(bank(0x80000000, 0x40000000) + bank(0xa0000000, 0x40000000))

    def test_no_memory_refused(self):
        with self.assertRaisesRegex(Error, 'DRAM range'):
            self.gen('')

    def test_payload_dram_size_must_be_the_span(self):
        with self.assertRaisesRegex(Error, 'differs'):
            self.gen(bank(0x80000000, 0x3bb00000) + bank(0xc0000000, 0x1c0000000), {'dram_size': '0x1fbb00000'})

    def test_window_larger_than_every_bank_refused(self):
        # 0x1c0000000 is the larger bank; the span (0x200000000) would hold this window, one bank does not
        with self.assertRaisesRegex(Error, 'larger than every DRAM bank'):
            self.gen(bank(0x80000000, 0x3bb00000) + bank(0xc0000000, 0x1c0000000),
                     {'adt': {'owned_memory_size': '0x1e0000000'}})

    def test_window_in_one_bank_accepted(self):
        c = chosen(self.gen(bank(0x80000000, 0x3bb00000) + bank(0xc0000000, 0x1c0000000),
                            {'adt': {'owned_memory_size': '0x170000000'}}))
        self.assertEqual(u64(c['darwinboot-memory-size']), 0x170000000)


@unittest.skipUnless(READY and (PORT / 'dts/pipa.dts').is_file(), 'pipa port tree not available')
class PipaBoard(unittest.TestCase):
    def test_real_pipa_dts(self):
        board = tomllib.loads((PORT / 'board.toml').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'pipa.dtb'
            subprocess.run(['dtc', '-q', '-I', 'dts', '-O', 'dtb', '-o', out, '-i', PORT / 'socs/sm8250/dts',
                            PORT / 'dts/pipa.dts'], check=True)
            root = dt.read_fdt(out.read_bytes())
            base, span, banks = dt.dram_span(root)
        self.assertEqual(banks, [(0x80000000, 0x3bb00000), (0xc0000000, 0x1c0000000)])
        self.assertEqual((base, span), (0x80000000, 0x200000000))
        self.assertEqual(int(board['payload']['dram_size'], 0), span)
        owned = int(board['payload']['adt']['owned_memory_size'], 0)
        self.assertLessEqual(owned, max(s for _, s in banks))
        # the hole is in the span and in no bank
        hole = (0xbbb00000, 0xc0000000)
        self.assertTrue(base <= hole[0] and hole[1] <= base + span)
        self.assertFalse(any(b < hole[1] and hole[0] < b + s for b, s in banks))


if __name__ == '__main__':
    unittest.main()
