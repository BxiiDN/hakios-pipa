#!/usr/bin/env python3
"""Design B's new LUN 0 GPT, made OFFLINE from the original sectors (docs/IPADOS-PARTITION.md, sections 10-12). It never
touches a device: no adb, no fastboot, no block device; it reads two files and writes files into --out.

  gpt_rewrite.py HEAD TAIL --out DIR [--ipados-mib 20480] [--min-userdata-gib 64]

HEAD = LBA 0 .. end of the primary entries (head.bin of tools/gpt_export_decode.py, or the first sectors of
lun0-head.img), TAIL = the disk's last sectors (backup entries + backup header). The change:
  - userdata (the last partition, ending at last usable LBA) ends 1 MiB-aligned below where ipados begins;
  - a new entry "ipados" in the first empty slot: ipados-mib MiB up to the last usable LBA, Apple APFS type GUID, a
    unique GUID derived from the disk GUID (uuid5), no attributes;
  - the entry array CRC and both header CRCs recomputed.
Then it proves the result: both new GPTs parse with valid CRCs, the backup mirrors the primary, and every byte that
differs from the original lies in (a) userdata's ending-LBA field, (b) the new entry's slot, (c) the CRC fields of the
headers -- in the primary and in the backup copy. Anything else changed, or any doubt about the input, and nothing is
written. DIR gets new-head.bin, new-tail.bin, gpt_both0.bin (primary sectors then backup sectors, the layout Qualcomm's
ptool emits; ABL's check at .text 0x28140 wants size > 2 blocks, MBR 55 AA with a 0xEE entry, the header at block 1),
diff.json and SHA256SUMS.
"""
import argparse
import hashlib
import json
import struct
import sys
import uuid
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpt_capacity  # noqa: E402
import pipa_gpt  # noqa: E402

APFS = uuid.UUID('7c3457ef-0000-11aa-aa11-00306543ecac')
MIB = 1 << 20


class RewriteError(Exception):
    pass


def crc(b):
    return zlib.crc32(bytes(b)) & 0xffffffff


def header_fields(hdr):
    (_, _, size, _, _, current, backup, first, last, guid, entries_lba, count, esize, ecrc) = \
        struct.unpack_from('<8sIIIIQQQQ16sQIII', hdr)
    return {'size': size, 'current': current, 'backup': backup, 'first': first, 'last': last, 'guid': guid,
            'entries_lba': entries_lba, 'count': count, 'esize': esize, 'ecrc': ecrc}


def seal(hdr, size, entries_crc):
    struct.pack_into('<I', hdr, 88, entries_crc)
    struct.pack_into('<I', hdr, 16, 0)
    struct.pack_into('<I', hdr, 16, crc(hdr[:size]))


def rewrite(head, tail, ipados_mib=20480, min_userdata_gib=64):
    # ABL's GPT image check (abl LinuxLoader .text 0x28140): MBR signature 55 AA and a protective entry of type 0xEE
    if head[510:512] != b'\x55\xaa' or head[0x1c2] != 0xee:
        raise RewriteError('LBA 0 is not a protective MBR (55 AA, type 0xEE at 0x1c2): ABL would refuse the image')
    table = pipa_gpt.parse_gpt(head, 'head')                 # CRCs of the primary checked here
    s = table['sector_size']
    h = header_fields(head[s:s + 92])
    disk_blocks = h['backup'] + 1
    entries_off, entries_len = h['entries_lba'] * s, h['count'] * h['esize']
    problems = gpt_capacity.backup_check(head[entries_off:entries_off + entries_len], tail, s, disk_blocks)
    if problems:
        raise RewriteError('original backup GPT: ' + problems[0])
    names = [p['name'] for p in table['partitions']]
    if 'ipados' in names:
        raise RewriteError('an ipados partition exists already')
    userdata = max(table['partitions'], key=lambda p: p['last_lba'])
    if userdata['name'] != 'userdata' or userdata['last_lba'] != h['last']:
        raise RewriteError('userdata is not the last partition ending at the last usable LBA')
    align = MIB // s
    size = ipados_mib * MIB // s
    ipados_first = (h['last'] + 1 - size) // align * align
    if (h['last'] - ipados_first + 1) * s < gpt_capacity.need():
        raise RewriteError('ipados would be smaller than tools/gpt_capacity.py need')
    userdata_last = ipados_first - 1
    if (userdata_last - userdata['first_lba'] + 1) * s < min_userdata_gib << 30:
        raise RewriteError(f'userdata would keep less than {min_userdata_gib} GiB')

    entries = bytearray(head[entries_off:entries_off + entries_len])
    ud_slot = slot = None
    for i in range(h['count']):
        e = entries[i * h['esize']:(i + 1) * h['esize']]
        if e[:16] == b'\0' * 16:
            if slot is None:
                slot = i
            continue
        if e[56:128].decode('utf-16-le').split('\0', 1)[0] == 'userdata':
            ud_slot = i
    if slot is None:
        raise RewriteError('no empty entry slot')
    struct.pack_into('<Q', entries, ud_slot * h['esize'] + 40, userdata_last)
    guid = uuid.uuid5(uuid.UUID(bytes_le=h['guid']), 'ipados')
    new = APFS.bytes_le + guid.bytes_le + struct.pack('<QQQ', ipados_first, h['last'], 0) + 'ipados'.encode('utf-16-le')
    entries[slot * h['esize']:slot * h['esize'] + len(new)] = new
    ecrc = crc(entries)

    new_head = bytearray(head)
    new_head[entries_off:entries_off + entries_len] = entries
    phdr = bytearray(new_head[s:s + h['size']])
    seal(phdr, h['size'], ecrc)
    new_head[s:s + h['size']] = phdr

    new_tail = bytearray(tail)
    first_tail_lba = disk_blocks - len(tail) // s
    bhdr_off = len(tail) - s
    bh = header_fields(tail[bhdr_off:bhdr_off + 92])
    bent_off = (bh['entries_lba'] - first_tail_lba) * s
    new_tail[bent_off:bent_off + entries_len] = entries
    bhdr = bytearray(new_tail[bhdr_off:bhdr_off + bh['size']])
    seal(bhdr, bh['size'], ecrc)
    new_tail[bhdr_off:bhdr_off + bh['size']] = bhdr
    new_head, new_tail = bytes(new_head), bytes(new_tail)

    # proof: the new tables are sound, and only the planned bytes moved
    new_table = pipa_gpt.parse_gpt(new_head, 'new-head')
    problems = gpt_capacity.backup_check(new_head[entries_off:entries_off + entries_len], new_tail, s, disk_blocks)
    if problems:
        raise RewriteError('new backup GPT: ' + problems[0])
    allowed_head = [(s + 16, s + 20), (s + 88, s + 92),
                    (entries_off + ud_slot * h['esize'] + 40, entries_off + ud_slot * h['esize'] + 48),
                    (entries_off + slot * h['esize'], entries_off + (slot + 1) * h['esize'])]
    allowed_tail = [(bhdr_off + 16, bhdr_off + 20), (bhdr_off + 88, bhdr_off + 92),
                    (bent_off + ud_slot * h['esize'] + 40, bent_off + ud_slot * h['esize'] + 48),
                    (bent_off + slot * h['esize'], bent_off + (slot + 1) * h['esize'])]

    def changed(a, b, allowed):
        out = [i for i in range(len(a)) if a[i] != b[i]]
        bad = [i for i in out if not any(lo <= i < hi for lo, hi in allowed)]
        if bad:
            raise RewriteError(f'unplanned byte changed at offset {bad[0]}')
        return len(out)

    if len(new_head) != len(head) or len(new_tail) != len(tail):
        raise RewriteError('sizes changed')
    diff = {'head_bytes_changed': changed(head, new_head, allowed_head),
            'tail_bytes_changed': changed(tail, new_tail, allowed_tail),
            'userdata': [userdata['first_lba'], userdata['last_lba'], userdata_last],
            'ipados': [ipados_first, h['last']], 'ipados_bytes': (h['last'] - ipados_first + 1) * s,
            'userdata_bytes_after': (userdata_last - userdata['first_lba'] + 1) * s,
            'ipados_guid': str(guid), 'entry_slot': slot,
            'partitions_before': len(table['partitions']), 'partitions_after': len(new_table['partitions']),
            'free_after': pipa_gpt.free_ranges(new_table)}
    return new_head, new_tail, diff


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('head', type=Path)
    ap.add_argument('tail', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--ipados-mib', type=int, default=20480)
    ap.add_argument('--min-userdata-gib', type=int, default=64)
    a = ap.parse_args(argv)
    try:
        new_head, new_tail, diff = rewrite(a.head.read_bytes(), a.tail.read_bytes(), a.ipados_mib, a.min_userdata_gib)
    except (RewriteError, pipa_gpt.GptError) as e:
        print(f'REFUSED {e}')
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    files = {'new-head.bin': new_head, 'new-tail.bin': new_tail, 'gpt_both0.bin': new_head + new_tail}
    for name, data in files.items():
        (a.out / name).write_bytes(data)
    (a.out / 'diff.json').write_text(json.dumps(diff, indent=2) + '\n')
    (a.out / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(d).hexdigest()}  {n}\n' for n, d in files.items()))
    print(json.dumps(diff, indent=2))
    print('NEW GPT WRITTEN TO FILES ONLY (nothing was sent to any device)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
