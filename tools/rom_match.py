#!/usr/bin/env python3
"""Does a candidate boot / vendor_boot / dtbo image belong to the ROM installed on this tablet? Offline, from facts read on the
tablet without root (docs/IPADOS-PARTITION.md, session 14). Nothing is written anywhere but --json.

  rom_match.py --boot boot.img [--vendor-boot vendor_boot.img] [--dtbo dtbo.img] --config config.gz --uname-r R --uname-v V
               [--msm-id 0x164:0x20001] [--dtbo-idx 9] [--json OUT]

Device facts (adb, read-only): `cat /proc/config.gz`, `uname -r`, `uname -v`, `getprop ro.boot.dtbo_idx`, fastboot getvar
hw-revision (the SoC version cell of qcom,msm-id). The installed port ROM carries no vbmeta digest (ro.boot.vbmeta.digest is
empty), so AVB cannot vouch for an image; the kernel is identified instead by:
  - its "Linux version" banner holds uname -r and uname -v exactly;
  - its embedded configuration (CONFIG_IKCONFIG: the gzip between IKCFG_ST and IKCFG_ED) is, decompressed, byte for byte the
    device's /proc/config.gz decompressed.
vendor_boot: a device tree for the SoC (qcom,msm-id = the given id). dtbo: a table with an entry at ro.boot.dtbo_idx.
The device tree and dtbo checks only show the image can serve this SoC; unlike the kernel they cannot prove it is the
installed one (/proc/device-tree is closed to the shell on this ROM).
"""
import argparse
import gzip
import json
import struct
import sys
import zlib
from pathlib import Path

FDT = b'\xd0\x0d\xfe\xed'
DTBO = 0xd7b7ab1e
PAGE = 4096


def align(n, a=PAGE):
    return (n + a - 1) // a * a


def boot_kernel(data):
    if data[:8] != b'ANDROID!':
        raise ValueError('not an Android boot image')
    version = struct.unpack_from('<I', data, 40)[0]
    if version >= 3:
        size, page = struct.unpack_from('<I', data, 8)[0], PAGE
    else:
        size, page = struct.unpack_from('<I', data, 8)[0], struct.unpack_from('<I', data, 36)[0]
    kernel = data[page:page + size]
    if kernel[:2] == b'\x1f\x8b':
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        kernel = d.decompress(kernel) + d.flush()
    return version, kernel


def banner(kernel):
    i = kernel.find(b'Linux version ')
    return kernel[i:kernel.index(b'\n', i)].decode(errors='replace') if i >= 0 else None


def ikconfig(kernel):
    i, j = kernel.find(b'IKCFG_ST'), kernel.find(b'IKCFG_ED')
    if i < 0 or j < i:
        return None
    return gzip.decompress(kernel[i + 8:j])


def vendor_dtbs(data):
    if data[:8] != b'VNDRBOOT':
        raise ValueError('not a vendor_boot image')
    version, page = struct.unpack_from('<II', data, 8)
    ramdisk = struct.unpack_from('<I', data, 24)[0]
    header, dtb_size = struct.unpack_from('<II', data, 2096)
    at = align(header, page) + align(ramdisk, page)
    blob, out = data[at:at + dtb_size], []
    o = 0
    while o + 8 <= len(blob) and blob[o:o + 4] == FDT:
        n = struct.unpack_from('>I', blob, o + 4)[0]
        out.append(blob[o:o + n])
        o += n
    return version, out


def fdt_root_prop(dtb, name):
    """Value bytes of a property of the root node, or None."""
    off_struct, off_strings = struct.unpack_from('>II', dtb, 8)
    i = off_struct
    depth = 0
    while i < len(dtb):
        token = struct.unpack_from('>I', dtb, i)[0]
        i += 4
        if token == 1:
            z = dtb.index(b'\0', i)
            i = (z + 4) & ~3
            depth += 1
        elif token == 2:
            depth -= 1
        elif token == 3:
            length, nameoff = struct.unpack_from('>II', dtb, i)
            i += 8
            z = dtb.index(b'\0', off_strings + nameoff)
            if depth == 1 and dtb[off_strings + nameoff:z].decode() == name:
                return dtb[i:i + length]
            i = (i + length + 3) & ~3
        elif token == 4:
            continue
        else:
            return None
    return None


def msm_ids(dtb):
    v = fdt_root_prop(dtb, 'qcom,msm-id') or b''
    cells = [struct.unpack_from('>I', v, k)[0] for k in range(0, len(v) - len(v) % 4, 4)]
    return [(cells[k], cells[k + 1]) for k in range(0, len(cells) - 1, 2)]


def dtbo_entries(data):
    magic, total, header, entry_size, count = struct.unpack_from('>5I', data, 0)
    if magic != DTBO:
        raise ValueError('not a dtbo image')
    return count


def check(boot=None, vendor=None, dtbo=None, config=None, uname_r=None, uname_v=None, msm=(0x164, 0x20001), dtbo_idx=9):
    results = []
    say = lambda ok, text: results.append(('PASS' if ok else 'FAIL', text))
    if boot is not None:
        version, kernel = boot_kernel(boot)
        b = banner(kernel)
        say(b is not None and uname_r is not None and f'Linux version {uname_r} ' in b,
            f'boot v{version}: kernel banner has uname -r {uname_r!r} ({(b or "no banner")[:60]})')
        say(b is not None and uname_v is not None and b.rstrip().endswith(uname_v),
            f'kernel banner ends with uname -v {uname_v!r}')
        cfg = ikconfig(kernel)
        dev = gzip.decompress(config) if config else None
        say(cfg is not None and dev is not None and cfg == dev,
            'embedded kernel config = the device\'s /proc/config.gz' + ('' if cfg is not None else ' (no IKCONFIG in the image)'))
    if vendor is not None:
        version, dtbs = vendor_dtbs(vendor)
        ids = [i for d in dtbs for i in msm_ids(d)]
        say(bool(dtbs), f'vendor_boot v{version}: {len(dtbs)} device trees')
        say(tuple(msm) in ids, f'a device tree for qcom,msm-id <{msm[0]} {msm[1]:#x}> (has {sorted(set(ids))})')
    if dtbo is not None:
        n = dtbo_entries(dtbo)
        say(n > dtbo_idx, f'dtbo: {n} entries, ro.boot.dtbo_idx={dtbo_idx} present')
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--boot', type=Path)
    ap.add_argument('--vendor-boot', type=Path)
    ap.add_argument('--dtbo', type=Path)
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--uname-r', required=True)
    ap.add_argument('--uname-v', required=True)
    ap.add_argument('--msm-id', default='0x164:0x20001')
    ap.add_argument('--dtbo-idx', type=int, default=9)
    ap.add_argument('--json', type=Path)
    a = ap.parse_args(argv)
    soc, ver = a.msm_id.split(':')
    rd = lambda p: p.read_bytes() if p else None
    res = check(rd(a.boot), rd(a.vendor_boot), rd(a.dtbo), a.config.read_bytes(), a.uname_r, a.uname_v,
                (int(soc, 0), int(ver, 0)), a.dtbo_idx)
    for level, text in res:
        print(f'{level:4} {text}')
    bad = any(level == 'FAIL' for level, _ in res)
    print('ROM MATCH ' + ('FAIL' if bad else 'PASS'))
    if a.json:
        a.json.write_text(json.dumps(res, indent=2) + '\n')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
