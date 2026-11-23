#!/usr/bin/env python3
"""A built UniXNU payload.img for pipa, checked the way DarwinBoot will read it, offline.

Reads the FAT volume in place (mtools), then:
  kernel     the payload kernel.macho parses as DarwinBoot's ParseKernelHeader does (MH_EXECUTE or fileset, arm64,
             one LC_UNIXTHREAD entry in an executable segment, non-overlapping segments, span <= 256 MiB - 2 MiB);
             payload.json's kernel_sha256 is the stage-B kernel given; its Data UUID string is the seed's
  ADT        /chosen dram-base/size = the DTS span (patch unixnu 0006), darwinboot-memory-size = the board window,
             memory-map has a zeroed 16-byte slot for each payload file present and none for an absent one
  trust      ValidTrustCaches (count, offsets, version 2, 24-byte entries, hash types 1..4, strictly sorted)
  addon      NGPUADD2 header length = file size, = the verified addon, every Mach-O inside covered by the trust cache
  data       DBRDISK1 extents valid, exactly one APFS volume, its UUID = the kernel's compiled Data UUID
  window     DarwinBoot's layout inside the window (kernel span, args page, ADT, packed RAM disk, trust, addon) must
             leave the 2 MiB DarwinBoot keeps: Used <= window - 2 MiB
Exit 1 on any failure. Prints no platform seed (unique-chip-id) and no Data UUID value.

  payload_check.py --payload payload.img --manifest payload.json --kernel stage-b/kernel.macho --addon gpu-addon-clients.bin \
                   --board board.toml --unixnu UniXNU [--json OUT]
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import tempfile
import tomllib
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from owner_trust import addon_files, cdhash   # noqa: E402

MB2, WINDOW_DEFAULT, PAGE = 0x200000, 0x10000000, 0x1000
UUID_RE = re.compile(rb'[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}')


def align(v, a):
    return (v + a - 1) // a * a


def kernel_span(data):
    """(base, end, entry) of an arm64 Mach-O kernel as DarwinBoot's ParseKernelHeader computes them."""
    magic, cpu, sub, ftype, ncmds, sizeofcmds = struct.unpack_from('<6I', data)
    if magic != 0xfeedfacf or cpu != 0x0100000c or (sub & 0xffffff) not in (0, 2) or ftype not in (2, 12):
        raise ValueError('kernel: not an arm64 MH_EXECUTE/MH_FILESET')
    at, end, segs, entry = 32, 32 + sizeofcmds, [], None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<2I', data, at)
        if size < 8 or size % 8 or at + size > end:
            raise ValueError('kernel: bad load command')
        if cmd == 0x19:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', data, at + 24)
            prot = struct.unpack_from('<I', data, at + 60)[0]
            if vmsize:
                if vmsize > WINDOW_DEFAULT or filesize > vmsize or fileoff + filesize > len(data):
                    raise ValueError('kernel: segment out of bounds')
                segs.append((vmaddr, vmsize, filesize, prot))
        elif cmd == 5:
            if entry is not None or size != 288:
                raise ValueError('kernel: LC_UNIXTHREAD')
            entry = struct.unpack_from('<Q', data, at + 272)[0]
        at += size
    if entry is None or not segs:
        raise ValueError('kernel: no entry or no segment')
    for i, (a, s, _, _) in enumerate(segs):
        for b, t, _, _ in segs[:i]:
            if a < b + t and b < a + s:
                raise ValueError('kernel: overlapping segments')
    base, top = min(a for a, *_ in segs), max(a + s for a, s, *_ in segs)
    if not any(a <= entry < a + f and p & 4 for a, _, f, p in segs) or entry & 3 or base & 0xfff:
        raise ValueError('kernel: entry not in an executable segment')
    if top - base > WINDOW_DEFAULT - MB2:
        raise ValueError(f'kernel: span {top - base:#x} exceeds 256 MiB - 2 MiB')
    return base, top, entry


def adt_tree(adt):
    def walk(at):
        nprops, nchildren = struct.unpack_from('<II', adt, at)
        at += 8
        props = {}
        for _ in range(nprops):
            key, length = struct.unpack_from('<32sI', adt, at)
            at += 36
            props[key.rstrip(b'\0').decode()] = adt[at:at + length]
            at += length + (-length % 4)
        kids = []
        for _ in range(nchildren):
            child, at = walk(at)
            kids.append(child)
        return (props, kids), at
    tree, end = walk(0)
    if end != len(adt):
        raise ValueError('ADT: trailing bytes')
    return tree


def child(node, name):
    return next((n for n in node[1] if n[0].get('name') == name.encode() + b'\0'), None)


def valid_trust(data):
    """DarwinBoot ValidTrustCaches; returns the set of CDHashes."""
    count = struct.unpack_from('<I', data)[0]
    if not 0 < count <= 128 or count > (len(data) - 4) // 4:
        raise ValueError('trust: module count')
    hashes = set()
    starts = list(struct.unpack_from(f'<{count}I', data, 4)) + [len(data)]
    for i in range(count):
        s, e = starts[i], starts[i + 1]
        if s < 4 + 4 * count or s & 3 or e > len(data) or e < s or e - s < 24 or struct.unpack_from('<I', data, s)[0] != 2:
            raise ValueError(f'trust: module {i} header')
        entries = struct.unpack_from('<I', data, s + 20)[0]
        if e - s != 24 + entries * 24:
            raise ValueError(f'trust: module {i} length')
        prev = None
        for k in range(entries):
            h = data[s + 24 + 24 * k:s + 48 + 24 * k]
            if not 1 <= h[20] <= 4 or (prev is not None and prev >= h[:20]):
                raise ValueError(f'trust: module {i} entry {k} type or order')
            prev = h[:20]
            hashes.add(h[:20].hex())
    return hashes


def seed_uuid(unixnu, data):
    sys.path.insert(0, str(Path(unixnu) / 'drivers/DarwinBoot/Test'))
    import packed_ramdisk
    _, extents = packed_ramdisk.regions(data)
    ids = {str(uuid.UUID(bytes=bytes(d[at + 240:at + 256]))).upper()
           for _, d in extents for at in range(0, len(d), 4096) if bytes(d[at + 32:at + 36]) == b'APSB'}
    if len(ids) != 1:
        raise ValueError('data: not exactly one APFS volume')
    return ids.pop()


def main():
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    for k in ('payload', 'manifest', 'kernel', 'addon', 'board', 'unixnu'):
        a.add_argument('--' + k, type=Path, required=True)
    a.add_argument('--json', type=Path)
    args = a.parse_args()
    results, failed = [], False

    def check(name, ok, detail=''):
        nonlocal failed
        failed |= not ok
        results.append(dict(check=name, ok=bool(ok), detail=detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}{': ' + detail if detail else ''}")

    board = tomllib.loads(args.board.read_text())
    manifest = json.loads(args.manifest.read_text())
    check('payload.img = payload.json', hashlib.sha256(args.payload.read_bytes()).hexdigest() == manifest['payload_sha256'],
          manifest['payload_sha256'][:16])
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        for name in ('kernel.macho', 'kernel.macho.adt', 'kernel.macho.trustcache', 'kernel.macho.gpuaddon',
                     'scratch-data.img', 'kernel.macho.vroot'):
            dst = Path(tmp) / name
            r = subprocess.run(['mcopy', '-n', '-i', str(args.payload), f'::/EFI/UniXNU/Payloads/{name}', str(dst)],
                               capture_output=True)
            if r.returncode == 0:
                files[name] = dst.read_bytes()
    check('payload files', {'kernel.macho', 'kernel.macho.adt'} <= set(files), ', '.join(sorted(files)))
    kernel = files['kernel.macho']
    check('stage-B kernel is the payload input', hashlib.sha256(args.kernel.read_bytes()).hexdigest() == manifest['kernel_sha256'],
          manifest['kernel_sha256'][:16])
    check('payload kernel = payload.json', hashlib.sha256(kernel).hexdigest() == manifest['payload_kernel_sha256'])
    try:
        kbase, kend, _ = kernel_span(kernel)
        check('kernel parses as DarwinBoot', True, f'span {kend - kbase:#x}')
    except ValueError as e:
        check('kernel parses as DarwinBoot', False, str(e))
        kbase = kend = 0

    adt = files['kernel.macho.adt']
    root = adt_tree(adt)
    chosen = child(root, 'chosen')
    mm = child(chosen, 'memory-map')
    u64 = lambda b: struct.unpack('<Q', b)[0]
    span = int(board['payload']['adt']['dram_size'], 0)
    check('ADT dram-base/size = DTS span', (u64(chosen[0]['dram-base']), u64(chosen[0]['dram-size'])) ==
          (int(board['payload']['adt']['dram_base'], 0), span), f"{u64(chosen[0]['dram-base']):#x}+{u64(chosen[0]['dram-size']):#x}")
    window = u64(chosen[0]['darwinboot-memory-size']) if 'darwinboot-memory-size' in chosen[0] else WINDOW_DEFAULT
    check('ADT window = board owned_memory_size', window == int(board['payload']['adt']['owned_memory_size'], 0), f'{window:#x}')
    check('ADT platform seed present (value not printed)', 'unique-chip-id' in chosen[0] and u64(chosen[0]['unique-chip-id']) != 0)
    slots = {'PackedRAMDisk': 'scratch-data.img', 'TrustCache': 'kernel.macho.trustcache', 'GpuAddon': 'kernel.macho.gpuaddon',
             'RootPolicies': 'kernel.macho.vroot'}
    for slot, f in slots.items():
        present = slot in mm[0]
        ok = present == (f in files) and (not present or mm[0][slot] == bytes(16))
        check(f'ADT memory-map {slot}', ok, 'zeroed slot, file present' if present else 'absent, no file')

    hashes = set()
    if 'kernel.macho.trustcache' in files:
        try:
            hashes = valid_trust(files['kernel.macho.trustcache'])
            check('trust cache valid (DarwinBoot rules)', True, f'{len(hashes)} hashes')
        except ValueError as e:
            check('trust cache valid (DarwinBoot rules)', False, str(e))
    addon = files.get('kernel.macho.gpuaddon')
    if addon is not None:
        check('addon = verified addon', addon == args.addon.read_bytes(), hashlib.sha256(addon).hexdigest()[:16])
        check('addon NGPUADD2 header', addon[:8] == b'NGPUADD2' and struct.unpack_from('<Q', addon, 16)[0] == len(addon))
        machos = [(n, d) for n, _, d in addon_files(addon) if d[:4] == b'\xcf\xfa\xed\xfe']
        uncovered = [n for n, d in machos if cdhash(d) not in hashes]
        check('addon Mach-O covered by the trust cache', machos and not uncovered,
              f'{len(machos)} Mach-O' + (f'; uncovered {uncovered}' if uncovered else ''))
    data = files.get('scratch-data.img')
    if data is not None:
        try:
            seed = seed_uuid(args.unixnu, data)
            in_kernel = set(UUID_RE.findall(kernel))
            check('Data seed UUID compiled into the kernel', seed.encode() in in_kernel,
                  'match' if seed.encode() in in_kernel else 'the kernel names a different Data volume: rebuild it with this seed')
        except ValueError as e:
            check('Data seed', False, str(e))

    # DarwinBoot's layout inside the window (Boot(): Args, Tree, Ramdisk, TrustCache, Addon, Policies)
    args_at = align(kend - kbase, 0x4000)
    tree_at = args_at + PAGE
    ram_at = align(tree_at + len(adt), PAGE)
    ram_bytes = align(len(data), PAGE) if data is not None else 0   # PackedRAMDisk: kept packed
    trust_at = ram_at + ram_bytes
    addon_at = align(trust_at + len(files.get('kernel.macho.trustcache', b'')), 0x4000)
    policy_at = align(addon_at + len(addon or b''), 0x4000)
    used = align(policy_at + len(files.get('kernel.macho.vroot', b'')), 0x4000)
    check('DarwinBoot layout fits the window', used <= window - MB2, f'used {used:#x} of {window:#x} (- 2 MiB)')
    layout = dict(kernel=(0, kend - kbase), args=args_at, adt=tree_at, ramdisk=ram_at, trust=trust_at, addon=addon_at,
                  policies=policy_at, used=used, window=window)
    print('layout (window offsets)', {k: (hex(v) if isinstance(v, int) else [hex(x) for x in v]) for k, v in layout.items()})
    if args.json:
        args.json.write_text(json.dumps(dict(results=results, layout={k: v if isinstance(v, int) else list(v)
                                                                       for k, v in layout.items()}), indent=2) + '\n')
    print('VERDICT', 'FAIL' if failed else 'PASS (offline payload; no boot)')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
