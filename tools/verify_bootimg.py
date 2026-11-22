#!/usr/bin/env python3
"""Check an Android boot image before `fastboot boot`: the header, the sizes, that the parts are inside the file, and
that it carries nothing it should not. Read only.

  verify_bootimg.py IMAGE        PASS (exit 0) or the problems (exit 1)
  verify_bootimg.py --self-test  checks this file against images it builds
"""
import hashlib
import struct
import sys

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


def build_v0(kernel, ramdisk=b'', page=4096):
    header = bytearray(page)
    struct.pack_into('<8s8I', header, 0, MAGIC, len(kernel), 0x8000, len(ramdisk), 0x01000000, 0, 0, 0x100, page)
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
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    data = open(argv[1], 'rb').read()
    fields, problems = check(data)
    for key, value in fields.items():
        print(f'{key:15} {value}')
    for problem in problems:
        print(f'FAIL  {problem}')
    print('PASS' if not problems else 'FAIL')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
