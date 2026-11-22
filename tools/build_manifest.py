#!/usr/bin/env python3
"""What a UniXNU build produced: path, size, SHA-256 and, for Mach-O files, CPU type, file type, segment count and
symbol counts -- without copying any of it. Text logs are copied (binary files never are).

  build_manifest.py UNIXNU [--uefi UEFI] [--status STATUS.json] --out MANIFEST.json [--logs DIR]

The manifest is what the readiness gate and the next session compare against (kernel hash, firmware hash, payload
hash, boot image hash). Files derived from Apple software or vendor firmware stay where they were built.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

PATTERNS = ['out/**/kernel/kernel.macho', 'out/**/kernel/kernel.json', 'build/xnu/**/mach.development.*',
            'out/**/package/**/*.efi', 'out/**/payload/payload.img', 'out/**/payload/payload.json',
            'out/**/boot/*.img', 'out/**/userdata/*.img']
UEFI_PATTERNS = ['Build/**/FV/*.fd', 'Build/**/FV/*.Fv']
CPU = {0x0100000c: 'arm64', 0x01000007: 'x86_64'}
FILETYPE = {1: 'object', 2: 'execute', 6: 'dylib', 11: 'kext_bundle'}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def macho(path):
    with open(path, 'rb') as f:
        head = f.read(32)
    if len(head) < 32 or head[:4] != b'\xcf\xfa\xed\xfe':
        return None
    _, cputype, _, filetype, ncmds, _, _, _ = struct.unpack('<8I', head)
    info = {'cpu': CPU.get(cputype, hex(cputype)), 'filetype': FILETYPE.get(filetype, filetype), 'load_commands': ncmds}
    nm = shutil.which('llvm-nm') or next((str(p) for p in Path('/opt/homebrew/opt/llvm/bin').glob('llvm-nm')), None)
    if nm:
        for key, flag in (('defined_symbols', '--defined-only'), ('undefined_symbols', '--undefined-only')):
            try:
                out = subprocess.run([nm, flag, str(path)], capture_output=True, text=True, timeout=300)
                info[key] = len(out.stdout.splitlines()) if out.returncode == 0 else f'nm failed: {out.stderr[:200]}'
            except (OSError, subprocess.TimeoutExpired) as error:
                info[key] = f'nm failed: {error}'
    return info


def collect(root, patterns):
    files = []
    for pattern in patterns:
        for path in sorted(Path(root).glob(pattern)):
            if path.is_file() and not path.is_symlink():
                entry = {'path': str(path.relative_to(root)), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
                info = macho(path)
                if info:
                    entry['macho'] = info
                files.append(entry)
    return files


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('unixnu', type=Path)
    ap.add_argument('--uefi', type=Path)
    ap.add_argument('--status', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--logs', type=Path)
    a = ap.parse_args(argv)
    manifest = {'unixnu_files': collect(a.unixnu, PATTERNS)}
    if a.uefi:
        manifest['uefi_files'] = collect(a.uefi, UEFI_PATTERNS)
    if a.status and a.status.is_file():
        try:
            manifest['status'] = json.loads(a.status.read_text())
        except json.JSONDecodeError:
            manifest['status'] = a.status.read_text()[-4000:]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(manifest, indent=1) + '\n')
    copied = 0
    if a.logs:
        a.logs.mkdir(parents=True, exist_ok=True)
        for log in sorted(a.unixnu.glob('out/**/logs/*.log')) + sorted(a.unixnu.glob('build/**/*.log'))[:200]:
            data = log.read_bytes()
            if b'\0' not in data:
                (a.logs / f'{log.parent.parent.name}-{log.name}').write_bytes(data)
                copied += 1
    n = len(manifest['unixnu_files']) + len(manifest.get('uefi_files', []))
    print(f'build_manifest: {n} built files recorded, {copied} text logs copied -> {a.out}')
    for entry in manifest['unixnu_files'] + manifest.get('uefi_files', []):
        print(f'  {entry["sha256"][:16]} {entry["bytes"]:>12} {entry["path"]} {entry.get("macho", "")}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
