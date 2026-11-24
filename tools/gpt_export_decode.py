#!/usr/bin/env python3
"""Decode LUN 0's GPT exported by the "GPT export (QR)" UEFI tool (patches/unixnu/0007, GptExport.h) and check it.
Read-only on its input; writes only into --out (docs/IPADOS-PARTITION.md, section 11).

  gpt_export_decode.py FILE --out DIR

FILE is what the phone saved: the "HKGPT1" container itself (what OneSend writes as pipa-lun0-gpt.hkgpt), its "LMS1"
envelope, or the raw OneSend frames ("OS" + 28-byte header + 720-byte block + CRC32, concatenated, in any order, repeats
allowed). Every CRC is checked: frame, envelope, container. Then the GPT: primary header and entries (tools/pipa_gpt.py),
the backup header and entries against them (tools/gpt_capacity.py backup_check), and the disk size the backup names.
DIR/sda.bin is the primary dump tools/pipa_gpt.py takes; DIR/head.bin and DIR/tail.bin are the exact sectors for a
restore; DIR/report.json says what was checked. DIR holds the tablet's partition table: keep it private.
"""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpt_capacity  # noqa: E402
import pipa_gpt  # noqa: E402

FRAME_HEADER, BLOCK = 28, 720
FRAME = FRAME_HEADER + BLOCK + 4


class ExportError(Exception):
    pass


def crc(data):
    return zlib.crc32(data) & 0xffffffff


def frames_to_payload(blob):
    """The payload the frames of one session carry, from concatenated frames."""
    blocks, meta = {}, None
    for at in range(0, len(blob) - FRAME + 1, FRAME):
        f = blob[at:at + FRAME]
        if f[:4] != b'OS\x02\x00':
            raise ExportError(f'no frame at byte {at}')
        if struct.unpack_from('<I', f, FRAME_HEADER + BLOCK)[0] != crc(f[:FRAME_HEADER + BLOCK]):
            raise ExportError(f'frame at byte {at}: CRC32 does not match')
        session, seq, count, size, _, length, pcrc = struct.unpack_from('<IIIHHII', f, 4)
        if size != BLOCK or count != -(-length // BLOCK):
            raise ExportError('frame geometry is not the exporter\'s')
        if meta is None:
            meta = (session, count, length, pcrc)
        elif meta != (session, count, length, pcrc):
            raise ExportError('frames of more than one session')
        index = seq - seq // 5                 # Sequence = Index + Index // 4
        if index + index // 4 != seq or index >= count:
            raise ExportError(f'sequence {seq} is not one the exporter makes')
        blocks[index] = f[FRAME_HEADER:FRAME_HEADER + BLOCK]
    if meta is None:
        raise ExportError('no frames')
    session, count, length, pcrc = meta
    missing = [i for i in range(count) if i not in blocks]
    if missing:
        raise ExportError(f'{len(missing)} of {count} frames missing (first {missing[0]}): scan again')
    payload = b''.join(blocks[i] for i in range(count))[:length]
    if crc(payload) != pcrc:
        raise ExportError('reassembled payload CRC32 does not match')
    return payload


def envelope_data(env):
    if env[:6] != b'LMS1\x02\x00':
        raise ExportError('not an LMS1 envelope')
    name_len, mime_len, length, c, length2, c2 = struct.unpack_from('<HHIIII', env, 6)
    start = 26 + name_len + mime_len
    data = env[start:start + length]
    if len(data) != length or (length, c) != (length2, c2) or crc(data) != c:
        raise ExportError('envelope length or CRC32 does not match')
    return env[26:26 + name_len].decode(errors='replace'), data


def container(data):
    if data[:8] != b'HKGPT1\0\0':
        raise ExportError('not an HKGPT1 container')
    block, head_blocks, disk_blocks, tail_blocks, c = struct.unpack_from('<IIQII', data, 8)
    body = data[32:]
    if len(body) != (head_blocks + tail_blocks) * block or crc(body) != c:
        raise ExportError('container length or CRC32 does not match')
    return block, disk_blocks, body[:head_blocks * block], body[head_blocks * block:]


def decode(blob):
    name = None
    if blob[:4] == b'OS\x02\x00':
        blob = frames_to_payload(blob)
    if blob[:4] == b'LMS1':
        name, blob = envelope_data(blob)
    block, disk_blocks, head, tail = container(blob)
    table = pipa_gpt.parse_gpt(head, 'sda.bin')
    problems = []
    if table['sector_size'] != block:
        problems.append('GPT sector size differs from the disk block size')
    if table['backup_lba'] != disk_blocks - 1:
        problems.append('primary header does not name the disk\'s last LBA as backup')
    hdr = head[block:block + 92]
    entries_lba, count, esize = struct.unpack_from('<QII', hdr, 72)
    problems += gpt_capacity.backup_check(head[entries_lba * block:entries_lba * block + count * esize], tail, block, disk_blocks)
    return {'name': name, 'block': block, 'disk_blocks': disk_blocks, 'head': head, 'tail': tail, 'table': table,
            'problems': problems}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        r = decode(a.file.read_bytes())
    except (ExportError, pipa_gpt.GptError, struct.error) as e:
        print(f'FAIL {e}')
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / 'head.bin').write_bytes(r['head'])
    (a.out / 'tail.bin').write_bytes(r['tail'])
    (a.out / 'sda.bin').write_bytes(r['head'])
    t = r['table']
    free = pipa_gpt.free_ranges(t)
    report = {'file': r['name'], 'block': r['block'], 'disk_blocks': r['disk_blocks'], 'partitions': len(t['partitions']),
              'first_usable_lba': t['first_usable_lba'], 'last_usable_lba': t['last_usable_lba'],
              'free_ranges': free, 'problems': r['problems'],
              'head_sha256': __import__('hashlib').sha256(r['head']).hexdigest(),
              'tail_sha256': __import__('hashlib').sha256(r['tail']).hexdigest()}
    (a.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(t["partitions"])} partitions, usable {t["first_usable_lba"]}..{t["last_usable_lba"]}, '
          f'free {sum(b - a_ + 1 for a_, b in free) * r["block"]} B')
    for p in r['problems']:
        print(f'FAIL {p}')
    print('GPT EXPORT ' + ('FAIL' if r['problems'] else 'VERIFIED: primary and backup sound and consistent'))
    return 1 if r['problems'] else 0


if __name__ == '__main__':
    sys.exit(main())
