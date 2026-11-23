#!/usr/bin/env python3
"""original-static-system.bundle from the IPSW's two trust-cache members, without the volumes.

UniXNU's scripts/build-original-system-trust.py reads Cryptex1,SystemTrustCache from a local IPSW zip and the static
module from a mounted root volume (.cache/firmware/target-volumes/static-trustcache.bin). Both modules are also IPSW
members, IM4P-wrapped: StaticTrustCache and Cryptex1,SystemTrustCache (`unixnu ipsw fetch` reads only those). This
unwraps them and applies the same checks and the same pinned digests, and writes the same bundle layout:
  <u32 2><u32 12><u32 12+len(static)> static system
Nothing is changed or added; a digest mismatch stops it. The output is Apple's data: it stays local / on the runner.

  original_trust.py --static Firmware/044-76040-038.dmg.trustcache --system Firmware/044-76034-038.dmg.trustcache --out DIR
"""
import argparse, hashlib, json, struct, sys
from pathlib import Path

# build-original-system-trust.py (UniXNU 62f203c): static, system
EXPECTED = ('da88460e6e513438d5307e5c526f76497a74754476a24da29f239f0c90120fc2',
            'd121ba89167e03aafd00fa687c30cd8ebc4ccafd10c1408adb2ba3de12403651')


def der(data, at):
    if at + 2 > len(data):
        raise ValueError('truncated DER')
    tag, size = data[at:at + 2]
    at += 2
    if size & 128:
        count = size & 127
        if not 0 < count <= 4 or at + count > len(data):
            raise ValueError('invalid DER length')
        size = int.from_bytes(data[at:at + count], 'big')
        at += count
    if at + size > len(data):
        raise ValueError('DER exceeds input')
    return tag, data[at:at + size], at + size


def im4p_payload(original, label):
    tag, sequence, end = der(original, 0)
    fields, cursor = [], 0
    while cursor < len(sequence):
        kind, data, cursor = der(sequence, cursor)
        fields.append((kind, data))
    # IM4P: IA5 "IM4P", IA5 type, IA5 description, OCTET STRING payload (a trust cache has no KBAG/compression)
    if tag != 0x30 or end != len(original) or [k for k, _ in fields] != [0x16, 0x16, 0x16, 4] or fields[0][1] != b'IM4P':
        raise ValueError(f'{label}: not an uncompressed trust-cache IM4P')
    return fields[1][1].decode(), fields[3][1]


def module_ok(module):
    return (len(module) >= 24 and struct.unpack_from('<I', module)[0] == 2
            and len(module) == 24 + struct.unpack_from('<I', module, 20)[0] * 24)


def build(static_im4p, system_im4p):
    modules = []
    for (label, raw), digest in zip((('static', static_im4p), ('system', system_im4p)), EXPECTED):
        kind, module = im4p_payload(raw, label)   # 'trst' (static), 'trcs' (cryptex): the pinned digest decides
        if hashlib.sha256(module).hexdigest() != digest or not module_ok(module):
            raise ValueError(f'{label}: not the complete pinned version-2 trust module ({hashlib.sha256(module).hexdigest()})')
        modules.append(module)
    static, system = modules
    return struct.pack('<3I', 2, 12, 12 + len(static)) + static + system


def main():
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('--static', type=Path, required=True)
    a.add_argument('--system', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True, help='directory: original-static-system.bundle + inputs.json')
    args = a.parse_args()
    static_raw, system_raw = args.static.read_bytes(), args.system.read_bytes()
    try:
        bundle = build(static_raw, system_raw)
    except ValueError as e:
        sys.exit(f'original_trust: {e}')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'original-static-system.bundle').write_bytes(bundle)
    (args.out / 'inputs.json').write_text(json.dumps(dict(
        original_static_sha256=EXPECTED[0], original_system_sha256=EXPECTED[1],
        static_im4p_sha256=hashlib.sha256(static_raw).hexdigest(), original_im4p_sha256=hashlib.sha256(system_raw).hexdigest(),
        bundle_sha256=hashlib.sha256(bundle).hexdigest(), source='IPSW members StaticTrustCache + Cryptex1,SystemTrustCache',
        own_code_entries_added=False, original_modules_modified=False, apple_personalization_claimed=False), indent=2) + '\n')
    print('original-static-system.bundle', hashlib.sha256(bundle).hexdigest())


if __name__ == '__main__':
    main()
