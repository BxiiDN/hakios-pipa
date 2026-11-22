#!/usr/bin/env python3
"""The final boot image is made of exactly the pieces that were built and checked -- not merely pieces whose names or
strings look right.

  image_consistency.py --image BOOT.img --kernel kernel.macho --firmware SILICIUM_UEFI.fd --payload payload.img
                       [--manifest MANIFEST.json]

Checks, each PASS or FAIL:
  - the image's ramdisk is byte-for-byte payload.img;
  - the payload volume's EFI/UniXNU/Payloads/kernel.macho is byte-for-byte kernel.macho;
  - the image's kernel (gzip of BootShim + firmware) contains the firmware volume whole, at the end;
  - with --manifest: the kernel, firmware, payload and image digests are the ones the build recorded.
Exit 0 only when every check passes.
"""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_bootimg as vb  # noqa: E402
from fat_reader import Fat, FatError  # noqa: E402


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(image, kernel, firmware, payload, manifest=None):
    results = []
    say = lambda ok, text: results.append(('PASS' if ok else 'FAIL', text))
    fields, problems = vb.check(image)
    if problems:
        return [('FAIL', f'image header: {p}') for p in problems]
    boot_kernel, ramdisk = vb.parts(image, fields)
    say(ramdisk == payload, f'ramdisk is payload.img ({digest(ramdisk)[:16]} / {digest(payload)[:16]})')
    try:
        inner = Fat(ramdisk).read('EFI/UniXNU/Payloads/kernel.macho')
        say(inner == kernel, f'payload kernel.macho is the built kernel ({digest(inner)[:16]} / {digest(kernel)[:16]})')
    except FatError as error:
        say(False, f'payload volume: {error}')
    try:
        shim_fv = gzip.decompress(boot_kernel)
        say(shim_fv.endswith(firmware) and len(shim_fv) > len(firmware),
            f'image kernel = BootShim ({len(shim_fv) - len(firmware)} B) + the built firmware ({digest(firmware)[:16]})')
    except (OSError, EOFError) as error:
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
    a = ap.parse_args(argv)
    manifest = json.loads(a.manifest.read_text()) if a.manifest else None
    results = check(a.image.read_bytes(), a.kernel.read_bytes(), a.firmware.read_bytes(), a.payload.read_bytes(), manifest)
    for level, text in results:
        print(f'{level:5} {text}')
    bad = any(level == 'FAIL' for level, _ in results)
    print('IMAGE CONSISTENT' if not bad else 'IMAGE NOT CONSISTENT')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
