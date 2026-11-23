#!/usr/bin/env python3
"""Structural fingerprint of a Mach-O (or fileset) kernel, to find which parts of two builds differ.

  macho_fingerprint.py KERNEL [--out FP.json]        per-segment and per-section sha256, LC_UUID, build/source
                                                     version, and the Darwin/XNU version strings it embeds
  macho_fingerprint.py --compare A.json B.json       which segments, sections and strings differ

The kernels themselves stay private (they carry Apple's kexts); fingerprints hold only digests and the kernel's own
version strings, so two runs can be compared through their logs.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

LC_SEGMENT_64, LC_UUID, LC_SOURCE_VERSION, LC_BUILD_VERSION, LC_FILESET_ENTRY = 0x19, 0x1b, 0x2a, 0x32, 0x80000035
VERSION = re.compile(rb'(Darwin Kernel Version [^\x00]{0,200}|xnu-[0-9][0-9.~]*[^\x00]{0,120}|@\(#\)VERSION:[^\x00]{0,200})')


def fingerprint(data):
    magic, cpu, subtype, filetype, ncmds, sizeofcmds = struct.unpack_from('<6I', data)
    if magic != 0xfeedfacf:
        raise SystemExit('not a 64-bit little-endian Mach-O')
    fp = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'cpu': hex(cpu), 'filetype': filetype,
          'load_commands_sha256': hashlib.sha256(data[32:32 + sizeofcmds]).hexdigest(),
          'segments': {}, 'sections': {}, 'uuid': None, 'fileset_entries': 0}
    at = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<2I', data, at)
        if cmd == LC_SEGMENT_64:
            name = data[at + 8:at + 24].rstrip(b'\0').decode('latin1')
            va, vmsize, fileoff, filesize, _, _, nsects, _ = struct.unpack_from('<4Q4I', data, at + 24)
            key = f'{name}@{va:#x}'
            fp['segments'][key] = {'fileoff': fileoff, 'filesize': filesize,
                                   'sha256': hashlib.sha256(data[fileoff:fileoff + filesize]).hexdigest()}
            for i in range(nsects):
                s = at + 72 + 80 * i
                sect = data[s:s + 16].rstrip(b'\0').decode('latin1')
                addr, ssize, off = struct.unpack_from('<2QI', data, s + 32)
                flags = struct.unpack_from('<I', data, s + 64)[0]
                zerofill = flags & 0xff in (0x1, 0xc, 0x12)
                fp['sections'][f'{name},{sect}@{addr:#x}'] = {
                    'size': ssize, 'sha256': None if zerofill else hashlib.sha256(data[off:off + ssize]).hexdigest()}
        elif cmd == LC_UUID:
            fp['uuid'] = data[at + 8:at + 24].hex()
        elif cmd == LC_SOURCE_VERSION:
            fp['source_version'] = struct.unpack_from('<Q', data, at + 8)[0]
        elif cmd == LC_BUILD_VERSION:
            platform, minos, sdk = struct.unpack_from('<3I', data, at + 8)
            fp['build_version'] = {'platform': platform, 'minos': hex(minos), 'sdk': hex(sdk)}
        elif cmd == LC_FILESET_ENTRY:
            fp['fileset_entries'] += 1
        at += size
    fp['version_strings'] = sorted({m.group(0).decode('latin1', 'replace') for m in VERSION.finditer(data)})[:40]
    return fp


def compare(a, b):
    lines = []
    for key in ('bytes', 'sha256', 'uuid', 'load_commands_sha256', 'source_version', 'build_version', 'fileset_entries'):
        if a.get(key) != b.get(key):
            lines.append(f'DIFF {key}: {a.get(key)} != {b.get(key)}')
    for kind in ('segments', 'sections'):
        for name in sorted(set(a[kind]) | set(b[kind])):
            x, y = a[kind].get(name), b[kind].get(name)
            if x is None or y is None:
                lines.append(f'DIFF {kind[:-1]} {name}: only in {"B" if x is None else "A"}')
            elif x != y:
                lines.append(f'DIFF {kind[:-1]} {name}: {json.dumps(x)} != {json.dumps(y)}')
    only_a = sorted(set(a['version_strings']) - set(b['version_strings']))
    only_b = sorted(set(b['version_strings']) - set(a['version_strings']))
    for s in only_a:
        lines.append(f'DIFF string only in A: {s!r}')
    for s in only_b:
        lines.append(f'DIFF string only in B: {s!r}')
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('kernel', nargs='?')
    p.add_argument('--out')
    p.add_argument('--compare', nargs=2, metavar=('A', 'B'))
    args = p.parse_args(argv)
    if args.compare:
        a, b = (json.loads(Path(f).read_text()) for f in args.compare)
        lines = compare(a, b)
        print('\n'.join(lines) if lines else 'IDENTICAL')
        return 0 if not lines else 1
    if not args.kernel:
        p.error('KERNEL or --compare')
    fp = fingerprint(Path(args.kernel).read_bytes())
    text = json.dumps(fp, indent=1, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + '\n')
    print(f'uuid {fp["uuid"]}; {len(fp["segments"])} segments, {len(fp["sections"])} sections')
    for s in fp['version_strings'][:6]:
        print(f'  version string: {s}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
