"""tools/memory_plan.py: free runs, the gap rule and the window fit; then the real pipa sources."""
import importlib.util
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('memory_plan', ROOT / 'tools/memory_plan.py')
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)
WORK = Path(os.environ.get('HAKIOS_WORK', ROOT.parent / 'hakios-work'))
FILES = (WORK / 'UniXNU-pipa/dts/pipa.dts', WORK / 'uefi-pipa/Platforms/Xiaomi/pipaPkg/Library/MemoryMapLib/MemoryMapLib.c',
         WORK / 'UniXNU-pipa/board.toml')
READY = all(f.is_file() for f in FILES) and shutil.which('dtc') is not None
if os.environ.get('HAKIOS_REQUIRE_INTEGRATION') == '1' and not READY:
    raise RuntimeError('pipa port / uefi-pipa trees or dtc missing')

BANKS = [(0x80000000, 0x3bb00000), (0xc0000000, 0x1c0000000)]


def region(name, base, size, kind='Reserv'):
    return dict(name=name, base=base, size=size, hob='AddMem', resource='MEM_RES', type=kind)


class Plan(unittest.TestCase):
    def kinds(self, result):
        return [k for k, _ in result['findings']]

    def test_fits_in_the_upper_bank(self):
        r = mp.plan(BANKS, [region('x', 0xffc00000, 0x20000)], 0x170000000)
        self.assertNotIn('FAIL', self.kinds(r))
        self.assertEqual(r['window_runs'], [('0xffe00000', '0x280000000')])   # aligned up past the reserved block
        self.assertEqual(r['gaps'], [('0xbbb00000', '0xc0000000')])

    def test_window_larger_than_any_run(self):
        r = mp.plan(BANKS, [region('x', 0x180000000, 0x1000)], 0x170000000)   # splits the upper bank
        self.assertIn('FAIL', self.kinds(r))

    def test_conventional_region_in_the_gap_fails(self):
        r = mp.plan(BANKS, [region('bad', 0xbc000000, 0x100000, 'Conv')], 0x10000000)
        self.assertTrue(any('gap' in t and k == 'FAIL' for k, t in r['findings']))

    def test_reserved_region_in_the_gap_is_only_noted(self):
        r = mp.plan(BANKS, [region('fw', 0xbc000000, 0x100000)], 0x10000000)
        self.assertNotIn('FAIL', self.kinds(r))
        self.assertIn('NOTE', self.kinds(r))

    def test_mmio_below_dram_ignored(self):
        r = mp.plan(BANKS, [region('regs', 0x0a600000, 0x11b000, 'MmIO')], 0x10000000)
        self.assertEqual(r['findings'], [])

    def test_parse_memory_map_entries(self):
        src = Path(self.id().replace('.', '_') + '.c')
        try:
            src.write_text('// {"Commented", 0x1, 0x1, AddMem, MEM_RES, UNCACHEABLE, Reserv, NS_DEVICE},\n'
                           '{"HYP", 0x80000000, 0x00600000, AddMem, SYS_MEM, SYS_MEM_CAP, Reserv, NS_DEVICE},\n'
                           '{"DXE Heap", 0x92F00000, 0x08D00000, AddMem, SYS_MEM, SYS_MEM_CAP, Conv,   WRITE_BACK_XN},\n')
            got = mp.fixed_regions(src)
        finally:
            src.unlink()
        self.assertEqual([(g['name'], g['base'], g['size'], g['type']) for g in got],
                         [('HYP', 0x80000000, 0x600000, 'Reserv'), ('DXE Heap', 0x92f00000, 0x8d00000, 'Conv')])


@unittest.skipUnless(READY, 'pipa port / uefi-pipa trees or dtc not available')
class RealPipa(unittest.TestCase):
    def test_pipa_sources_pass(self):
        dts, memory_map, board = FILES
        r = subprocess.run([sys.executable, ROOT / 'tools/memory_plan.py', '--dts', dts, '--dts-include',
                            WORK / 'UniXNU-pipa/socs/sm8250/dts', '--memory-map', memory_map, '--board', board],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("window_runs                    [('0xffe00000', '0x280000000')]", r.stdout)


if __name__ == '__main__':
    unittest.main()
