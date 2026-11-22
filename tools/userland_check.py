#!/usr/bin/env python3
"""iPadOS 17 user space, checked where it sits (the unpacked root of the 21H461 iPad7,1 IPSW, or a mounted OS
volume): the programs and services the tablet UI needs are there, are arm64/arm64e Mach-O, and every library they
load is present -- on disk, or listed in a dyld shared cache of the same root.

  userland_check.py ROOT [--json]

Extracting an IPSW proves nothing about booting; this answers only "is the user space whole and for this
architecture". Apple files are read in place and never copied.

iPadOS has no WindowServer: the display server role is backboardd with the CoreAnimation render server, which is
what this checks for.
"""
import json
import re
import struct
import sys
from pathlib import Path

LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB, LC_LOAD_UPWARD_DYLIB = \
    0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023
ARM64 = 0x0100000c

# What the tablet UI and the services in the request rest on: (label, path in the root)
REQUIRED = [
    ('launchd', 'sbin/launchd'),
    ('backboardd (display, HID, CoreAnimation render server)', 'usr/libexec/backboardd'),
    ('SpringBoard (home screen, Dock, multitasking, Control and Notification Center)',
     'System/Library/CoreServices/SpringBoard.app/SpringBoard'),
    ('CoreGraphics', 'System/Library/Frameworks/CoreGraphics.framework'),
    ('QuartzCore (CoreAnimation)', 'System/Library/Frameworks/QuartzCore.framework'),
    ('Metal', 'System/Library/Frameworks/Metal.framework'),
    ('IOKit', 'System/Library/Frameworks/IOKit.framework'),
    ('CoreAudio / audio server', 'usr/sbin/mediaserverd'),
    ('network: configd', 'usr/libexec/configd'),
    ('network: wifid', 'usr/sbin/wifid'),
    ('software keyboard (UIKit)', 'System/Library/Frameworks/UIKit.framework'),
    ('Settings', 'Applications/Preferences.app/Preferences'),
]
LAUNCH_DAEMONS = ['System/Library/LaunchDaemons/com.apple.backboardd.plist',
                  'System/Library/LaunchDaemons/com.apple.SpringBoard.plist',
                  'System/Library/LaunchDaemons/com.apple.mediaserverd.plist',
                  'System/Library/LaunchDaemons/com.apple.configd.plist']
CACHE_DIRS = ['System/Library/Caches/com.apple.dyld', 'System/Cryptexes/OS/System/Library/Caches/com.apple.dyld',
              'private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld']


def slices(data):
    """(cputype, offset) of each Mach-O slice; [] when the file is not Mach-O."""
    magic = data[:4]
    if magic == b'\xcf\xfa\xed\xfe':
        return [(struct.unpack_from('<I', data, 4)[0], 0)]
    if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        n = struct.unpack_from('>I', data, 4)[0]
        if n > 20:
            return []
        wide = magic == b'\xca\xfe\xba\xbf'
        out = []
        for i in range(n):
            if wide:
                cpu, _, off = struct.unpack_from('>IIQ', data, 8 + i * 32)
            else:
                cpu, _, off = struct.unpack_from('>III', data, 8 + i * 20)
            out.append((cpu, off))
        return out
    return []


def dylibs(data, offset):
    """Libraries a 64-bit Mach-O slice loads."""
    ncmds, sizeofcmds = struct.unpack_from('<II', data, offset + 16)
    at, end, out = offset + 32, offset + 32 + sizeofcmds, []
    for _ in range(ncmds):
        if at + 8 > end:
            break
        cmd, size = struct.unpack_from('<II', data, at)
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LAZY_LOAD_DYLIB, LC_LOAD_UPWARD_DYLIB):
            name_off = struct.unpack_from('<I', data, at + 8)[0]
            raw = data[at + name_off:at + size]
            out.append((raw.split(b'\0', 1)[0].decode('utf-8', 'replace'), cmd == LC_LOAD_WEAK_DYLIB))
        if size < 8:
            break
        at += size
    return out


def binary_of(root, rel):
    path = root / rel
    if path.suffix == '.framework' and path.is_dir():
        return path / path.stem
    return path


class SharedCache:
    """Image paths listed in the dyld shared caches under ROOT (the paths are stored as NUL-terminated strings)."""
    def __init__(self, root):
        self.blobs = []
        for d in CACHE_DIRS:
            for f in sorted((root / d).glob('dyld_shared_cache_arm64*')):
                if f.is_file() and not f.name.endswith(('.map', '.atlas')):
                    self.blobs.append(f)
        self._seen = {}

    def lists(self, path):
        if path not in self._seen:
            needle = b'\0' + path.encode() + b'\0'
            self._seen[path] = any(needle in f.read_bytes() for f in self.blobs)
        return self._seen[path]


def check(root):
    root = Path(root)
    cache = SharedCache(root)
    findings, report = [], {'required': [], 'missing_libraries': {}, 'shared_caches': [str(b.relative_to(root)) for b in cache.blobs]}
    say = lambda level, text: findings.append((level, text))
    say('PASS' if cache.blobs else 'FAIL', f'dyld shared cache: {len(cache.blobs)} file(s)')
    for label, rel in REQUIRED:
        path = binary_of(root, rel)
        if not path.is_file():
            say('FAIL', f'{label}: {rel} missing')
            continue
        data = path.read_bytes()
        found = slices(data)
        if not found:
            say('FAIL', f'{label}: {rel} is not Mach-O')
            continue
        arm = [off for cpu, off in found if cpu == ARM64]
        if not arm:
            say('FAIL', f'{label}: no arm64/arm64e slice ({[hex(c) for c, _ in found]})')
            continue
        missing = []
        for lib, weak in dylibs(data, arm[0]):
            if lib.startswith('@') or weak:
                continue
            if not (root / lib.lstrip('/')).exists() and not cache.lists(lib):
                missing.append(lib)
        report['required'].append({'label': label, 'path': rel})
        if missing:
            report['missing_libraries'][rel] = missing
            say('FAIL', f'{label}: {len(missing)} library(ies) neither on disk nor in a shared cache: {missing[:3]}')
        else:
            say('PASS', f'{label}: arm64, every library present')
    for plist in LAUNCH_DAEMONS:
        path = root / plist
        if not path.is_file():
            say('FAIL', f'launchd job missing: {plist}')
        else:
            text = path.read_bytes()
            ok = b'bplist' in text[:8] or b'<plist' in text[:200]
            say('PASS' if ok else 'FAIL', f'launchd job {Path(plist).stem}{"" if ok else ": not a property list"}')
    return findings, report


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    findings, report = check(argv[1])
    if '--json' in argv:
        print(json.dumps({'findings': findings, **report}, indent=1))
    else:
        for level, text in findings:
            print(f'{level:5} {text}')
    bad = any(level == 'FAIL' for level, _ in findings)
    print('USERLAND COMPLETE (not a boot test)' if not bad else 'USERLAND INCOMPLETE')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
