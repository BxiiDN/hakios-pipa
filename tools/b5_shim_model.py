#!/usr/bin/env python3
"""Reference model of the B5 entry shim (docs/MODE-B.md, B5): the decision it makes from the device tree ABL hands
over in x0, and the only change it may make to that tree. The assembly shim, when it is written, must behave exactly
like decide() on every case of tests/test_b5_shim_model.py. Nothing here boots or writes a device.

  b5_shim_model.py DTB --payload-addr ADDR --payload-bytes N [--out PATCHED.dtb]

Rules, fail-safe first (any doubt -> Android, i.e. branch to the stock Image's code unchanged):
  1. x0 is not a flattened device tree (magic, version >= 16, sizes inside totalsize)       -> android
  2. no /chosen or no /chosen/bootargs                                                       -> android
  3. bootargs has androidboot.mode=charger (off-mode charging)                               -> android
  4. bootargs has androidboot.force_normal_boot=1 (ABL's normal boot, LinuxLoader strings)   -> android
  5. otherwise ABL booted the boot partition for recovery (Vol+ held, `reboot recovery`, BCB): the menu. The shim then
     needs /chosen linux,initrd-start and linux,initrd-end, each 4 or 8 bytes, and a payload whose length is a whole
     number of 512-byte sectors (ShengBootMemoryDxe RAM_BLOCK_SIZE); if any is missing                   -> android
     else it overwrites the two values in place (same lengths: the tree's size never changes) with the payload's
     address and end, and enters BootShim with x0 unchanged                                             -> menu
Consequence, recorded in docs/MODE-B.md: with B5 installed, stock recovery is reached only through the menu's
Android-recovery entry, which needs the return-to-Linux path (not written) -- or by restoring the stock boot image
from fastboot, which ABL keeps in its own partition.
"""
import argparse
import struct
import sys
from pathlib import Path

FDT_MAGIC = 0xd00dfeed
BEGIN_NODE, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9
SECTOR = 512


def header(dtb):
    if len(dtb) < 40:
        return None
    magic, total, off_struct, off_strings, _, version, _, _, size_strings, size_struct = struct.unpack_from('>10I', dtb, 0)
    if magic != FDT_MAGIC or version < 16 or total > len(dtb):
        return None
    if off_struct + size_struct > total or off_strings + size_strings > total:
        return None
    return off_struct, size_struct, off_strings, size_strings


def chosen_props(dtb):
    """{name: (offset of the value, length)} of the properties directly under /chosen, or None if the tree is bad."""
    h = header(dtb)
    if h is None:
        return None
    off_struct, size_struct, off_strings, size_strings = h
    i, end, path, props = off_struct, off_struct + size_struct, [], {}
    try:
        while i < end:
            token = struct.unpack_from('>I', dtb, i)[0]
            i += 4
            if token == BEGIN_NODE:
                z = dtb.index(b'\0', i)
                path.append(dtb[i:z].decode('ascii', 'replace'))
                i = (z + 1 + 3) & ~3
            elif token == END_NODE:
                if not path:
                    return None
                path.pop()
            elif token == PROP:
                length, nameoff = struct.unpack_from('>II', dtb, i)
                i += 8
                if nameoff >= size_strings or i + length > end:
                    return None
                z = dtb.index(b'\0', off_strings + nameoff)
                name = dtb[off_strings + nameoff:z].decode('ascii', 'replace')
                if path == ['', 'chosen']:
                    props[name] = (i, length)
                i = (i + length + 3) & ~3
            elif token == NOP:
                continue
            elif token == END:
                return props
            else:
                return None
    except (ValueError, struct.error):
        return None
    return None


def decide(dtb, payload_addr, payload_bytes):
    """('android', reason, None) or ('menu', reason, patched tree bytes)."""
    props = chosen_props(dtb)
    if props is None:
        return 'android', 'x0 is not a valid device tree', None
    if 'bootargs' not in props:
        return 'android', 'no /chosen/bootargs', None
    off, length = props['bootargs']
    args = dtb[off:off + length].rstrip(b'\0').split()
    if b'androidboot.mode=charger' in args:
        return 'android', 'off-mode charging', None
    if b'androidboot.force_normal_boot=1' in args:
        return 'android', 'normal boot', None
    if payload_bytes == 0 or payload_bytes % SECTOR:
        return 'android', 'payload is not a whole number of sectors', None
    new = bytearray(dtb)
    for name, value in (('linux,initrd-start', payload_addr), ('linux,initrd-end', payload_addr + payload_bytes)):
        if name not in props or props[name][1] not in (4, 8):
            return 'android', f'no usable /chosen/{name}', None
        off, length = props[name]
        if length == 4:
            if value >> 32:
                return 'android', f'{name} cannot hold {value:#x} in 32 bits', None
            struct.pack_into('>I', new, off, value)
        else:
            struct.pack_into('>Q', new, off, value)
    return 'menu', 'recovery boot: the menu, initrd = the payload', bytes(new)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dtb', type=Path)
    ap.add_argument('--payload-addr', type=lambda v: int(v, 0), required=True)
    ap.add_argument('--payload-bytes', type=lambda v: int(v, 0), required=True)
    ap.add_argument('--out', type=Path)
    a = ap.parse_args(argv)
    path, reason, patched = decide(a.dtb.read_bytes(), a.payload_addr, a.payload_bytes)
    print(f'{path.upper()}: {reason}')
    if patched is not None and a.out:
        a.out.write_bytes(patched)
    return 0


if __name__ == '__main__':
    sys.exit(main())
