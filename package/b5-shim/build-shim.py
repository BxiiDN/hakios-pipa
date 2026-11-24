#!/usr/bin/env python3
"""Build the B5 entry shim as a flat, position-independent AArch64 binary (package/b5-shim, docs/MODE-B.md).

  build-shim.py --out shim.bin

Proof of position independence: the shim is linked at two different addresses and both flat binaries must be byte
identical; the descriptor offset (HKB5) is printed for tools/b5_compose.py.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLAGS = ['--target=aarch64-none-elf', '-O2', '-ffreestanding', '-fno-builtin', '-nostdlib', '-fno-stack-protector',
         '-fno-pic', '-mcmodel=tiny', '-mgeneral-regs-only', '-Wall', '-Wextra', '-Werror']


def tool(name):
    t = shutil.which(name)
    if not t:
        raise SystemExit(f'{name} not found')
    return t


def link(work, base):
    script = work / f'shim-{base:x}.ld'
    script.write_text(f"""ENTRY(shim_entry)
SECTIONS
{{
  . = 0x{base:x};
  .shim : {{ *(.text.entry) *(.text .text.*) *(.rodata .rodata.*) }}
  /DISCARD/ : {{ *(.comment) *(.note*) *(.eh_frame*) *(.data*) *(.bss*) }}
}}
""")
    elf = work / f'shim-{base:x}.elf'
    subprocess.run([tool('ld.lld'), '-static', '-nostdlib', '-T', script, work / 'entry.o', work / 'shim.o', '-o', elf],
                   check=True)
    out = work / f'shim-{base:x}.bin'
    subprocess.run([tool('llvm-objcopy'), '-O', 'binary', '--only-section=.shim', elf, out], check=True)
    return elf, out.read_bytes()


def build(out):
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        subprocess.run([tool('clang'), *FLAGS, '-c', HERE / 'entry.S', '-o', work / 'entry.o'], check=True)
        subprocess.run([tool('clang'), *FLAGS, '-c', HERE / 'shim.c', '-o', work / 'shim.o'], check=True)
        elf, a = link(work, 0)
        _, b = link(work, 0x7ff000)
        if a != b:
            raise SystemExit('the shim is not position independent: binaries linked at two addresses differ')
        relocs = subprocess.run([tool('llvm-readelf'), '-r', elf], capture_output=True, text=True).stdout
        if 'R_AARCH64' in relocs:
            raise SystemExit('the linked shim keeps relocations')
        desc = a.find(b'HKB5')
        if desc < 0 or desc % 8:
            raise SystemExit('no aligned HKB5 descriptor')
        Path(out).write_bytes(a)
        return len(a), desc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args(argv)
    size, desc = build(a.out)
    print(f'BUILT {a.out}: {size} bytes, position independent, HKB5 descriptor at 0x{desc:x}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
