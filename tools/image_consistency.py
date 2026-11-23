#!/usr/bin/env python3
"""The final boot image is made of exactly the pieces that were built and checked -- not merely pieces whose names or
strings look right.

  image_consistency.py --image BOOT.img --kernel kernel.macho --firmware SILICIUM_UEFI.fd --payload payload.img
                       [--manifest MANIFEST.json]

Checks, each PASS or FAIL:
  - the image's ramdisk is byte-for-byte payload.img;
  - the payload volume's EFI/UniXNU/Payloads/kernel.macho is byte-for-byte kernel.macho;
  - the image's kernel (gzip of BootShim + firmware) contains the firmware volume whole, at the end;
  - with --manifest: the kernel, firmware, payload and image digests are the ones the build recorded;
  - the image is not larger than the boot partition (--max-bytes, default the 8 GB unit's boot_b 0xC000000): ABL refuses a
    larger image even for `fastboot boot` and marks the slot unbootable (2026-11-17).
Exit 0 only when every check passes.
"""
import argparse
import gzip
import zlib
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_bootimg as vb  # noqa: E402
from fat_reader import Fat, FatError  # noqa: E402


BOOT_B_BYTES = 0xC000000   # boot_b of the 8 GB unit, fastboot getvar partition-size (2026-11-16)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(image, kernel, firmware, payload, manifest=None, max_bytes=BOOT_B_BYTES, dtb=None):
    results = []
    say = lambda ok, text: results.append(('PASS' if ok else 'FAIL', text))
    say(len(image) <= max_bytes, f'image {len(image)} B fits the boot partition ({max_bytes} B)')
    fields, problems = vb.check(image)
    # verify_bootimg's IMG4/img4 markers guard publication. A pipa image always carries the Apple kernel, whose own strings
    # name img4 (AppleImage4, trust-cache loading): those are a reason never to publish the image, not an inconsistency.
    # Only markers that all come from the given kernel are set aside; IM4P anywhere, or a marker outside it, stays FAIL.
    marker = lambda m: f'{m} found: an Apple-signed file is inside; it must not be published'
    kernel_only = [marker(m) for m in ('IMG4', 'img4') if marker(m) in problems and b'IM4P' not in image
                   and image.count(m.encode()) == kernel.count(m.encode())]
    problems = [p for p in problems if p not in kernel_only]
    if problems:
        return [('FAIL', f'image header: {p}') for p in problems]
    if kernel_only:
        results.append(('NOTE', 'IMG4/img4 only inside the Apple kernel (its strings): a local image, never to be published'))
    boot_kernel, ramdisk = vb.parts(image, fields)
    say(ramdisk == payload, f'ramdisk is payload.img ({digest(ramdisk)[:16]} / {digest(payload)[:16]})')
    try:
        inner = Fat(ramdisk).read('EFI/UniXNU/Payloads/kernel.macho')
        say(inner == kernel, f'payload kernel.macho is the built kernel ({digest(inner)[:16]} / {digest(kernel)[:16]})')
    except FatError as error:
        say(False, f'payload volume: {error}')
    # UniXNU bootimg.py: kernel = gzip(BootShim + FD) followed by the device tree (Image.gz-dtb); only the first gzip
    # member is the shim, whatever follows must be one FDT (and the given one, with --dtb).
    try:
        inflate = zlib.decompressobj(16 + zlib.MAX_WBITS)
        shim_fv = inflate.decompress(boot_kernel) + inflate.flush()
        if not inflate.eof:
            raise EOFError('truncated gzip stream')
        say(shim_fv.endswith(firmware) and len(shim_fv) > len(firmware),
            f'image kernel = BootShim ({len(shim_fv) - len(firmware)} B) + the built firmware ({digest(firmware)[:16]})')
        tail = inflate.unused_data
        if tail:
            fdt = tail[:4] == b'\xd0\x0d\xfe\xed' and len(tail) >= 8 and int.from_bytes(tail[4:8], 'big') == len(tail)
            say(fdt, f'appended device tree: {len(tail)} B, one FDT ({digest(tail)[:16]})')
            if dtb is not None:
                say(tail == dtb, f'appended device tree is the given --dtb ({digest(dtb)[:16]})')
        elif dtb is not None:
            say(False, 'no device tree is appended to the image kernel, but --dtb was given')
    except (OSError, EOFError, zlib.error) as error:
        say(False, f'image kernel does not decompress: {error}')
    if manifest is not None:
        recorded = {Path(e['path']).name: e['sha256'] for e in manifest.get('unixnu_files', []) + manifest.get('uefi_files', [])}
        for name, data in (('kernel.macho', kernel), ('payload.img', payload), ('SILICIUM_UEFI.fd', firmware)):
            want = recorded.get(name)
            say(want == digest(data), f'{name} is the one the build recorded ({(want or "not recorded")[:16]})')
        img = [h for n, h in recorded.items() if n.endswith('.img') and n not in ('payload.img',)]
        say(digest(image) in img, f'boot image is one the build recorded ({digest(image)[:16]})')
    return results


def main(argv):
    ap = argparse.ArgumentParser()
    for name in ('image', 'kernel', 'firmware', 'payload'):
        ap.add_argument(f'--{name}', type=Path, required=True)
    ap.add_argument('--manifest', type=Path)
    ap.add_argument('--max-bytes', type=lambda v: int(v, 0), default=BOOT_B_BYTES)
    ap.add_argument('--dtb', type=Path, help='the device tree bootimg appended (pipa: uefi-pipa Resources/DTBs/pipa.dtb)')
    a = ap.parse_args(argv)
    manifest = json.loads(a.manifest.read_text()) if a.manifest else None
    results = check(a.image.read_bytes(), a.kernel.read_bytes(), a.firmware.read_bytes(), a.payload.read_bytes(), manifest, a.max_bytes,
                    a.dtb.read_bytes() if a.dtb else None)
    for level, text in results:
        print(f'{level:5} {text}')
    bad = any(level == 'FAIL' for level, _ in results)
    print('IMAGE CONSISTENT' if not bad else 'IMAGE NOT CONSISTENT')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
