#!/usr/bin/env python3
"""Provenance of the stage-A reference kernel and its HID bindings (docs/BOOTSTRAP.md).

The pipa port's ABI builders (build-sheng-hid-input.py, build-gop-legacy-display.py, build-platform-power.py) qualify
their drivers against a kernel that has already been prelinked. Stage A builds that kernel from the same pinned
sources, without the two archives that need it, and prelinks it with UniXNU's own prelinker. This tool records where
the candidate came from, refuses a candidate that is not the prelinker's own output, and compares the HID bindings
of the stage-B build with a second qualification against the final kernel.

  record  --kernel K --plan K.json --stage-patch P --out provenance.json [--commit NAME=SHA ...]
  verify  --candidate C --plan C.json --provenance provenance.json
  install --candidate C --plan C.json --provenance provenance.json --tree TREE
  compare-bindings STAGE_B_AUDIT FINAL_AUDIT

Exit status 0 only for a full PASS. A missing input is FAIL, never SKIP.
"""
import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

# The original IOHIDFamily __TEXT_EXEC of the iPad7,1 21H461 kernelcache (build-sheng-hid-input.py HID_TEXT_SHA).
HID_TEXT_SHA = '7e4c5104814f2e773d5be13d092dec53ee44ba5a61a81264b229780406e86b72'
# Native symbols the HID and display builders read from the candidate.
REQUIRED_EXPORTS = ('__ZTV9IOService', '___cxa_pure_virtual', '__ZN9IOServiceC2EPK11OSMetaClass', '__ZN9IOServiceD2Ev')
# The name build-sheng-hid-input.py globs (native-owner-ufs-cpu-desktop-*-candidate.macho).
INSTALLED_NAME = 'native-owner-ufs-cpu-desktop-stagea-candidate.macho'
LC_SYMTAB, LC_SEGMENT_64 = 0x2, 0x19


class Fail(Exception):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse(data):
    """Header, segments and defined external symbols of an ordinary little-endian arm64 Mach-O."""
    if len(data) < 32:
        raise Fail('not a Mach-O file (too short)')
    magic, cpu, subtype, filetype, ncmds, sizeofcmds = struct.unpack_from('<6I', data)
    if (magic, cpu, subtype) != (0xfeedfacf, 0x100000c, 0):
        raise Fail(f'not an ordinary arm64 Mach-O (magic {magic:#x}, cpu {cpu:#x}, subtype {subtype:#x})')
    if 32 + sizeofcmds > len(data):
        raise Fail('load commands outside the file')
    at, segments, symtab = 32, [], None
    for _ in range(ncmds):
        command, size = struct.unpack_from('<2I', data, at)
        if size < 8 or at + size > 32 + sizeofcmds:
            raise Fail('malformed load command')
        if command == LC_SEGMENT_64:
            name = data[at + 8:at + 24].rstrip(b'\0').decode('latin1')
            va, vmsize, fileoff, filesize = struct.unpack_from('<4Q', data, at + 24)
            segments.append({'name': name, 'va': va, 'vmsize': vmsize, 'fileoff': fileoff, 'filesize': filesize})
        elif command == LC_SYMTAB:
            if symtab is not None:
                raise Fail('more than one symbol table')
            symtab = struct.unpack_from('<4I', data, at + 8)
        at += size
    for s in segments:
        if s['filesize'] and s['fileoff'] + s['filesize'] > len(data):
            raise Fail(f'segment {s["name"]} extends past the file')
    exports = {}
    if symtab:
        symoff, count, stroff, strsize = symtab
        if symoff + 16 * count > len(data) or stroff + strsize > len(data):
            raise Fail('symbol table outside the file')
        strings = data[stroff:stroff + strsize]
        for index in range(count):
            strx, kind, _, _, value = struct.unpack_from('<IBBHQ', data, symoff + 16 * index)
            if kind & 0xe0 or not kind & 1 or not kind & 0x0e or strx >= strsize:
                continue   # stabs, local or undefined
            end = strings.find(b'\0', strx)
            exports[strings[strx:end].decode('latin1')] = value
    return {'filetype': filetype, 'segments': segments, 'exports': exports}


def check_candidate(candidate, plan_path, provenance=None):
    """Return (findings, facts); a finding is ('PASS'|'FAIL', text)."""
    findings = []

    def check(ok, text):
        findings.append(('PASS' if ok else 'FAIL', text))
        return ok

    candidate, plan_path = Path(candidate), Path(plan_path)
    if not check(candidate.is_file(), f'candidate {candidate} exists') or not check(plan_path.is_file(), f'plan {plan_path} exists'):
        return findings, {}
    plan = json.loads(plan_path.read_text())
    digest = sha256(candidate)
    check(plan.get('candidate_sha256') == digest, f'candidate sha256 {digest[:16]}... is the one the prelinker recorded')
    check(plan.get('images_modified') is False, 'prelink plan: original images unmodified')
    hid = plan.get('original_executable_sha256', {}).get('com.apple.iokit.IOHIDFamily')
    check(hid == HID_TEXT_SHA, 'original IOHIDFamily __TEXT_EXEC is the 21H461 one')
    check(any(e.get('module') == 'com.apple.iokit.IOHIDFamily' and e.get('segment') == '__TEXT_EXEC'
              for e in plan.get('extents', [])), 'IOHIDFamily __TEXT_EXEC extent in the plan')
    facts = {'candidate_sha256': digest, 'candidate_bytes': candidate.stat().st_size, 'plan_sha256': sha256(plan_path)}
    try:
        image = parse(candidate.read_bytes())
    except Fail as error:
        check(False, f'Mach-O: {error}')
        return findings, facts
    check(image['filetype'] in (2, 12), f'Mach-O file type {image["filetype"]} (executable or fileset)')
    text = [s for s in image['segments'] if s['name'] == '__TEXT']
    check(len(text) == 1 and text[0]['va'] % 0x4000 == 0, '__TEXT present and 16 KiB aligned')
    for name in REQUIRED_EXPORTS:
        check(name in image['exports'], f'exports {name}')
    facts['exports'] = {n: hex(image['exports'][n]) for n in REQUIRED_EXPORTS if n in image['exports']}
    if provenance is not None:
        prov = json.loads(Path(provenance).read_text())
        check(prov.get('stage') == 'A', 'provenance: stage A reference kernel')
        check(prov.get('candidate_sha256') == digest, 'provenance names this candidate')
        check(prov.get('plan_candidate_sha256') == digest, 'provenance plan digest matches')
        check(prov.get('boot_candidate') is False, 'provenance: never a boot candidate')
    return findings, facts


def report(findings):
    for verdict, text in findings:
        print(f'{verdict:5} {text}')
    failed = sum(v == 'FAIL' for v, _ in findings)
    print('CANDIDATE PROVENANCE ' + ('PASS' if not failed and findings else f'FAIL ({failed})'))
    return 0 if not failed and findings else 1


def compare_bindings(stage_b, final):
    findings = []
    a, b = json.loads(Path(stage_b).read_text()), json.loads(Path(final).read_text())
    for key in ('original_text_sha256', 'original_slots', 'original_instance_size', 'owned_slots'):
        findings.append(('PASS' if a.get(key) == b.get(key) else 'FAIL', f'{key} unchanged against the final kernel'))
    ba, bb = a.get('bindings', {}), b.get('bindings', {})
    findings.append(('PASS' if ba and set(ba) == set(bb) else 'FAIL', f'same {len(ba)} bound original HID symbols'))
    for name in sorted(set(ba) & set(bb)):
        if ba[name] != bb[name]:
            findings.append(('FAIL', f'{name}: {ba[name]:#x} at stage B, {bb[name]:#x} against the final kernel'))
    findings.append(('PASS' if a.get('reference_candidate_sha256') != b.get('reference_candidate_sha256') else 'FAIL',
                     'the second qualification ran against a different (the final) kernel'))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='action', required=True)
    r = sub.add_parser('record')
    r.add_argument('--kernel', required=True)
    r.add_argument('--plan', required=True)
    r.add_argument('--stage-patch', required=True)
    r.add_argument('--out', required=True)
    r.add_argument('--commit', action='append', default=[], metavar='NAME=SHA')
    for name in ('verify', 'install'):
        v = sub.add_parser(name)
        v.add_argument('--candidate', required=True)
        v.add_argument('--plan', required=True)
        v.add_argument('--provenance', required=True)
        if name == 'install':
            v.add_argument('--tree', required=True)
    c = sub.add_parser('compare-bindings')
    c.add_argument('stage_b')
    c.add_argument('final')
    args = parser.parse_args(argv)

    if args.action == 'record':
        findings, facts = check_candidate(args.kernel, args.plan)
        code = report(findings)
        if code:
            return code
        plan = json.loads(Path(args.plan).read_text())
        prov = dict(stage='A', boot_candidate=False, purpose='ABI reference for the stage-B driver builders only',
                    candidate_sha256=facts['candidate_sha256'], candidate_bytes=facts['candidate_bytes'],
                    plan_sha256=facts['plan_sha256'], plan_candidate_sha256=plan['candidate_sha256'],
                    iohidfamily_text_sha256=plan['original_executable_sha256']['com.apple.iokit.IOHIDFamily'],
                    stage_patch_sha256=sha256(args.stage_patch), exports=facts['exports'],
                    commits=dict(item.split('=', 1) for item in args.commit),
                    missing_from_stage_a=['ShengHidInput (touch)', 'NativeLegacyDisplay archive (display, USB, '
                                          'Wi-Fi, Bluetooth, touch, buttons)', 'PMGR bridge (first-pass no-op)'])
        Path(args.out).write_text(json.dumps(prov, indent=2) + '\n')
        print(f'recorded {args.out}')
        return 0
    if args.action in ('verify', 'install'):
        findings, _ = check_candidate(args.candidate, args.plan, args.provenance)
        code = report(findings)
        if code or args.action == 'verify':
            return code
        target = Path(args.tree) / 'build/xnu-prelink' / INSTALLED_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.candidate, target)
        shutil.copyfile(args.plan, target.with_suffix('.json'))
        print(f'installed {target}')
        return 0
    return report(compare_bindings(args.stage_b, args.final))


if __name__ == '__main__':
    sys.exit(main())
