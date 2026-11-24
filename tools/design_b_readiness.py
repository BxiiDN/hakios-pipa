#!/usr/bin/env python3
"""Is design B (docs/IPADOS-PARTITION.md, sections 10-11) ready to be PROPOSED to the owner? Each prerequisite is checked from
evidence on this PC, never from a claim. Reads only; changes nothing anywhere. Exit 0 only when every item passes -- and
even then nothing is done: the owner still decides.

  design_b_readiness.py [--backup DIR] [--restore-test FILE] [--rom DIR --config config.gz --uname-r R --uname-v V]
                        [--gpt-dump DIR] [--plan plans/ipados-shrink-userdata.json]

  1 backup     DIR from scripts/backup-android.sh: SHA256SUMS intact, tablet-vs-PC comparison complete
  2 restore    FILE written by the owner after one test restore (date, what was restored, result: OK)
  3 rom        DIR with boot.img, vendor_boot.img, dtbo.img (tools/rom_match.py PASS against the tablet) and the rest of
               the installed ROM's flashable images (vbmeta.img, vbmeta_system.img, super.img or its dynamic images)
  4 gpt dump   DIR from tools/gpt_export_decode.py: no problems, and the measured LUN 0 (tests/data/pipa-lun0-layout.json)
  5 gpt writer the tool that changes only userdata's end and adds ipados, verified byte for byte -- not written yet
  6 consent    the plan's userdata_erase_confirmed and backup_verified, set by the owner
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import rom_match  # noqa: E402

LAYOUT = ROOT / 'tests/data/pipa-lun0-layout.json'


def check_backup(d):
    if not d:
        return 'MISSING', 'no backup directory given (scripts/backup-android.sh backup DIR, after the owner agrees)'
    r = subprocess.run(['bash', str(ROOT / 'scripts/backup-android.sh'), 'verify', str(d)], capture_output=True, text=True)
    return ('PASS' if r.returncode == 0 else 'FAIL'), (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else 'no output'


def check_restore(f):
    if not f:
        return 'MISSING', 'no record of a test restore'
    p = Path(f)
    if not p.is_file():
        return 'FAIL', f'{p} does not exist'
    text = p.read_text()
    return ('PASS', 'test restore recorded as OK') if 'result: OK' in text else ('FAIL', 'record does not say "result: OK"')


def check_rom(d, config, uname_r, uname_v):
    if not d:
        return 'MISSING', 'no package of the installed port ROM (only the porter has it)'
    d = Path(d)
    need = ['boot.img', 'vendor_boot.img', 'dtbo.img', 'vbmeta.img', 'vbmeta_system.img']
    missing = [n for n in need if not (d / n).is_file()]
    if not ((d / 'super.img').is_file() or all((d / f'{n}.img').is_file() for n in ('system', 'vendor', 'product'))):
        missing.append('super.img (or system/vendor/product images)')
    if missing:
        return 'FAIL', 'missing ' + ', '.join(missing)
    if not (config and uname_r and uname_v):
        return 'FAIL', 'give --config, --uname-r and --uname-v to match the kernel'
    res = rom_match.check(boot=(d / 'boot.img').read_bytes(), vendor=(d / 'vendor_boot.img').read_bytes(),
                          dtbo=(d / 'dtbo.img').read_bytes(), config=Path(config).read_bytes(), uname_r=uname_r, uname_v=uname_v)
    bad = [t for level, t in res if level == 'FAIL']
    return ('FAIL', bad[0]) if bad else ('PASS', 'boot/vendor_boot/dtbo are the installed ROM (rom_match.py)')


def check_gpt(d):
    if not d:
        return 'MISSING', 'no decoded GPT export (Tools > GPT export (QR), then tools/gpt_export_decode.py)'
    d = Path(d)
    try:
        report = json.loads((d / 'report.json').read_text())
    except (OSError, ValueError):
        return 'FAIL', f'no report.json in {d}'
    if report['problems']:
        return 'FAIL', report['problems'][0]
    layout = json.loads(LAYOUT.read_text())
    if (report['last_usable_lba'], report['partitions']) != (layout['last_usable_lba'], len(layout['partitions'])):
        return 'FAIL', 'the dump is not the LUN 0 measured on 24 Nov'
    for name in ('head', 'tail'):
        if hashlib.sha256((d / f'{name}.bin').read_bytes()).hexdigest() != report[f'{name}_sha256']:
            return 'FAIL', f'{name}.bin changed since it was decoded'
    return 'PASS', f'primary and backup GPT of LUN 0 kept (head {report["head_sha256"][:12]}...)'


def check_writer():
    return 'MISSING', 'not written on purpose: it is built only after items 1-4 pass'


def check_consent(plan):
    p = json.loads(Path(plan).read_text())
    ok = p.get('userdata_erase_confirmed') is True and p.get('backup_verified') is True
    return ('PASS', 'both set by the owner') if ok else ('BLOCKED', 'userdata_erase_confirmed and backup_verified are not both true')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--backup')
    ap.add_argument('--restore-test')
    ap.add_argument('--rom')
    ap.add_argument('--config')
    ap.add_argument('--uname-r')
    ap.add_argument('--uname-v')
    ap.add_argument('--gpt-dump')
    ap.add_argument('--plan', default=str(ROOT / 'plans/ipados-shrink-userdata.json'))
    a = ap.parse_args(argv)
    items = [('1 backup', check_backup(a.backup)), ('2 restore test', check_restore(a.restore_test)),
             ('3 port ROM package', check_rom(a.rom, a.config, a.uname_r, a.uname_v)), ('4 GPT dump', check_gpt(a.gpt_dump)),
             ('5 GPT writer', check_writer()), ('6 owner consent', check_consent(a.plan))]
    for name, (level, text) in items:
        print(f'{level:8} {name:20} {text}')
    ready = all(level == 'PASS' for _, (level, _) in items)
    print('DESIGN B ' + ('READY TO PROPOSE (nothing is done without the owner)' if ready else 'NOT READY'))
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
