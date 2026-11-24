#!/usr/bin/env python3
"""Where pipa's ABL puts a boot image in memory, and whether it accepts it -- offline, from the rules read out of the
stock bootloader itself (docs/MODE-B.md, "ABL, dari biner").

  abl_layout.py --boot BOOT.img [--vendor-boot VENDOR_BOOT.img] [--json OUT]
  abl_layout.py --boot STOCK_BOOT.img --vendor-boot STOCK_VENDOR_BOOT.img --b5 --fd SILICIUM_UEFI.fd --payload payload.img
                [--shim-bytes N]

Evidence (official OTA OS2.0.16.0.UMZMIXM, extracted with tools/ota_extract.py; never committed):
  - xbl: uefiplat.cfg  `0xA0000000, 0x10000000, "Kernel"` -- the region ABL reads back as the UEFI variables
    KernelBaseAddr / KernelSize (LinuxLoader GetVariable at .text 0x16550/0x16598). The fallback when the variables
    are absent is base + 0x5600000 (constant at 0x47c98); with the variables the region is the one below.
  - abl LinuxLoader (.text 0x16658..0x166b8): KernelLoadAddr = base + 0x80000 for an arm64 Image (0x8000 otherwise);
    RamdiskLoadAddr = region end - ALIGN(ramdisk + vendor ramdisk, page) - page; DeviceTreeLoadAddr = RamdiskLoadAddr
    - page - 2 MiB; DeviceTreeLoadAddr <= KernelLoadAddr is refused.
  - abl LinuxLoader (.text 0x169c0..0x16a20): an Image with the "ARMd" magic must have image_size (header +0x10) <=
    DeviceTreeLoadAddr - KernelLoadAddr, else "DTB header can get corrupted due to runtime kernel size".
  - abl (.text 0x379c4): an image larger than the boot partition is refused ("Image is too large for the partition");
    boot_b of this unit is 0xC000000 (fastboot getvar, 2026-11-16).
  - "Error: Ramdisk size is over the limit" (.text 0x17000) is only an address overflow check, no size limit.
Not known offline: fastboot max-download-size (a runtime value); the region of the newer bootloader the tablet now runs
(OS4.0.8.0) -- the rules are those of OS2.0.16 and must be confirmed against that ABL before any boot.
"""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

REGION_BASE = 0xA0000000      # xbl uefiplat.cfg "Kernel"
REGION_SIZE = 0x10000000
BOOT_B_BYTES = 0xC000000      # fastboot getvar partition-size:boot_b, 2026-11-16
TWO_MIB = 0x200000


def align(n, a):
    return (n + a - 1) // a * a


def parse_boot(data):
    if data[:8] != b'ANDROID!':
        raise ValueError('not an Android boot image')
    version = struct.unpack_from('<I', data, 40)[0]
    if version >= 3:
        kernel_size, ramdisk_size = struct.unpack_from('<II', data, 8)
        page, header = 4096, 4096
        kernel = data[header:header + kernel_size]
        ramdisk_off = header + align(kernel_size, page)
        bootconfig = 0
        if version == 4:
            bootconfig = 0   # bootconfig lives in vendor_boot v4
        return {'version': version, 'page': page, 'kernel': kernel, 'ramdisk_size': ramdisk_size,
                'ramdisk_offset': ramdisk_off, 'bytes': len(data), 'bootconfig': bootconfig}
    kernel_size, _, ramdisk_size = struct.unpack_from('<III', data, 8)
    page = struct.unpack_from('<I', data, 36)[0]
    kernel = data[page:page + kernel_size]
    return {'version': version, 'page': page, 'kernel': kernel, 'ramdisk_size': ramdisk_size,
            'ramdisk_offset': page + align(kernel_size, page), 'bytes': len(data), 'bootconfig': 0}


def parse_vendor_boot(data):
    if data[:8] != b'VNDRBOOT':
        raise ValueError('not a vendor_boot image')
    version, page = struct.unpack_from('<II', data, 8)
    vendor_ramdisk = struct.unpack_from('<I', data, 24)[0]
    bootconfig = 0
    if version >= 4:
        # v4: after dtb_size(4) dtb_addr(8): table size, entry num, entry size, bootconfig size
        off = 8 + 4 + 4 + 4 + 4 + 4 + 512 + 4 + 4 + 8
        bootconfig = struct.unpack_from('<I', data, off + 12)[0]
    return {'version': version, 'page': page, 'vendor_ramdisk_size': vendor_ramdisk, 'bootconfig': bootconfig}


def kernel_runtime(kernel):
    """(kind, bytes ABL places at KernelLoadAddr, Image header image_size or None)."""
    if kernel[:2] == b'\x1f\x8b':
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = d.decompress(kernel) + d.flush()
        size = struct.unpack_from('<Q', out, 16)[0] if out[56:60] == b'ARMd' else None
        return 'gzip', len(out), size
    if kernel[56:60] == b'ARMd':
        return 'Image', len(kernel), struct.unpack_from('<Q', kernel, 16)[0]
    return 'raw', len(kernel), None


def layout(boot, vendor=None, region_base=REGION_BASE, region_size=REGION_SIZE, partition=BOOT_B_BYTES):
    page = vendor['page'] if vendor else boot['page']
    ramdisks = boot['ramdisk_size'] + (vendor['vendor_ramdisk_size'] + vendor['bootconfig'] if vendor else 0)
    kind, placed, image_size = kernel_runtime(boot['kernel'])
    kernel_addr = region_base + (0x80000 if kind in ('Image', 'gzip') and image_size is not None else 0x8000)
    end = region_base + region_size
    ramdisk_addr = end - align(ramdisks, page) - page
    dtb_addr = ramdisk_addr - page - TWO_MIB
    room = dtb_addr - kernel_addr
    checks = []
    say = lambda ok, text: checks.append(('PASS' if ok else 'FAIL', text))
    say(boot['bytes'] <= partition, f'image {boot["bytes"]} B <= boot partition {partition} B')
    say(dtb_addr > kernel_addr, f'DeviceTreeLoadAddr {dtb_addr:#x} above KernelLoadAddr {kernel_addr:#x}')
    if image_size is not None:
        say(image_size <= room, f'{kind} image_size {image_size:#x} <= DTB - kernel {room:#x}')
    say(placed <= room, f'{kind} bytes placed at the kernel address {placed:#x} <= DTB - kernel {room:#x}')
    return {'kind': kind, 'kernel_addr': kernel_addr, 'dtb_addr': dtb_addr, 'ramdisk_addr': ramdisk_addr,
            'ramdisk_bytes': ramdisks, 'kernel_room': room, 'image_size': image_size, 'placed': placed,
            'page': page, 'checks': checks}


def b5_budget(boot, vendor, fd_bytes, payload_bytes, shim_bytes=0x10000, partition=BOOT_B_BYTES):
    """The B5 boot image: the stock header and ramdisk; the kernel = the stock Image file, then the shim, the FD and the
    payload, each page aligned right after the Image's file bytes. They may lie inside the Image's runtime size (its
    bss): on the Android path the shim has already branched into Linux before Linux clears its bss, and the payload is
    not needed there; on the menu path Linux never runs. The header image_size is raised to cover them (ABL checks it,
    .text 0x169c0; Linux reserves [_text, _end) from its own symbols, not from the header). Sizes only: nothing is built."""
    page = 4096
    kind, placed, image_size = kernel_runtime(boot['kernel'])
    if kind != 'Image':
        raise ValueError('B5 needs the stock arm64 Image (not compressed)')
    shim_off = align(len(boot['kernel']), page)
    fd_off = align(shim_off + shim_bytes, page)
    payload_off = align(fd_off + fd_bytes, page)
    kernel_bytes = payload_off + payload_bytes
    new_image_size = max(image_size, align(kernel_bytes, page))
    image = page + align(kernel_bytes, page) + align(boot['ramdisk_size'], page)
    ramdisks = boot['ramdisk_size'] + vendor['vendor_ramdisk_size'] + vendor['bootconfig']
    end = REGION_BASE + REGION_SIZE
    dtb_addr = end - align(ramdisks, vendor['page']) - 2 * vendor['page'] - TWO_MIB
    room = dtb_addr - (REGION_BASE + 0x80000)
    return {'image_size_stock': image_size, 'shim_offset': shim_off, 'fd_offset': fd_off, 'payload_offset': payload_off,
            'kernel_bytes': kernel_bytes, 'new_image_size': new_image_size, 'boot_image_bytes': image,
            'partition': partition, 'kernel_room': room,
            'fits_partition': image <= partition, 'fits_abl': new_image_size <= room and kernel_bytes <= room,
            'max_payload': min(partition - page - align(boot['ramdisk_size'], page) - payload_off,
                               room - payload_off) // 0x100000 * 0x100000}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--boot', type=Path, required=True)
    ap.add_argument('--vendor-boot', type=Path)
    ap.add_argument('--partition-bytes', type=lambda v: int(v, 0), default=BOOT_B_BYTES)
    ap.add_argument('--b5', action='store_true')
    ap.add_argument('--fd', type=Path)
    ap.add_argument('--payload', type=Path)
    ap.add_argument('--shim-bytes', type=lambda v: int(v, 0), default=0x10000)
    ap.add_argument('--json', type=Path)
    a = ap.parse_args(argv)
    boot = parse_boot(a.boot.read_bytes())
    vendor = parse_vendor_boot(a.vendor_boot.read_bytes()) if a.vendor_boot else None
    if a.b5:
        if not (vendor and a.fd and a.payload):
            ap.error('--b5 needs --vendor-boot, --fd and --payload')
        r = b5_budget(boot, vendor, a.fd.stat().st_size, a.payload.stat().st_size, a.shim_bytes, a.partition_bytes)
        for k, v in r.items():
            print(f'{k:20} {v:#x}' if isinstance(v, int) and not isinstance(v, bool) else f'{k:20} {v}')
        ok = r['fits_partition'] and r['fits_abl']
        print('B5 BUDGET ' + ('PASS' if ok else 'FAIL'))
        if a.json:
            a.json.write_text(json.dumps(r, indent=2) + '\n')
        return 0 if ok else 1
    r = layout(boot, vendor, partition=a.partition_bytes)
    print(f'boot v{boot["version"]} page {r["page"]:#x}, kernel {r["kind"]}: load {r["kernel_addr"]:#x}, '
          f'DTB {r["dtb_addr"]:#x}, ramdisk {r["ramdisk_addr"]:#x} ({r["ramdisk_bytes"]} B)')
    for level, text in r['checks']:
        print(f'{level:5} {text}')
    bad = any(level == 'FAIL' for level, _ in r['checks'])
    print('ABL LAYOUT ' + ('FAIL' if bad else 'PASS'))
    if a.json:
        a.json.write_text(json.dumps({k: v for k, v in r.items()}, indent=2) + '\n')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
