#!/usr/bin/env python3
"""Check what scripts/windows/dump-pipa-usb.ps1 copied from the tablet's read-only USB disks, and build the recovery set.
Reads DIR, writes only DIR/partitions, DIR/recovery and DIR/report.json (docs/IPADOS-PARTITION.md, section 12).

  usb_dump_check.py DIR --config config.gz --proc-version FILE

DIR holds boot-lun.img (the whole boot LUN) and lun0-head.img + lun0-tail.bin (LUN 0 up to userdata, and its last 5
sectors), with SHA256SUMS.txt. Checked:
  - every file against SHA256SUMS.txt;
  - both GPTs (primary and backup, CRCs, entries identical); LUN 0 = the layout measured on 24 Nov
    (tests/data/pipa-lun0-layout.json);
  - the active slot's boot_b, vendor_boot_b, dtbo_b are the installed ROM (tools/rom_match.py: kernel banner and embedded
    config = the tablet's) -- the only proof that this set can bring Android back;
  - super carries liblp metadata (geometry magic at 4096).
DIR/recovery/{boot,vendor_boot,dtbo,vbmeta,vbmeta_system,super}.img is then the set tools/design_b_readiness.py --rom takes.
"""
import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpt_capacity  # noqa: E402
import pipa_gpt  # noqa: E402
import rom_match  # noqa: E402

LAYOUT = Path(__file__).resolve().parent.parent / 'tests/data/pipa-lun0-layout.json'
LP_GEOMETRY_MAGIC = 0x616c4467          # liblp LP_METADATA_GEOMETRY_MAGIC ("gDla"), at byte 4096 of super
SLOT = '_b'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 24), b''):
            h.update(chunk)
    return h.hexdigest()


def check_sums(d):
    problems = []
    sums = d / 'SHA256SUMS.txt'
    if not sums.is_file():
        return ['no SHA256SUMS.txt']
    for line in sums.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        want, name = line.split(None, 1)
        if sha(d / name.strip()) != want.lower():
            problems.append(f'{name.strip()} does not match SHA256SUMS.txt')
    return problems


def gpt_of(head, tail, sector, disk_blocks):
    table = pipa_gpt.parse_gpt(head, 'disk')
    hdr = head[sector:sector + 92]
    entries_lba, count, esize = struct.unpack_from('<QII', hdr, 72)
    problems = gpt_capacity.backup_check(head[entries_lba * sector:entries_lba * sector + count * esize], tail, sector,
                                         disk_blocks)
    if table['backup_lba'] != disk_blocks - 1:
        problems.append('primary header does not name the last LBA as backup')
    return table, problems


def read_range(path, offset, length):
    with open(path, 'rb') as f:
        f.seek(offset)
        return f.read(length)


def extract(path, table, name, out, base=0):
    part = next((p for p in table['partitions'] if p['name'] == name), None)
    if part is None:
        return None
    sector = table['sector_size']
    off, length = part['first_lba'] * sector - base, (part['last_lba'] - part['first_lba'] + 1) * sector
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'rb') as src, open(out, 'wb') as dst:
        src.seek(off)
        left = length
        while left:
            chunk = src.read(min(left, 1 << 24))
            if not chunk:
                raise ValueError(f'{path.name} ends inside {name}')
            dst.write(chunk)
            left -= len(chunk)
    return out


def check(d, config, proc_version, layout_path=LAYOUT):
    d = Path(d)
    report = {'problems': check_sums(d), 'recovery': {}}
    parts = d / 'partitions'
    boot = d / 'boot-lun.img'
    if boot.is_file():
        size = boot.stat().st_size
        head = read_range(boot, 0, 6 * 4096)
        sector = 4096 if head[4096:4104] == b'EFI PART' else 512
        tail = read_range(boot, size - 5 * sector, 5 * sector) if sector == 4096 else read_range(boot, size - 33 * 512, 33 * 512)
        table, problems = gpt_of(head, tail, sector, size // sector)
        report['problems'] += [f'boot LUN: {p}' for p in problems]
        for name in ('boot', 'vendor_boot', 'dtbo', 'vbmeta'):
            got = extract(boot, table, name + SLOT, parts / f'{name}{SLOT}.img')
            if got is None:
                report['problems'].append(f'boot LUN has no {name}{SLOT}')
            else:
                report['recovery'][name] = str(got)
    else:
        report['problems'].append('no boot-lun.img')
    lun0 = d / 'lun0-head.img'
    if lun0.is_file() and (d / 'lun0-tail.bin').is_file():
        layout = json.loads(Path(layout_path).read_text())
        head = read_range(lun0, 0, 6 * 4096)
        table = pipa_gpt.parse_gpt(head, 'lun0')
        disk_blocks = table['backup_lba'] + 1
        table, problems = gpt_of(head, (d / 'lun0-tail.bin').read_bytes(), 4096, disk_blocks)
        report['problems'] += [f'LUN 0: {p}' for p in problems]
        measured = [(p['name'], p['first_lba'], p['last_lba']) for p in layout['partitions']]
        got = sorted(((p['name'], p['first_lba'], p['last_lba']) for p in table['partitions']), key=lambda t: t[1])
        if got != measured:
            report['problems'].append('LUN 0 GPT is not the layout measured on 24 Nov')
        userdata = next(p for p in table['partitions'] if p['name'] == 'userdata')
        if lun0.stat().st_size != userdata['first_lba'] * 4096:
            report['problems'].append('lun0-head.img does not end where userdata starts')
        for name, key in (('super', 'super'), ('vbmeta_system' + SLOT, 'vbmeta_system')):
            out = extract(lun0, table, name, parts / f'{name}.img')
            if out is None:
                report['problems'].append(f'LUN 0 has no {name}')
            else:
                report['recovery'][key] = str(out)
        if 'super' in report['recovery'] and \
                struct.unpack_from('<I', read_range(Path(report['recovery']['super']), 4096, 4))[0] != LP_GEOMETRY_MAGIC:
            report['problems'].append('super has no liblp geometry: not a dynamic-partition super image')
    else:
        report['problems'].append('no lun0-head.img / lun0-tail.bin')
    rec = report['recovery']
    if all(k in rec for k in ('boot', 'vendor_boot', 'dtbo')):
        res = rom_match.check(boot=Path(rec['boot']).read_bytes(), vendor=Path(rec['vendor_boot']).read_bytes(),
                              dtbo=Path(rec['dtbo']).read_bytes(), config=Path(config).read_bytes(),
                              proc_version=Path(proc_version).read_text())
        report['rom_match'] = res
        report['problems'] += [f'rom_match: {t}' for level, t in res if level == 'FAIL']
    if not report['problems']:
        out = d / 'recovery'
        out.mkdir(exist_ok=True)
        for key, src in rec.items():
            shutil.copyfile(src, out / f'{key}.img')
        report['recovery_dir'] = str(out)
    (d / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dir', type=Path)
    ap.add_argument('--config', required=True)
    ap.add_argument('--proc-version', required=True)
    a = ap.parse_args(argv)
    try:
        r = check(a.dir, a.config, a.proc_version)
    except (pipa_gpt.GptError, ValueError, OSError) as e:
        print(f'FAIL {e}')
        return 1
    for p in r['problems']:
        print(f'FAIL {p}')
    print('RECOVERY SET ' + (f'VERIFIED: {r["recovery_dir"]}' if not r['problems'] else 'NOT VERIFIED'))
    return 0 if not r['problems'] else 1


if __name__ == '__main__':
    sys.exit(main())
