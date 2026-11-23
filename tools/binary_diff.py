#!/usr/bin/env python3
"""Where two builds of the same firmware differ, and what the differing bytes are.

  binary_diff.py A B [--json OUT]

Lists every differing byte range (merged when closer than 16 bytes). For each range it names the enclosing PE/COFF
image (an MZ header whose e_lfanew points at "PE\\0\\0") and classifies the bytes: COFF TimeDateStamp, optional-header
CheckSum, debug directory / CodeView record (PDB path and GUID), or other. Firmware volumes compress their files, so
ranges inside compressed sections show up as "other"; build twice uncompressed or compare the Build/ trees then.
Exit 0 when identical.
"""
import argparse
import json
import struct
import sys
from pathlib import Path


def ranges(a, b, gap=16):
    out, start, last = [], None, None
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            if start is None:
                start = i
            elif i - last > gap:
                out.append((start, last + 1))
                start = i
            last = i
    if start is not None:
        out.append((start, last + 1))
    if len(a) != len(b):
        out.append((n, max(len(a), len(b))))
    return out


def pe_images(data):
    images, at = [], data.find(b'MZ')
    while at >= 0:
        if at + 64 <= len(data):
            lfanew = struct.unpack_from('<I', data, at + 60)[0]
            pe = at + lfanew
            if 0 < lfanew < 4096 and data[pe:pe + 4] == b'PE\0\0':
                machine, nsect, stamp = struct.unpack_from('<HHI', data, pe + 4)
                optsize = struct.unpack_from('<H', data, pe + 20)[0]
                opt = pe + 24
                magic = struct.unpack_from('<H', data, opt)[0]
                dd = opt + (112 if magic == 0x20b else 96)
                debug_rva, debug_size = struct.unpack_from('<II', data, dd + 6 * 8) if optsize > (dd - opt) + 56 else (0, 0)
                size_of_image = struct.unpack_from('<I', data, opt + 56)[0]
                images.append({'offset': at, 'pe': pe, 'end': at + max(size_of_image, 0x200), 'stamp_at': pe + 8,
                               'checksum_at': opt + 64, 'debug_rva': debug_rva, 'debug_size': debug_size})
        at = data.find(b'MZ', at + 2)
    return images


def classify(data, start, end, images):
    for img in images:
        if img['offset'] <= start < img['end']:
            if start < img['stamp_at'] + 4 and end > img['stamp_at']:
                return img, 'COFF TimeDateStamp'
            if start < img['checksum_at'] + 4 and end > img['checksum_at']:
                return img, 'optional-header CheckSum'
            window = data[max(img['offset'], start - 64):end + 64]
            if b'RSDS' in window or b'.pdb' in window or b'.dll' in window or b'/Build/' in window:
                return img, 'debug directory / CodeView (path or GUID)'
            return img, 'other (inside PE image)'
    return None, 'other (outside any PE header-identified image: FV/FFS header, padding or compressed data)'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('a')
    p.add_argument('b')
    p.add_argument('--json')
    args = p.parse_args(argv)
    a, b = Path(args.a).read_bytes(), Path(args.b).read_bytes()
    diffs = ranges(a, b)
    images = pe_images(a)
    report = []
    for start, end in diffs:
        img, kind = classify(a, start, end, images)
        report.append({'start': start, 'end': end, 'bytes': end - start, 'kind': kind,
                       'image_offset': img['offset'] if img else None,
                       'a': a[start:min(end, start + 32)].hex(), 'b': b[start:min(end, start + 32)].hex()})
    summary = {}
    for r in report:
        summary[r['kind']] = summary.get(r['kind'], 0) + 1
    print(f'{len(a)} / {len(b)} bytes; {len(report)} differing ranges; {len(images)} PE images found in A')
    for kind, count in sorted(summary.items()):
        print(f'  {count:5}  {kind}')
    for r in report[:40]:
        print(f'  {r["start"]:#010x}+{r["bytes"]:<6} {r["kind"]}  A={r["a"][:32]} B={r["b"][:32]}')
    if args.json:
        Path(args.json).write_text(json.dumps({'ranges': report, 'summary': summary}, indent=1) + '\n')
    return 0 if not report else 1


if __name__ == '__main__':
    sys.exit(main())
