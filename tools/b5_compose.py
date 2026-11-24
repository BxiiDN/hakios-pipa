#!/usr/bin/env python3
"""Compose the B5 boot image (docs/MODE-B.md, B5) -- files only, nothing is flashed or booted.

  b5_compose.py --android-boot boot.img --mode-a-boot boot-mode-a.img --payload payload.img --shim shim.bin --out b5.img
  b5_compose.py ... --bootshim-blob FILE         (tests: a raw blob in place of BootShim + firmware)

The kernel of the Android boot image (header v3) becomes, page aligned:
  [Android Image, code0 = "b shim"] [shim, HKB5 descriptor filled] [BootShim + firmware, from the MODE A image's gzip kernel]
  [payload volume]
The Image's original code0 is kept in the descriptor (a "b" is re-encoded for its new place; the usual EFI-stub
"add x13, x18, #0x16" is copied as it is; anything else is refused), followed by "b Image+4". The header's image_size
grows to cover everything so ABL places the ramdisk and device tree after it (tools/abl_layout.py). The ramdisk, the
header's other fields and os_version stay the stock ones. Every limit is checked: boot partition, ABL kernel room,
1 MiB-free margins are reported, payload a whole number of sectors.
"""
import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import abl_layout  # noqa: E402

PAGE = 4096
EFI_STUB_CODE0 = 0x91005a4d          # add x13, x18, #0x16 ("MZ")
DESC = b'HKB5'


class ComposeError(Exception):
    pass


def align(n, a=PAGE):
    return (n + a - 1) // a * a


def branch(from_off, to_off):
    delta = to_off - from_off
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise ComposeError('branch out of range')
    return 0x14000000 | ((delta >> 2) & 0x3ffffff)


def relocate_code0(code0, new_off):
    if code0 == EFI_STUB_CODE0:
        return code0
    if code0 >> 26 == 0b000101:                           # b imm26
        imm = code0 & 0x3ffffff
        if imm & (1 << 25):
            imm -= 1 << 26
        return branch(new_off, imm * 4)                   # the same target (offset 0 + imm*4), from its new place
    raise ComposeError(f'Image code0 0x{code0:08x} is neither the EFI stub "add" nor a "b": not composed')


def bootshim_from_mode_a(img):
    if img[:8] != b'ANDROID!':
        raise ComposeError('MODE A image is not an Android boot image')
    ks = struct.unpack_from('<I', img, 8)[0]
    page = struct.unpack_from('<I', img, 36)[0]
    k = img[page:page + ks]
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    blob = d.decompress(k) + d.flush()                   # BootShim + firmware; the appended DTB is d.unused_data
    if blob[56:60] != b'ARMd':
        raise ComposeError('MODE A kernel is not BootShim (no ARM64 Image header)')
    return blob


def compose(android_boot, bootshim, payload, shim):
    if android_boot[:8] != b'ANDROID!' or struct.unpack_from('<I', android_boot, 40)[0] not in (3, 4):
        raise ComposeError('Android boot image must be header v3 or v4')
    ks, rs = struct.unpack_from('<II', android_boot, 8)
    image = bytearray(android_boot[PAGE:PAGE + ks])
    ramdisk = android_boot[PAGE + align(ks):PAGE + align(ks) + rs]
    if image[56:60] != b'ARMd':
        raise ComposeError('Android kernel is not an uncompressed arm64 Image')
    if len(payload) == 0 or len(payload) % 512:
        raise ComposeError('payload is not a whole number of 512-byte sectors')
    desc = shim.find(DESC)
    if desc < 0 or desc % 8:
        raise ComposeError('shim has no HKB5 descriptor')
    shim_off = align(len(image))
    bootshim_off = align(shim_off + len(shim))
    payload_off = align(bootshim_off + len(bootshim))
    total = payload_off + len(payload)
    code0 = struct.unpack_from('<I', image, 0)[0]
    s = bytearray(shim)
    orig_at = shim_off + desc + 40
    struct.pack_into('<QQQQ', s, desc + 8, shim_off, bootshim_off, payload_off, len(payload))
    struct.pack_into('<I', s, desc + 40, relocate_code0(code0, orig_at))
    struct.pack_into('<I', s, desc + 44, branch(orig_at + 4, 4))
    struct.pack_into('<I', image, 0, branch(0, shim_off))
    image_size = struct.unpack_from('<Q', image, 16)[0]
    struct.pack_into('<Q', image, 16, max(image_size, align(total)))
    kernel = bytes(image) + b'\0' * (shim_off - len(image)) + bytes(s) + b'\0' * (bootshim_off - shim_off - len(s)) + \
        bootshim + b'\0' * (payload_off - bootshim_off - len(bootshim)) + payload
    header = bytearray(android_boot[:PAGE])
    struct.pack_into('<I', header, 8, len(kernel))
    out = bytes(header) + kernel + b'\0' * (align(len(kernel)) - len(kernel)) + ramdisk + b'\0' * (align(rs) - rs)
    return out, {'shim_offset': shim_off, 'bootshim_offset': bootshim_off, 'payload_offset': payload_off,
                 'kernel_bytes': len(kernel), 'image_size': max(image_size, align(total)), 'boot_image_bytes': len(out),
                 'code0': f'0x{code0:08x}'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--android-boot', type=Path, required=True)
    ap.add_argument('--mode-a-boot', type=Path)
    ap.add_argument('--bootshim-blob', type=Path)
    ap.add_argument('--payload', type=Path, required=True)
    ap.add_argument('--shim', type=Path, required=True)
    ap.add_argument('--vendor-boot', type=Path, help='for the ABL layout check (defaults to no vendor ramdisk)')
    ap.add_argument('--partition-bytes', type=lambda v: int(v, 0), default=abl_layout.BOOT_B_BYTES)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        if not (a.mode_a_boot or a.bootshim_blob):
            raise ComposeError('give --mode-a-boot (or --bootshim-blob)')
        bootshim = a.bootshim_blob.read_bytes() if a.bootshim_blob else bootshim_from_mode_a(a.mode_a_boot.read_bytes())
        out, info = compose(a.android_boot.read_bytes(), bootshim, a.payload.read_bytes(), a.shim.read_bytes())
        vendor = abl_layout.parse_vendor_boot(a.vendor_boot.read_bytes()) if a.vendor_boot else None
        layout = abl_layout.layout(abl_layout.parse_boot(out), vendor, partition=a.partition_bytes)
        bad = [t for level, t in layout['checks'] if level == 'FAIL']
        if bad:
            raise ComposeError('ABL would refuse it: ' + bad[0])
    except ComposeError as e:
        print(f'REFUSED {e}')
        return 1
    a.out.write_bytes(out)
    for k, v in info.items():
        print(f'{k:18} {v:#x}' if isinstance(v, int) else f'{k:18} {v}')
    print(f'margin to the boot partition: {a.partition_bytes - len(out)} B')
    print(f'COMPOSED {a.out} sha256 {hashlib.sha256(out).hexdigest()} (a file only: nothing was flashed)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
