#!/usr/bin/env python3
"""owner-trust.bundle for a GPU addon built elsewhere, rebuilt here from the addon's own files.

build-pipa-gpu-addon.py (UniXNU-pipa) writes owner-trust.bundle = [own module, the two original Apple modules]. The
CI run that builds the addon uploads only what is compiled from source (the plugin bundle, adrenoprobed, Turnip,
gpu-addon-clients.bin, trust.json, owner-trust.json), never the bundle: it carries Apple's modules. This rebuilds it
next to the local original-static-system.bundle (tools/original_trust.py) and proves it is the same bytes:

  1. the CDHash of each signed file is computed from its own code signature (LC_CODE_SIGNATURE, CodeDirectory
     SHA-256 truncated to 20 bytes) and must equal the one trust.json records;
  2. the own module is laid out as build-pipa-gpu-addon.py does (version 2, uuid5 identifier, sorted hashes,
     hash type 2) and the three modules as <u32 3><u32 starts...>;
  3. the result's SHA-256 must equal owner-trust.json's bundle_sha256.

  4. every Mach-O inside gpu-addon-clients.bin (NGPUADD2: what the kernel writes to the Data volume) carries a
     CDHash of the own module, and the plugin and daemon in it are the very files checked in 1.

  owner_trust.py --addon DIR --original original-static-system.bundle --out FILE
"""
import argparse
import hashlib
import json
import struct
import sys
import uuid
import zlib
from pathlib import Path

ORIGINAL_SHA256 = '7416ca4f8377146626bb284e2133c76bee6cb4e3ee0af5d648b186235a7323a7'   # build-pipa-gpu-addon.py
LC_CODE_SIGNATURE = 0x1d
CSMAGIC_EMBEDDED_SIGNATURE, CSMAGIC_CODEDIRECTORY = 0xfade0cc0, 0xfade0c02
CS_HASHTYPE_SHA256 = 2


def cdhash(path):
    """The SHA-256 CDHash (first 20 bytes) of a thin arm64 Mach-O's primary CodeDirectory."""
    data = path if isinstance(path, bytes) else Path(path).read_bytes()
    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from('<8I', data)
    if magic != 0xfeedfacf:
        raise ValueError(f'{path}: not a thin 64-bit Mach-O')
    at = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<2I', data, at)
        if cmd == LC_CODE_SIGNATURE:
            off, length = struct.unpack_from('<2I', data, at + 8)
            blob = data[off:off + length]
            m, _, count = struct.unpack_from('>3I', blob)
            if m != CSMAGIC_EMBEDDED_SIGNATURE:
                raise ValueError(f'{path}: no embedded signature')
            for i in range(count):
                slot, boff = struct.unpack_from('>2I', blob, 12 + 8 * i)
                if slot != 0:   # CSSLOT_CODEDIRECTORY
                    continue
                cm, clen = struct.unpack_from('>2I', blob, boff)
                hash_type = blob[boff + 37]
                if cm != CSMAGIC_CODEDIRECTORY or hash_type != CS_HASHTYPE_SHA256:
                    raise ValueError(f'{path}: primary CodeDirectory is not SHA-256')
                return hashlib.sha256(blob[boff:boff + clen]).hexdigest()[:40]
            raise ValueError(f'{path}: signature has no CodeDirectory')
        at += size
    raise ValueError(f'{path}: unsigned')


def addon_files(blob):
    """[(name, mode, data)] of an NGPUADD2 blob (build-pipa-gpu-addon.py's layout)."""
    if blob[:8] != b'NGPUADD2':
        raise ValueError('not an NGPUADD2 addon')
    count, _, total = struct.unpack_from('<IIQ', blob, 8)
    if total != len(blob):
        raise ValueError('addon length field does not match the file')
    pad = lambda n: (n + 7) & ~7
    at, files = 24, []
    for _ in range(count):
        nlen, mode, size, packed = struct.unpack_from('<IIQQ', blob, at)
        at += 24
        name = blob[at:at + nlen].rstrip(b'\0').decode()
        at += pad(nlen)
        data = zlib.decompress(blob[at:at + packed])
        at += pad(packed)
        if len(data) != size:
            raise ValueError(f'{name}: size field {size} != {len(data)}')
        files.append((name, mode, data))
    if at != len(blob):
        raise ValueError('trailing bytes after the last addon file')
    return files


def bundle(original, hashes):
    if hashlib.sha256(original).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('original-static-system.bundle is not the pinned one')
    if struct.unpack_from('<I', original)[0] != 2:
        raise ValueError('original bundle does not hold two modules')
    a, b = struct.unpack_from('<2I', original, 4)
    originals = [original[a:b], original[b:]]
    raw = sorted({bytes.fromhex(h) for h in hashes})
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, 'org.blu-sharky.adreno-metal:' + ''.join(h.hex() for h in raw))
    own = struct.pack('<I16sI', 2, identifier.bytes, len(raw)) + b''.join(h + bytes([2, 0, 0, 0]) for h in raw)
    modules, starts, cursor = [own, *originals], [], 16
    for mod in modules:
        starts.append(cursor)
        cursor += len(mod)
    return struct.pack('<4I', 3, *starts) + b''.join(modules)


def main():
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('--addon', type=Path, required=True, help='NativeAdrenoMetal.bundle, adrenoprobed, trust.json, owner-trust.json')
    a.add_argument('--original', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    args = a.parse_args()
    trust = json.loads((args.addon / 'trust.json').read_text())
    record = json.loads((args.addon / 'owner-trust.json').read_text())
    checks = [('plugin', args.addon / 'NativeAdrenoMetal.bundle/NativeAdrenoMetal', trust['cdhash']),
              ('daemon', args.addon / 'adrenoprobed', trust['daemon_cdhash'])]
    for label, path, expected in checks:
        got = cdhash(path)
        print(f"{'OK  ' if got == expected else 'DIFF'} {label}: computed {got} recorded {expected}")
        if got != expected:
            sys.exit(f'owner_trust: {label} does not carry the CDHash its trust record names')
    own = set(record['own_cdhashes'])
    files = addon_files((args.addon / 'gpu-addon-clients.bin').read_bytes())
    machos = [(n, d) for n, _, d in files if d[:4] == b'\xcf\xfa\xed\xfe']
    for name, data in machos:
        h = cdhash(data)
        print(f"{'OK  ' if h in own else 'DIFF'} addon {name}: {h}")
        if h not in own:
            sys.exit(f'owner_trust: {name} in the addon is not covered by the own trust module')
    by_name = dict((n, d) for n, d in machos)
    for name, path in (('addons/NativeAdrenoMetal.bundle/NativeAdrenoMetal', checks[0][1]), ('bin/adrenoprobed', checks[1][1])):
        if by_name.get(name) != path.read_bytes():
            sys.exit(f'owner_trust: {name} in the addon is not the uploaded file')
    if trust['turnip_cdhash'] not in {cdhash(d) for _, d in machos}:
        sys.exit('owner_trust: no Mach-O in the addon carries the recorded Turnip CDHash')
    print(f'addon: {len(files)} files, {len(machos)} Mach-O, all covered')
    hashes = [trust['cdhash'], trust['daemon_cdhash'], trust['turnip_cdhash'], *trust.get('extra_cdhashes', [])]
    if sorted(hashes) != sorted(record['own_cdhashes']):
        sys.exit('owner_trust: trust.json and owner-trust.json list different hashes')
    try:
        data = bundle(args.original.read_bytes(), hashes)
    except ValueError as e:
        sys.exit(f'owner_trust: {e}')
    digest = hashlib.sha256(data).hexdigest()
    if digest != record['bundle_sha256']:
        sys.exit(f'owner_trust: rebuilt {digest} != recorded {record["bundle_sha256"]}')
    args.out.write_bytes(data)
    print(f'owner-trust.bundle {digest} (= the CI build)')


if __name__ == '__main__':
    main()
