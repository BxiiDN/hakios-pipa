#!/usr/bin/env python3
"""iPadOS 17 user space, checked where it sits (the unpacked root of the 21H461 iPad7,1 IPSW, or a mounted OS
volume): the programs and services the tablet UI needs are there, are arm64/arm64e Mach-O, and every library they
load is present -- on disk, or listed in a dyld shared cache of the same root.

  userland_check.py ROOT [--json]
  userland_check.py --dmg OS.dmg [--dmg-at System/Cryptexes/OS=SystemOS.dmg] [--json]

With --dmg the IPSW disk images themselves are read in place through 7-Zip's APFS reader (7z, streamed to memory,
nothing written): OS.dmg is the root, and each --dmg-at volume is seen at its mount point (the SystemOS cryptex at
System/Cryptexes/OS, where the dyld shared cache lives). A file 7-Zip cannot decode (LZBITMAP) is reported, not skipped.

Extracting an IPSW proves nothing about booting; this answers only "is the user space whole and for this
architecture". Apple files are read in place and never copied.

iPadOS has no WindowServer: the display server role is backboardd with the CoreAnimation render server, which is
what this checks for.
"""
import json
import re
import struct
import subprocess
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
    ('IOSurface (shared GPU/display buffers)', 'System/Library/Frameworks/IOSurface.framework'),
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


def parse_slt(text):
    """(path, kind, method) of each entry in `7z l -slt -ba` output; kind from the POSIX mode: dir, link or file.
    Alternate streams (resource forks, extended attributes) are not files of the volume and are left out."""
    out, row = [], {}
    for line in text.splitlines() + ['']:
        if not line.strip():
            if 'Path' in row and row.get('Alternate Stream', '-') != '+' and ':' not in row['Path'].rsplit('/', 1)[-1]:
                mode = row.get('Mode', '')
                kind = 'dir' if mode.startswith('d') else 'link' if mode.startswith('l') or row.get('Method') == 'symlink' else 'file'
                out.append((row['Path'], kind, row.get('Method', '')))
            row = {}
        elif ' = ' in line:
            k, v = line.split(' = ', 1)
            row[k] = v
        elif line.endswith(' ='):
            row[line[:-2]] = ''
    return out


class DmgRoot:
    """A read-only view of one or more APFS volumes inside IPSW disk images, through 7-Zip. Paths are relative."""
    def __init__(self, image, mounts=()):
        self.volumes = [('', Path(image))] + [(m.strip('/') + '/', Path(i)) for m, i in mounts]
        self.entries = {}   # rel -> (kind, method, image, inner path)
        self.unreadable = []
        for prefix, img in self.volumes:
            out = subprocess.run(['7z', 'l', '-slt', '-ba', str(img)], capture_output=True, text=True).stdout
            for path, kind, method in parse_slt(out):
                self.entries[prefix + path] = (kind, method, img, path)
        if not self.entries:
            raise SystemExit(f'7z could not list {image}')

    def kind(self, rel):
        return self.entries.get(str(rel).strip('/'), (None,))[0]

    def read(self, rel):
        kind, method, img, inner = self.entries[str(rel).strip('/')]
        if method.startswith('ZBM'):
            self.unreadable.append(str(rel))
            return None
        r = subprocess.run(['7z', 'e', '-so', str(img), inner], capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def glob(self, directory, pattern):
        prefix = directory.strip('/') + '/'
        return sorted(k for k, v in self.entries.items() if k.startswith(prefix) and '/' not in k[len(prefix):]
                      and re.fullmatch(pattern.replace('*', '.*'), k[len(prefix):]) and v[0] == 'file')


def check_dmg(view):
    """check() for a DmgRoot: the same required programs, libraries and launchd jobs."""
    findings, report = [], {'required': [], 'missing_libraries': {}, 'unreadable': []}
    say = lambda level, text: findings.append((level, text))
    caches = [c for d in CACHE_DIRS for c in view.glob(d, 'dyld_shared_cache_arm64*') if not c.endswith(('.map', '.atlas'))]
    report['shared_caches'] = caches
    say('PASS' if caches else 'FAIL', f'dyld shared cache: {len(caches)} file(s)')
    wanted, in_cache = {}, {}
    for label, rel in REQUIRED:
        path = rel + '/' + Path(rel).stem if rel.endswith('.framework') else rel
        if rel.endswith('.framework') and view.kind(path) != 'file':
            # iOS 17 keeps framework binaries only in the dyld shared cache; the bundle directory stays on disk
            if view.kind(rel) not in ('dir', 'link'):
                say('FAIL', f'{label}: {rel} missing')
            else:
                in_cache[(label, rel)] = '/' + path
            continue
        if view.kind(path) != 'file':
            say('FAIL', f'{label}: {rel} missing ({view.kind(path)})')
            continue
        data = view.read(path)
        found = slices(data or b'')
        arm = [off for cpu, off in found if cpu == ARM64]
        if not arm:
            say('FAIL', f'{label}: {rel} is not an arm64 Mach-O')
            continue
        libs = [lib for lib, weak in dylibs(data, arm[0]) if not lib.startswith('@') and not weak]
        report['required'].append({'label': label, 'path': rel, 'libraries': len(libs)})
        wanted[(label, rel)] = [lib for lib in libs if view.kind(lib.lstrip('/')) not in ('file', 'link')]
    needles = {lib for libs in wanted.values() for lib in libs} | set(in_cache.values())
    seen = set()
    for cache in sorted(caches, key=lambda c: (not c.endswith('dyld_shared_cache_arm64'), c)):
        if not needles - seen:
            break
        blob = view.read(cache)
        if blob is None:
            continue
        seen |= {lib for lib in needles - seen if b'\0' + lib.encode() + b'\0' in blob}
    for (label, rel), image in in_cache.items():
        say('PASS' if image in seen else 'FAIL', f'{label}: {image} ' + ('is an image of the shared cache' if image in seen else 'is neither on disk nor in a shared cache'))
    for (label, rel), libs in wanted.items():
        missing = [lib for lib in libs if lib not in seen]
        if missing:
            report['missing_libraries'][rel] = missing
            say('FAIL', f'{label}: {len(missing)} library(ies) neither on disk nor in a shared cache: {missing[:3]}')
        else:
            say('PASS', f'{label}: arm64, every library present ({len(libs)} from the shared cache)')
    for plist in LAUNCH_DAEMONS:
        data = view.read(plist) if view.kind(plist) == 'file' else None
        ok = bool(data) and (b'bplist' in data[:8] or b'<plist' in data[:200])
        say('PASS' if ok else 'FAIL', f'launchd job {Path(plist).stem}{"" if ok else ": missing or not a property list"}')
    report['unreadable'] = view.unreadable
    if view.unreadable:
        say('WARN', f'7-Zip cannot decode {len(view.unreadable)} file(s) (LZBITMAP): {view.unreadable[:3]}')
    return findings, report


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
        if not path.is_file() and rel.endswith('.framework') and (root / rel).is_dir():
            image = '/' + str(path.relative_to(root))
            say('PASS' if cache.lists(image) else 'FAIL', f'{label}: {image} ' + ('is an image of the shared cache' if cache.lists(image) else 'is neither on disk nor in a shared cache'))
            continue
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
    if argv[1] == '--dmg':
        mounts = [a.split('=', 1) for i, a in enumerate(argv) if i and argv[i - 1] == '--dmg-at']
        findings, report = check_dmg(DmgRoot(argv[2], mounts))
    else:
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
