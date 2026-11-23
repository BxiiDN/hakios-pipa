#!/usr/bin/env python3
"""Where DarwinBoot can put the kernel's window on pipa, from the sources that decide it, offline.

Chain (each link read from source, see docs/MEMORY.md):
  1. DRAM banks: the hardware DTS memory nodes (measured on the 8 GB unit; the gap between them is the bootloader's).
  2. UEFI memory map: uefi-pipa pipaPkg MemoryMapLib.c gives the fixed regions; RamManagerDxe then adds, as
     EfiConventionalMemory, only the parts of the firmware's RAM partitions that no fixed region covers. A gap between
     RAM partitions is never added, so it can never be conventional memory.
  3. DarwinBoot AllocateWindow: the window (board.toml owned_memory_size) is AllocatePages(AllocateAddress) inside ONE run
     of contiguous EfiConventionalMemory descriptors, its start aligned to 2 MiB (+ the kernel's offset in a block);
     the kernel gets PhysicalBase = that address, MemorySize = the window (XNU gPhysBase/gPhysSize).
  4. XNU: gDramBase/gDramSize (ADT dram-base/size = the span) only pick a mapping attribute (is_dram_addr).

This computes the free runs that exist before any DXE driver allocates (an upper bound: what drivers take at boot is
only known at boot) and checks: no fixed region marks the gap as memory; every fixed region lies in a bank or below DRAM
(MMIO); the window fits in one run with its alignment; the window cannot reach the gap. Exit 1 on a violation.

  memory_plan.py --dts pipa.dts [--dts-include DIR] --memory-map MemoryMapLib.c --board board.toml [--json OUT]
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

BLOCK = 0x200000    # DarwinBoot BLOCK_SIZE
# MemoryMapLib.c entries: {"Name", Address, Length, HobOption, ResourceType, ResourceAttribute, MemoryType, ArmAttribute}
ENTRY = re.compile(r'\{\s*"([^"]+)"\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(0x[0-9A-Fa-f]+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,'
                   r'\s*(\w+)\s*,\s*(\w+)\s*\}')


def fixed_regions(source):
    text = re.sub(r'//[^\n]*', '', Path(source).read_text())
    return [dict(name=m[0], base=int(m[1], 16), size=int(m[2], 16), hob=m[3], resource=m[4], type=m[6])
            for m in ENTRY.findall(text)]


def dts_banks(dts, includes):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'hw.dtb'
        cmd = ['dtc', '-q', '-I', 'dts', '-O', 'dtb', '-o', str(out)]
        for d in includes:
            cmd += ['-i', str(d)]
        subprocess.run(cmd + [str(dts)], check=True)
        dts_out = subprocess.run(['dtc', '-q', '-I', 'dtb', '-O', 'dts', str(out)], capture_output=True, text=True,
                                 check=True).stdout
    banks = []
    for body in re.findall(r'memory@[0-9a-f]+\s*\{([^}]*)\}', dts_out):
        if 'device_type = "memory"' not in body or 'status = "disabled"' in body:
            continue
        cells = [int(x, 16) for x in re.search(r'reg = <([^>]*)>', body)[1].split()]
        for i in range(0, len(cells), 4):   # #address-cells = #size-cells = 2
            banks.append(((cells[i] << 32) | cells[i + 1], (cells[i + 2] << 32) | cells[i + 3]))
    return sorted(banks)


def subtract(runs, base, end):
    out = []
    for s, e in runs:
        if e <= base or end <= s:
            out.append((s, e))
            continue
        if s < base:
            out.append((s, base))
        if end < e:
            out.append((end, e))
    return out


def plan(banks, regions, window):
    findings = []
    gaps = [(a + sa, b) for (a, sa), (b, _) in zip(banks, banks[1:]) if a + sa < b]
    dram_lo, dram_hi = banks[0][0], banks[-1][0] + banks[-1][1]
    for r in regions:
        lo, hi = r['base'], r['base'] + r['size']
        in_bank = any(b <= lo and hi <= b + s for b, s in banks)
        if hi <= dram_lo:
            continue   # register blocks, IMEM: below DRAM
        if not in_bank:
            # a fixed region in a gap or across a bank boundary: fine only if it is not memory the OS may take
            kind = 'FAIL' if r['type'] in ('Conv', 'BsData', 'BsCode', 'LdData', 'LdCode') else 'NOTE'
            findings.append((kind, f"fixed region {r['name']} {lo:#x}..{hi:#x} ({r['type']}) is not inside one DRAM bank"))
        for g0, g1 in gaps:
            if lo < g1 and g0 < hi and r['type'] == 'Conv':
                findings.append(('FAIL', f"fixed region {r['name']} marks the gap {g0:#x}..{g1:#x} as conventional memory"))
    # Conventional memory before drivers allocate: each bank minus every fixed non-Conv region. Fixed Conv regions
    # (the DXE heap) are taken by the DXE core itself, so they count as used, not free, for the window.
    runs = [(b, b + s) for b, s in banks]
    for r in regions:
        runs = subtract(runs, r['base'], r['base'] + r['size'])
    runs = sorted(runs)
    placements = []
    for s, e in runs:
        start = (s + BLOCK - 1) & ~(BLOCK - 1)
        if start < e and e - start >= window:
            placements.append((start, e))
    if not placements:
        findings.append(('FAIL', f'no run of free memory holds the {window:#x} window (largest run '
                                 f'{max((e - s for s, e in runs), default=0):#x})'))
    for s, e in placements:
        # any 2 MiB-aligned window start inside this run stays inside it; check the run against the gaps
        for g0, g1 in gaps:
            if s < g1 and g0 < e:
                findings.append(('FAIL', f'run {s:#x}..{e:#x} overlaps the gap {g0:#x}..{g1:#x}'))
    slack = max((e - s - window for s, e in placements), default=None)
    return dict(banks=[(hex(b), hex(s)) for b, s in banks], gaps=[(hex(a), hex(b)) for a, b in gaps],
                span=(hex(dram_lo), hex(dram_hi - dram_lo)), total=hex(sum(s for _, s in banks)),
                window=hex(window), free_runs_before_drivers=[(hex(s), hex(e - s)) for s, e in runs if e - s >= 0x1000000],
                window_runs=[(hex(s), hex(e)) for s, e in placements],
                slack_for_driver_allocations=hex(slack) if slack is not None else None,
                findings=findings)


def main():
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('--dts', type=Path, required=True)
    a.add_argument('--dts-include', type=Path, action='append', default=[])
    a.add_argument('--memory-map', type=Path, required=True)
    a.add_argument('--board', type=Path, required=True)
    a.add_argument('--json', type=Path)
    args = a.parse_args()
    board = tomllib.loads(args.board.read_text())
    window = int(board['payload']['adt']['owned_memory_size'], 0)
    banks = dts_banks(args.dts, args.dts_include)
    result = plan(banks, fixed_regions(args.memory_map), window)
    span = int(result['span'][1], 16)
    for key in (('payload', 'dram_size'), ('payload', 'adt', 'dram_size')):
        value = board
        for k in key:
            value = value.get(k, {}) if isinstance(value, dict) else {}
        if value and int(value, 0) != span:
            result['findings'].append(('FAIL', f"board {'.'.join(key)} {value} is not the DTS span {span:#x}"))
    for k in ('banks', 'gaps', 'span', 'total', 'window', 'free_runs_before_drivers', 'window_runs',
              'slack_for_driver_allocations'):
        print(f'{k:30} {result[k]}')
    for kind, text in result['findings']:
        print(f'{kind}  {text}')
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + '\n')
    bad = any(kind == 'FAIL' for kind, _ in result['findings'])
    print('VERDICT', 'FAIL' if bad else 'PASS (offline; the driver allocations inside the run are known only at boot)')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
