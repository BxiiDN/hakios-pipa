#!/usr/bin/env python3
"""Free space of every UFS LUN, from the GPT reader's LOG.BIN (package/gpt-reader), against what an `ipados` partition needs.
Read-only on its inputs; it never writes a device (docs/IPADOS-PARTITION.md).

  gpt_capacity.py need [--root-bytes N] [--data-pages N] [--reserve-mib N]
  gpt_capacity.py report LOG.BIN [--out DIR] [--json OUT] [--need BYTES]

need: the smallest partition native-ufs-root-part=ipados can use, from the rules of UniXNU-pipa drivers/ShengUfs/NativeUfs.cpp
native_ufs_store_open and drivers/RamBlock PersistOverlay.h: the root image (its OS and SystemOS objects at the start), a guard of
1024 blocks, the Data store window (1 header block + bitmap + one block per seed page), then the log reserve (sheng-log-reserve,
1024 MiB by default); 4096-byte blocks, rounded up to whole MiB.

report: for each disk the reader saw (gpt/<disk>.info, .head, .tail records):
  - the primary GPT parses with valid CRCs (tools/pipa_gpt.py parse_gpt) and names the last LBA of the disk as its backup;
  - the backup header in the disk's last sector has a valid CRC, points back to LBA 1, and its entry array (the 4 sectors before
    it) is byte-identical to the primary one;
  - the free ranges inside first..last usable LBA, and the largest; with --need, whether one range holds the partition.
--out writes each disk's head as <disk>.bin, the dump format pipa_gpt.py read/check/simulate take.
"""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipa_gpt  # noqa: E402

BLOCK = 4096
MIB = 1 << 20
ROOT_BYTES = 9_457_106_944        # userdata-root.img of session 1 (OS + SystemOS objects), 2 308 864 blocks
DATA_PAGES = 2_097_152            # the 8 GiB Data seed (data.dbr logical size / 4096)
RESERVE_MIB = 1024                # NativeUfs kDefaultReserveMiB
GUARD_BLOCKS = 1024               # native_ufs_store_open: partition - blocks - reserve >= imageBlocks + 1024


def window_blocks(pages):
    return 1 + (pages + 32767) // 32768 + pages      # PersistOverlay.h windowBlocks


def need(root_bytes=ROOT_BYTES, data_pages=DATA_PAGES, reserve_mib=RESERVE_MIB):
    image = -(-root_bytes // BLOCK)
    blocks = image + GUARD_BLOCKS + window_blocks(data_pages) + reserve_mib * (MIB // BLOCK)
    return -(-blocks * BLOCK // MIB) * MIB


def records(log):
    """{name: bytes or negative errno} of a LOG.BIN (UXFILE01 records, UXEND000 after the last)."""
    out, at = {}, 0
    while at + 8 <= len(log):
        if log[at:at + 8] == b'UXEND000':
            return out
        if log[at:at + 8] != b'UXFILE01' or at + 64 > len(log):
            raise ValueError(f'LOG.BIN: no record at {at}')
        size = struct.unpack_from('<q', log, at + 8)[0]
        name = log[at + 16:at + 64].split(b'\0')[0].decode()
        data = log[at + 64:at + 64 + size] if size > 0 else size
        out[name] = data
        at += 64 + (-(-size // 8) * 8 if size > 0 else 0)
    raise ValueError('LOG.BIN: no UXEND000')


def backup_check(head_table, tail, sector, disk_lbas):
    """Problems of the backup GPT in TAIL (the disk's last 5 sectors), compared with the primary table; [] when it is sound."""
    problems = []
    hdr = tail[-sector:]
    if hdr[:8] != pipa_gpt.GPT_SIGNATURE:
        return ['no backup GPT header in the last sector']
    (_, _, size, crc, _, current, other, _, _, _, entries_lba, count, esize, ecrc) = struct.unpack_from('<8sIIIIQQQQ16sQIII', hdr)
    blank = bytearray(hdr[:size])
    blank[16:20] = b'\0\0\0\0'
    if zlib.crc32(bytes(blank)) & 0xffffffff != crc:
        problems.append('backup header CRC32 does not match')
    if current != disk_lbas - 1:
        problems.append(f'backup header says it is at LBA {current}, the disk ends at {disk_lbas - 1}')
    if other != 1:
        problems.append(f'backup header points to LBA {other}, not 1')
    first_tail_lba = disk_lbas - len(tail) // sector
    start = (entries_lba - first_tail_lba) * sector
    table = tail[start:start + count * esize] if start >= 0 else b''
    if len(table) != count * esize:
        problems.append('backup entries are not inside the last sectors read')
    elif zlib.crc32(table) & 0xffffffff != ecrc:
        problems.append('backup entries CRC32 does not match')
    elif table != head_table:
        problems.append('backup entries differ from the primary ones')
    return problems


def report(log_bytes, out=None, need_bytes=None):
    recs = records(log_bytes)
    disks = sorted({n.split('/')[1].split('.')[0] for n in recs if n.startswith('gpt/')})
    result = []
    for disk in disks:
        info, head, tail = (recs.get(f'gpt/{disk}.{k}') for k in ('info', 'head', 'tail'))
        entry = {'disk': disk, 'problems': []}
        result.append(entry)
        if not isinstance(info, bytes) or not isinstance(head, bytes) or not isinstance(tail, bytes):
            entry['problems'].append('reader did not record info, head and tail')
            continue
        fields = dict(f.split('=') for f in info.decode().split())
        size, sector = int(fields['bytes']), int(fields['sector'])
        lbas = size // sector
        entry.update(bytes=size, sector=sector, lbas=lbas)
        try:
            table = pipa_gpt.parse_gpt(head, f'{disk}.head')
        except pipa_gpt.GptError as e:
            entry['problems'].append(str(e))
            continue
        if table['sector_size'] != sector:
            entry['problems'].append(f'GPT sector size {table["sector_size"]} is not the disk\'s {sector}')
        if table['backup_lba'] != lbas - 1:
            entry['problems'].append(f'primary header names backup LBA {table["backup_lba"]}, the disk ends at {lbas - 1}')
        hdr = head[sector:sector + 92]
        entries_lba, count, esize = struct.unpack_from('<QII', hdr, 72)
        primary_entries = head[entries_lba * sector:entries_lba * sector + count * esize]
        entry['problems'] += backup_check(primary_entries, tail, sector, lbas)
        free = pipa_gpt.free_ranges(table)
        entry.update(partitions=len(table['partitions']), first_usable=table['first_usable_lba'],
                     last_usable=table['last_usable_lba'],
                     last_partition=max(table['partitions'], key=lambda p: p['last_lba'])['name'] if table['partitions'] else None,
                     free=[(a, b, (b - a + 1) * sector) for a, b in free],
                     free_bytes=sum((b - a + 1) * sector for a, b in free),
                     largest_free=max(((b - a + 1) * sector for a, b in free), default=0),
                     tail_after_last_usable=(lbas - 1 - table['last_usable_lba']) * sector)
        if need_bytes:
            entry['fits'] = entry['largest_free'] >= need_bytes
        if out:
            out.mkdir(parents=True, exist_ok=True)
            (out / f'{disk}.bin').write_bytes(head)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('need')
    n.add_argument('--root-bytes', type=int, default=ROOT_BYTES)
    n.add_argument('--data-pages', type=int, default=DATA_PAGES)
    n.add_argument('--reserve-mib', type=int, default=RESERVE_MIB)
    r = sub.add_parser('report')
    r.add_argument('log', type=Path)
    r.add_argument('--out', type=Path)
    r.add_argument('--json', type=Path)
    r.add_argument('--need', type=int, default=None)
    a = ap.parse_args(argv)
    if a.cmd == 'need':
        b = need(a.root_bytes, a.data_pages, a.reserve_mib)
        print(f'ipados partition needs at least {b} bytes ({b / 2**30:.2f} GiB): root {a.root_bytes}, Data window '
              f'{window_blocks(a.data_pages) * BLOCK}, guard {GUARD_BLOCKS * BLOCK}, reserve {a.reserve_mib} MiB')
        return 0
    want = a.need if a.need is not None else need()
    res = report(a.log.read_bytes(), a.out, want)
    bad = 0
    for e in res:
        state = 'FAIL' if e['problems'] else 'PASS'
        bad += bool(e['problems'])
        line = f'{state:4} {e["disk"]}'
        if 'lbas' in e:
            line += f'  {e["bytes"]} B, sector {e["sector"]}'
        if 'free_bytes' in e:
            line += (f', {e["partitions"]} partitions (last {e["last_partition"]}), free {e["free_bytes"]} B, '
                     f'largest {e["largest_free"]} B -> {"FITS" if e.get("fits") else "does not fit"} {want} B')
        print(line)
        for p in e['problems']:
            print(f'     {p}')
    fits = [e['disk'] for e in res if e.get('fits')]
    print(f'IPADOS PARTITION ({want} B): ' + (f'room on {", ".join(fits)}' if fits else 'NO LUN HAS ROOM WITHOUT RESIZING'))
    if a.json:
        a.json.write_text(json.dumps(res, indent=2) + '\n')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
