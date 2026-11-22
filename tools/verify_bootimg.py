#!/usr/bin/env python3
"""Check an Android boot image before `fastboot boot`: the header, the sizes, that the parts are inside the file, and
that it carries nothing it should not. Read only.

  verify_bootimg.py IMAGE              PASS (exit 0) or the problems (exit 1)
  verify_bootimg.py --unixnu IMAGE     also what a UniXNU pipa image must hold: BootShim + firmware (gzip, ARM64
                                       header), a FAT payload volume with EFI/UniXNU/unixnu.toml, kernel.macho (Mach-O),
                                       kernel.macho.adt, and a menu that passes tools/storage_safety.py
  verify_bootimg.py --self-test        checks this file against images it builds
"""
import gzip
import hashlib
import struct
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MAGIC = b'ANDROID!'


def pages(size, page):
    return -(-size // page)


def check(data):
    """(fields, problems)"""
    problems = []
    if data[:8] != MAGIC:
        return {}, ['no ANDROID! magic: not an Android boot image']
    version = struct.unpack_from('<I', data, 40)[0]
    if version in (0, 1, 2):
        kernel_size, kernel_addr, ramdisk_size, _, second_size, _, _, page = struct.unpack_from('<8I', data, 8)
        fields = {'header_version': version, 'page_size': page, 'kernel_size': kernel_size,
                  'ramdisk_size': ramdisk_size, 'second_size': second_size, 'kernel_addr': hex(kernel_addr)}
        if page not in (2048, 4096, 8192, 16384):
            problems.append(f'page size {page} is not one ABL takes')
        sizes = [kernel_size, ramdisk_size, second_size]
        if version >= 1:
            recovery_dtbo = struct.unpack_from('<I', data, 1632)[0]
            sizes.append(recovery_dtbo)
        if version == 2:
            sizes.append(struct.unpack_from('<I', data, 1648)[0])
        end = page * (1 + sum(pages(s, page) for s in sizes))
    elif version in (3, 4):
        kernel_size, ramdisk_size = struct.unpack_from('<II', data, 8)
        page = 4096
        fields = {'header_version': version, 'page_size': page, 'kernel_size': kernel_size,
                  'ramdisk_size': ramdisk_size}
        sizes = [kernel_size, ramdisk_size]
        if version == 4:
            sizes.append(struct.unpack_from('<I', data, 1580)[0])
        end = page * (1 + sum(pages(s, page) for s in sizes))
    else:
        return {'header_version': version}, [f'header version {version} unknown']
    if kernel_size == 0:
        problems.append('no kernel in the image')
    if end > len(data):
        problems.append(f'the header says {end} bytes, the file has {len(data)}: truncated')
    kernel = data[page:page + kernel_size]
    if kernel[56:60] == b'ARM\x64':
        fields['kernel'] = 'arm64 Image'
    elif kernel[:2] == b'MZ':
        fields['kernel'] = 'PE/EFI image'
    fields['sha256'] = hashlib.sha256(data).hexdigest()
    for marker in (b'IM4P', b'IMG4', b'img4'):
        if marker in data:
            problems.append(f'{marker.decode()} found: an Apple-signed file is inside; it must not be published')
    return fields, problems


def parts(data, fields):
    page = fields['page_size']
    kernel = data[page:page + fields['kernel_size']]
    start = page * (1 + pages(fields['kernel_size'], page))
    return kernel, data[start:start + fields['ramdisk_size']]


# uefi-pipa's boot image values (EsaiJJ/UniXNU-pipa porting record: base 0x10000000, kernel_offset 0x8000, page 2048, v1)
PIPA_KERNEL_ADDR, PIPA_PAGE = 0x10008000, 2048


def check_unixnu(data, fields):
    """Problems of a UniXNU pipa boot image beyond its header; the menu it carries is returned as well."""
    from fat_reader import Fat, FatError
    import storage_safety
    problems, menu = [], None
    if fields.get('header_version') not in (0, 1, 2):
        return ['a UniXNU pipa image is an Android boot image of header version 0-2'], None
    if fields['page_size'] != PIPA_PAGE or fields.get('kernel_addr') != hex(PIPA_KERNEL_ADDR):
        problems.append(f'page {fields["page_size"]} / kernel at {fields.get("kernel_addr")}: uefi-pipa packs page '
                        f'{PIPA_PAGE}, kernel at {PIPA_KERNEL_ADDR:#x}')
    kernel, ramdisk = parts(data, fields)
    if kernel[:2] != b'\x1f\x8b':
        problems.append('the kernel is not gzip (BootShim + firmware volume)')
    else:
        try:
            shim = gzip.decompress(kernel)
            if shim[56:60] != b'ARM\x64':
                problems.append('the decompressed kernel has no ARM64 image header (BootShim)')
            fields['firmware_bytes'] = len(shim)
        except (OSError, EOFError) as error:
            problems.append(f'the kernel does not decompress: {error}')
    try:
        fat = Fat(ramdisk)
        files = fat.files()
        fields['payload_files'] = len(files)
        for needed in ('EFI/UniXNU/unixnu.toml', 'EFI/UniXNU/Payloads/kernel.macho', 'EFI/UniXNU/Payloads/kernel.macho.adt'):
            if needed not in files:
                problems.append(f'payload volume lacks {needed}')
        if 'EFI/UniXNU/Payloads/kernel.macho' in files and fat.read('EFI/UniXNU/Payloads/kernel.macho')[:4] != b'\xcf\xfa\xed\xfe':
            problems.append('kernel.macho is not a 64-bit Mach-O')
        if 'EFI/UniXNU/unixnu.toml' in files:
            menu = tomllib.loads(fat.read('EFI/UniXNU/unixnu.toml').decode())
            verdict, _, findings = storage_safety.judge({'menu': menu, 'board': {}})
            problems += [f'menu: {text}' for level, text in findings if level == 'FAIL']
    except (FatError, tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        problems.append(f'payload volume: {error}')
    return problems, menu


def build_v0(kernel, ramdisk=b'', page=4096, kernel_addr=0x8000):
    header = bytearray(page)
    struct.pack_into('<8s8I', header, 0, MAGIC, len(kernel), kernel_addr, len(ramdisk), 0x01000000, 0, 0, 0x100, page)
    pad = lambda b: b + b'\0' * (pages(len(b), page) * page - len(b))
    return bytes(header) + pad(kernel) + pad(ramdisk)


def self_test():
    arm64 = bytearray(4096)
    arm64[56:60] = b'ARM\x64'
    fields, problems = check(build_v0(bytes(arm64)))
    assert not problems and fields['kernel'] == 'arm64 Image', (fields, problems)
    assert check(b'NOTANDROID' + b'\0' * 100)[1]
    assert any('truncated' in p for p in check(build_v0(bytes(arm64), b'x' * 9000)[:-5000])[1])
    assert any('IM4P' in p for p in check(build_v0(bytes(arm64) + b'IM4P'))[1])
    assert any('no kernel' in p for p in check(build_v0(b''))[1])
    print('verify_bootimg: self-test ok (5 cases)')
    return 0


def main(argv):
    if argv[1:] == ['--self-test']:
        return self_test()
    unixnu = '--unixnu' in argv
    args = [a for a in argv[1:] if a != '--unixnu']
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    data = open(args[0], 'rb').read()
    fields, problems = check(data)
    if unixnu and not problems:
        more, _ = check_unixnu(data, fields)
        problems += more
    for key, value in fields.items():
        print(f'{key:15} {value}')
    for problem in problems:
        print(f'FAIL  {problem}')
    print('PASS' if not problems else 'FAIL')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
