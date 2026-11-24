#!/usr/bin/env python3
"""Everything the installation would put on the tablet, verified offline in one run (docs/IPADOS-PARTITION.md, 13).
Reads only; runs the repository's own checks. Exit 0 only when every item passes.

  final_verify.py --mode-a DIR --kernel kernel.macho --addon gpu-addon-clients.bin --root-image userdata-root.img
                  --root-json userdata-root.json --policies DIR --uefi DIR [--b5 b5.img --vendor-boot vendor_boot.img]
                  [--config config.gz --proc-version FILE]

  stage-B kernel   sha256 = the reproducible build (1d02cbe8...); owner key, anchor and both root manifests embedded
  MODE A image     image_consistency.py (derivation repeated), payload_check.py, cmdline_budget.py, abl_layout.py
  GPU addon        part of payload_check.py (NGPUADD2, the verified addon, every Mach-O in the trust cache)
  root image       sha256 = its record; OS/SystemOS windows and .vroot objects = the record; the .vroot objects =
                   the owner policies the kernel was built with
  B5 image         abl_layout.py PASS; structure: code0 -> shim, HKB5 descriptor, BootShim+firmware = the MODE A kernel,
                   payload = the MODE A payload; with --config/--proc-version, its kernel is the installed one
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))
import abl_layout  # noqa: E402
import b5_compose  # noqa: E402
import rom_match  # noqa: E402

KERNEL_SHA = '1d02cbe8d9992f32ad8e96ac2a475e41eba8667fdb7c52d42162e940deb3dc59'


def run(*args, env=None):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=env)
    return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else ''


def sha_file(p, offset=0, length=None):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        f.seek(offset)
        left = length
        while left is None or left > 0:
            chunk = f.read(1 << 24 if left is None else min(1 << 24, left))
            if not chunk:
                break
            h.update(chunk)
            if left is not None:
                left -= len(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('mode-a', 'kernel', 'addon', 'root-image', 'root-json', 'policies', 'uefi'):
        ap.add_argument(f'--{name}', type=Path, required=True)
    ap.add_argument('--b5', type=Path)
    ap.add_argument('--vendor-boot', type=Path)
    ap.add_argument('--config', type=Path)
    ap.add_argument('--proc-version', type=Path)
    a = ap.parse_args(argv)
    results = []
    say = lambda ok, name, text: results.append(('PASS' if ok else 'FAIL', name, text))
    import os
    env = dict(os.environ, UNIXNU_UEFI=str(a.uefi))

    kernel = a.kernel.read_bytes()
    say(hashlib.sha256(kernel).hexdigest() == KERNEL_SHA, 'stage-B kernel', f'sha256 {hashlib.sha256(kernel).hexdigest()[:16]}')
    for f in ('trusted-key.bin', 'OS/manifest.bin', 'SystemOS/manifest.bin'):
        say((a.policies / f).read_bytes() in kernel, 'stage-B kernel', f'{f} embedded')

    boot, payload = a.mode_a / 'boot/boot.img', a.mode_a / 'payload/payload.img'
    fd = a.uefi / 'Build/pipaPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd'
    probe = a.mode_a / 'tree/scripts/patch-xnu-entry-probe.py'
    say(*run(TOOLS / 'image_consistency.py', '--image', boot, '--kernel', a.kernel, '--payload', payload, '--firmware', fd,
             '--dtb', a.uefi / 'Resources/DTBs/pipa.dtb', '--derive', f'{sys.executable} {probe} {{}} --panic-screen --no-reset',
             env=env)[:1], 'MODE A image', 'image_consistency.py')
    ok, last = run(TOOLS / 'payload_check.py', '--payload', payload, '--manifest', a.mode_a / 'payload/payload.json',
                   '--kernel', a.kernel, '--addon', a.addon, '--board', ROOT.parent / 'hakios-work/UniXNU-pipa/board.toml',
                   '--unixnu', ROOT.parent / 'hakios-work/UniXNU')
    say(ok, 'MODE A payload + GPU addon', last)
    ok, last = run(TOOLS / 'cmdline_budget.py', payload)
    say(ok, 'MODE A menu', last)
    lay = abl_layout.layout(abl_layout.parse_boot(boot.read_bytes()), None)
    say(all(l == 'PASS' for l, _ in lay['checks']), 'MODE A image', 'ABL layout')

    rec = json.loads(a.root_json.read_text())
    say(a.root_image.stat().st_size == rec['image_bytes'], 'root image', f'{rec["image_bytes"]} bytes')
    say(sha_file(a.root_image) == rec['image_sha256'], 'root image', f'sha256 {rec["image_sha256"][:16]}')
    for part in rec['windows'] + rec['objects']:
        say(sha_file(a.root_image, part['offset'], part['size']) == part['sha256'], 'root image', f'{part["name"]} = its record')
    for obj in rec['objects']:
        name = obj['name']                                       # OS.vroot / SystemOS.vroot
        cand = [p for p in (a.policies / name, ROOT.parent.parent / 'unixnu-work/UniXNU-pipa/.cache/firmware/verified-root' / name)
                if p.is_file()]
        say(bool(cand) and sha_file(cand[0]) == obj['sha256'], 'root image', f'{name} = the owner policy object')

    if a.b5:
        img = a.b5.read_bytes()
        vendor = abl_layout.parse_vendor_boot(a.vendor_boot.read_bytes()) if a.vendor_boot else None
        lay = abl_layout.layout(abl_layout.parse_boot(img), vendor)
        say(all(l == 'PASS' for l, _ in lay['checks']), 'B5 image', f'ABL layout, {len(img)} bytes')
        ks = struct.unpack_from('<I', img, 8)[0]
        k = img[4096:4096 + ks]
        d = k.find(b'HKB5')
        so, bo, po, pl = struct.unpack_from('<QQQQ', k, d + 8)
        say(((struct.unpack_from('<I', k, 0)[0] & 0x3ffffff) * 4) == so, 'B5 image', 'code0 branches to the shim')
        bs = b5_compose.bootshim_from_mode_a(boot.read_bytes())
        say(k[bo:bo + len(bs)] == bs, 'B5 image', 'BootShim + firmware = the MODE A kernel')
        say(k[po:po + pl] == payload.read_bytes(), 'B5 image', 'payload = the MODE A payload')
        if a.config and a.proc_version:
            res = rom_match.check(boot=img, config=a.config.read_bytes(), proc_version=a.proc_version.read_text())
            bad = [t for level, t in res if level == 'FAIL']
            say(not bad, 'B5 image', 'Android kernel = the installed one' + (f' ({bad[0][:60]})' if bad else ''))

    for level, name, text in results:
        print(f'{level:4} {name:28} {text}')
    bad = sum(level == 'FAIL' for level, _, _ in results)
    print(f'FINAL VERIFY: {"PASS" if not bad else "FAIL"} ({len(results) - bad} of {len(results)})')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
