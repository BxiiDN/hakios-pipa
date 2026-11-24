#!/usr/bin/env python3
"""Extract named partitions from an Android A/B OTA payload.bin (full OTA only), read-only on the input.

  ota_extract.py PAYLOAD.bin|OTA.zip --out DIR [--list] PARTITION...

Full OTAs carry each partition as REPLACE / REPLACE_BZ / REPLACE_XZ / ZERO / DISCARD operations; a delta operation
(SOURCE_COPY, BSDIFF, PUFFDIFF, ...) is refused, never guessed. Each operation's data is checked against its
data_sha256_hash when the manifest records one, and the partition against new_partition_info.hash.
The protobuf wire format is decoded here (update_metadata.proto field numbers), so nothing else is needed.
"""
import argparse
import bz2
import hashlib
import lzma
import struct
import sys
import zipfile
from pathlib import Path

REPLACE, REPLACE_BZ, ZERO, DISCARD, REPLACE_XZ = 0, 1, 6, 7, 8


def varint(buf, i):
    shift = value = 0
    while True:
        b = buf[i]
        i += 1
        value |= (b & 0x7f) << shift
        if not b & 0x80:
            return value, i
        shift += 7


def fields(buf):
    """(field number, wire type, value) for each field of one message; value is int or bytes."""
    i, out = 0, []
    while i < len(buf):
        key, i = varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = varint(buf, i)
        elif wt == 1:
            v = struct.unpack_from('<Q', buf, i)[0]
            i += 8
        elif wt == 2:
            n, i = varint(buf, i)
            v = bytes(buf[i:i + n])
            i += n
        elif wt == 5:
            v = struct.unpack_from('<I', buf, i)[0]
            i += 4
        else:
            raise ValueError(f'protobuf wire type {wt} not supported')
        out.append((num, wt, v))
    return out


def first(fs, num, default=None):
    return next((v for n, _, v in fs if n == num), default)


def open_payload(path):
    """A file object positioned anywhere: payload.bin itself, or the stored payload.bin member of an OTA zip."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        info = z.getinfo('payload.bin')
        if info.compress_type != zipfile.ZIP_STORED:
            raise ValueError('payload.bin is compressed inside the zip')
        f = open(path, 'rb')
        f.seek(info.header_offset)
        local = f.read(30)
        n, m = struct.unpack_from('<HH', local, 26)
        return f, info.header_offset + 30 + n + m
    return open(path, 'rb'), 0


def manifest(f, base):
    f.seek(base)
    head = f.read(24)
    if head[:4] != b'CrAU':
        raise ValueError('not an A/B OTA payload (no CrAU magic)')
    version, msize, sigsize = struct.unpack('>QQI', head[4:24])
    if version != 2:
        raise ValueError(f'payload version {version}, only 2 is known')
    m = fields(f.read(msize))
    return m, base + 24 + msize + sigsize


def partitions(m):
    block = first(m, 3, 4096)
    out = {}
    for n, _, v in m:
        if n != 13:
            continue
        p = fields(v)
        name = first(p, 1).decode()
        info = first(p, 7)
        info = fields(info) if info else []
        ops = []
        for pn, _, pv in p:
            if pn != 8:
                continue
            o = fields(pv)
            dst = [(first(fields(e), 1, 0), first(fields(e), 2, 0)) for en, _, e in o if en == 6]
            ops.append({'type': first(o, 1, 0), 'offset': first(o, 2, 0), 'length': first(o, 3, 0),
                        'dst': dst, 'sha256': first(o, 8)})
        out[name] = {'size': first(info, 1), 'sha256': first(info, 2), 'ops': ops, 'block': block}
    return out


def extract(f, data_base, part, dest):
    block = part['block']
    size = part['size'] or sum(n for op in part['ops'] for _, n in op['dst']) * block
    with open(dest, 'wb') as out:
        out.truncate(size)
        for op in part['ops']:
            t = op['type']
            if t in (ZERO, DISCARD):
                for start, n in op['dst']:
                    out.seek(start * block)
                    out.write(b'\0' * n * block)
                continue
            if t not in (REPLACE, REPLACE_BZ, REPLACE_XZ):
                raise ValueError(f'operation type {t} is not a full-OTA operation; refusing')
            f.seek(data_base + op['offset'])
            data = f.read(op['length'])
            if op['sha256'] and hashlib.sha256(data).digest() != op['sha256']:
                raise ValueError('operation data does not match its data_sha256_hash')
            data = data if t == REPLACE else bz2.decompress(data) if t == REPLACE_BZ else lzma.decompress(data)
            pos = 0
            for start, n in op['dst']:
                out.seek(start * block)
                out.write(data[pos:pos + n * block])
                pos += n * block
    got = hashlib.sha256(Path(dest).read_bytes()).digest()
    if part['sha256'] and got != part['sha256']:
        raise ValueError(f'{dest}: partition hash does not match new_partition_info')
    return got.hex()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('payload')
    ap.add_argument('names', nargs='*')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args(argv)
    f, base = open_payload(a.payload)
    m, data_base = manifest(f, base)
    parts = partitions(m)
    if a.list:
        for name, p in sorted(parts.items()):
            print(f'{name:24} {p["size"] or 0:>12}')
    if a.names and not a.out:
        ap.error('--out is required to extract')
    for name in a.names:
        if name not in parts:
            print(f'MISSING  {name}')
            return 1
        a.out.mkdir(parents=True, exist_ok=True)
        digest = extract(f, data_base, parts[name], a.out / f'{name}.img')
        print(f'EXTRACTED {name}.img sha256 {digest} (= new_partition_info)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
