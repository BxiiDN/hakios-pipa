#!/usr/bin/env python3
"""Check firmware taken from the user's own tablet against a manifest of names and SHA-256 digests, without the
firmware ever entering this repository.

  firmware_manifest.py MANIFEST DIR [--touch NAME]   each file: PASS (digest matches), FAIL (differs), MISSING
     --touch NAME: the panel's touch firmware (tools/panel_firmware.py); the other panel's image is not required
  firmware_manifest.py --self-test

MANIFEST uses UniXNU-pipa's proprietary-files.txt format: `path | source | sha256 | consumer`, '#' comments.
A FAIL is not always an error: device-signed images (a650_zap.mdt/.b01/.elf) and the touch firmware depend on the
unit and panel maker; the report says so, and nothing is copied or renamed.
"""
import hashlib
import sys
import tempfile
from pathlib import Path

UNIT_DEPENDENT = ('a650_zap.mdt', 'a650_zap.b01', 'a650_zap.elf', 'novatek_nt36532_')


def parse(text):
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = [f.strip() for f in line.split('|')]
        if len(fields) != 4 or len(fields[2]) != 64:
            raise ValueError(f'bad manifest line: {line}')
        rows.append(dict(zip(('path', 'source', 'sha256', 'consumer'), fields)))
    return rows


def check(rows, base, touch=None):
    results = []
    for row in rows:
        if touch and Path(row['path']).name.startswith('novatek_') and Path(row['path']).name != touch:
            results.append(('OTHER', row, None))
            continue
        path = Path(base) / row['path']
        if not path.is_file():
            path = Path(base) / Path(row['path']).name
        if not path.is_file():
            results.append(('MISSING', row, None))
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        results.append(('PASS' if digest == row['sha256'] else 'FAIL', row, digest))
    return results


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'firmware').mkdir()
        Path(tmp, 'firmware', 'a.bin').write_bytes(b'abc')
        Path(tmp, 'b.bin').write_bytes(b'xyz')
        good = hashlib.sha256(b'abc').hexdigest()
        rows = parse(f'# c\nfirmware/a.bin | s | {good} | GPU\nfirmware/b.bin | s | {"0" * 64} | X\n'
                     f'firmware/c.bin | s | {"1" * 64} | Y\n')
        got = [r[0] for r in check(rows, tmp)]
        assert got == ['PASS', 'FAIL', 'MISSING'], got
        rows2 = parse(f'firmware/novatek_nt36532_m82_fw_tm.bin | s | {"2" * 64} | T\n')
        assert [r[0] for r in check(rows2, tmp, touch='novatek_nt36532_m82_fw_csot.bin')] == ['OTHER']
        assert [r[0] for r in check(rows2, tmp, touch='novatek_nt36532_m82_fw_tm.bin')] == ['MISSING']
        try:
            parse('x | y | short | z')
            raise AssertionError('short digest accepted')
        except ValueError:
            pass
    print('firmware_manifest: self-test ok (6 cases)')
    return 0


def main(argv):
    if argv[1:] == ['--self-test']:
        return self_test()
    touch = argv[argv.index('--touch') + 1] if '--touch' in argv else None
    args = [a for i, a in enumerate(argv) if a != '--touch' and (i == 0 or argv[i - 1] != '--touch')]
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    results = check(parse(Path(args[1]).read_text()), args[2], touch)
    bad = 0
    for state, row, digest in results:
        note = ''
        if state == 'OTHER':
            print(f'OTHER    {row["path"]}  [{row["consumer"]}] (the other panel\'s image: not required)')
            continue
        if state == 'FAIL' and any(k in row['path'] for k in UNIT_DEPENDENT):
            note = ' (unit- or panel-dependent: compare with your own panel maker / signature before calling it wrong)'
        elif state != 'PASS':
            bad += 1
        print(f'{state:8} {row["path"]}  [{row["consumer"]}]{note}')
    print(f'{sum(r[0] == "PASS" for r in results)}/{sum(r[0] != "OTHER" for r in results)} match')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
