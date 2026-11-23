#!/usr/bin/env python3
"""Check the private pipa firmware the legacy-display archive embeds, before a local stage-B build.

  firmware_check.py DIR [--pins UniXNU-pipa/proprietary-files.txt] [--pins manifests/pipa-official-rom-*.txt] [--json OUT]

DIR is a private directory outside Git (scripts/collect-firmware.sh fills it). For each input the check reports
MISSING, FORMAT FAIL, PIN MISMATCH or PASS:
  - the format rules of build-gop-legacy-display.py, unchanged (GMU block image, SQE image, 32-bit ELF ZAP, Novatek
    image whose trailer passes the vendor driver's version check); the ZAP ELF machine is reported, not judged;
  - the SHA-256 recorded for this unit in the port's proprietary-files.txt, or in another pin file given with a
    further --pins (each records its own provenance, e.g. an official Xiaomi ROM); the matching file is reported.
    A digest that matches no pin file is PIN MISMATCH, never PASS.
A split PIL image (a650_zap.mdt + .b0N) is reported as such: the builder needs the single a650_zap.elf from the
same /vendor/firmware, and renaming another file is never a substitute. Nothing is copied or printed but digests.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

INPUTS = {   # builder path under .cache/firmware -> proprietary-files.txt entry
    'gpu/a650_gmu.bin': 'firmware/a650_gmu.bin',
    'gpu/a650_sqe.fw': 'firmware/a650_sqe.fw',
    'gpu/a650_zap.elf': 'firmware/a650_zap.elf',
    'touch/novatek_nt36532_m82_fw_csot.bin': 'firmware/novatek_nt36532_m82_fw_csot.bin',
}


def pins_of(path):
    pins = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith('#') or '|' not in line:
            continue
        fields = [f.strip() for f in line.split('|')]
        if len(fields) >= 3 and len(fields[2]) == 64:
            pins[fields[0]] = fields[2]
    return pins


def format_problems(name, blob):
    if name.endswith('a650_gmu.bin'):
        return [] if len(blob) >= 16 and len(blob) % 4 == 0 else ['not a GMU block image (size >= 16, multiple of 4)']
    if name.endswith('a650_sqe.fw'):
        return [] if len(blob) >= 8 and len(blob) % 4 == 0 else ['not an SQE image (size >= 8, multiple of 4)']
    if name.endswith('a650_zap.elf'):
        if len(blob) < 52 or blob[:5] != b'\x7fELF\x01':
            return ['not a 32-bit ELF (the builder requires \\x7fELF\\x01)']
        return []   # e_machine is reported, not judged: the builder sets no rule for it
    if name.endswith('.bin') and 'novatek' in name:
        if len(blob) <= 4096 or (blob[-4096] + blob[-4095]) & 0xff != 0xff:
            return ['fails the vendor driver version check (size > 4096, trailer bytes sum to 0xff)']
        return []
    return ['unknown input']


def merge_pins(*files):
    """entry -> {sha256: [pin file names]} over several pin files"""
    merged = {}
    for f in files:
        for entry, digest in pins_of(f).items():
            merged.setdefault(entry, {}).setdefault(digest, []).append(Path(f).name)
    return merged


def check(directory, pins):
    directory, results = Path(directory), []
    pins = {k: (v if isinstance(v, dict) else {v: []}) for k, v in pins.items()}
    for rel, entry in INPUTS.items():
        path = directory / rel
        known = pins.get(entry, {})
        row = {'input': rel, 'pin': sorted(known)[0] if len(known) == 1 else (sorted(known) or None)}
        if not path.is_file():
            row['verdict'] = 'MISSING'
            if rel.endswith('a650_zap.elf') and (directory / 'gpu/a650_zap.mdt').is_file():
                row['note'] = 'split PIL image (a650_zap.mdt/.b0N) present; the single a650_zap.elf is still needed'
        else:
            blob = path.read_bytes()
            row.update(sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob))
            if rel.endswith('.elf') and len(blob) >= 20:
                row['elf_machine'] = struct.unpack_from('<H', blob, 18)[0]
            problems = format_problems(rel, blob)
            if problems:
                row.update(verdict='FORMAT FAIL', problems=problems)
            elif known and row['sha256'] not in known:
                row['verdict'] = 'PIN MISMATCH'
            elif not known:
                row['verdict'] = 'NO PIN'
            else:
                row['verdict'] = 'PASS'
                if known[row['sha256']]:
                    row['pin_source'] = known[row['sha256']]
        results.append(row)
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('directory')
    p.add_argument('--pins', action='append', default=[])
    p.add_argument('--json')
    args = p.parse_args(argv)
    pins = merge_pins(*args.pins)
    results = check(args.directory, pins)
    for r in results:
        extra = r.get('note') or '; '.join(r.get('problems', [])) or (r.get('sha256', '')[:16] + '...' if r.get('sha256') else '')
        if r.get('pin_source'):
            extra += ' (' + ', '.join(r['pin_source']) + ')'
        print(f'{r["verdict"]:12} {r["input"]}  {extra}')
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2) + '\n')
    ok = all(r['verdict'] == 'PASS' for r in results)
    print('FIRMWARE ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
