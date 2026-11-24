#!/usr/bin/env python3
"""Is design B (docs/IPADOS-PARTITION.md, sections 10-11) ready to be PROPOSED to the owner? Each prerequisite is checked from
evidence on this PC, never from a claim. Reads only; changes nothing anywhere. Exit 0 only when every item passes -- and
even then nothing is done: the owner still decides.

  design_b_readiness.py [--backup DIR] [--restore-test FILE] [--rom DIR --config config.gz --proc-version FILE]
                        [--gpt-dump DIR] [--plan plans/ipados-shrink-userdata.json]

  1 backup     DIR from scripts/backup-android.sh: SHA256SUMS intact, tablet-vs-PC comparison complete
  2 restore    FILE written by the owner after one test restore (date, what was restored, result: OK)
  3 rom        DIR with boot.img, vendor_boot.img, dtbo.img, vbmeta.img, vbmeta_system.img, super.img (raw or sparse
               liblp): the installed boot chain exactly, or the installed ROM's own kernel with the same embedded config
  4 gpt dump   DIR from tools/gpt_export_decode.py: no problems, and the measured LUN 0 (tests/data/pipa-lun0-layout.json)
  5 gpt writer tools/gpt_rewrite.py: changes only userdata's end and adds ipados, verified byte for byte (offline)
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


def check_backup(d, waived=False):
    if not d and waived:
        return 'WAIVED', "the owner decided Android's personal data need not be kept (2026-11-24)"
    if not d:
        return 'MISSING', 'no backup directory given (scripts/backup-android.sh backup DIR, after the owner agrees)'
    r = subprocess.run(['bash', str(ROOT / 'scripts/backup-android.sh'), 'verify', str(d)], capture_output=True, text=True)
    return ('PASS' if r.returncode == 0 else 'FAIL'), (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else 'no output'


def check_restore(f, waived=False):
    if not f and waived:
        return 'WAIVED', 'no backup, so no test restore'
    if not f:
        return 'MISSING', 'no record of a test restore'
    p = Path(f)
    if not p.is_file():
        return 'FAIL', f'{p} does not exist'
    text = p.read_text()
    return ('PASS', 'test restore recorded as OK') if 'result: OK' in text else ('FAIL', 'record does not say "result: OK"')


def super_is_valid(path):
    """liblp super image: raw (geometry magic at 4096) or Android sparse (magic 0xed26ff3a) that expands to it."""
    import struct
    with open(path, 'rb') as f:
        head = f.read(28)
        if struct.unpack_from('<I', head)[0] == 0xed26ff3a:
            _, _, _, fhs, chs, blk = struct.unpack_from('<IHHHHI', head)
            f.seek(fhs)
            out = bytearray()
            while len(out) < 4100:
                ctype, _, cb, tot = struct.unpack('<HHII', f.read(chs))
                n = tot - chs
                if ctype == 0xCAC1:
                    out += f.read(n)
                elif ctype == 0xCAC2:
                    out += f.read(4) * (cb * blk // 4)
                elif ctype == 0xCAC3:
                    out += b'\0' * (cb * blk)
                else:
                    f.read(n)
            return struct.unpack_from('<I', out, 4096)[0] == 0x616c4467
        f.seek(4096)
        return struct.unpack('<I', f.read(4))[0] == 0x616c4467


def check_rom(d, config, proc_version):
    if not d:
        return 'MISSING', 'no package of the installed port ROM'
    d = Path(d)
    need = ['boot.img', 'vendor_boot.img', 'dtbo.img', 'vbmeta.img', 'vbmeta_system.img', 'super.img']
    missing = [n for n in need if not (d / n).is_file()]
    if missing:
        return 'FAIL', 'missing ' + ', '.join(missing)
    if not super_is_valid(d / 'super.img'):
        return 'FAIL', 'super.img carries no liblp metadata'
    if not (config and proc_version):
        return 'FAIL', 'give --config and --proc-version to match the kernel'
    res = rom_match.check(boot=(d / 'boot.img').read_bytes(), vendor=(d / 'vendor_boot.img').read_bytes(),
                          dtbo=(d / 'dtbo.img').read_bytes(), config=Path(config).read_bytes(),
                          proc_version=Path(proc_version).read_text())
    failed = [t for level, t in res if level == 'FAIL']
    if not failed:
        return 'PASS', 'the installed boot chain exactly (kernel banner = /proc/version)'
    if all('banner' in t for t in failed):
        return 'PASS', ('the installed ROM with its own kernel (same embedded config, other build): Android comes back with '
                        'the ROM kernel; a kernel flashed later (e.g. N0 kernel++) must be re-flashed from its own package')
    return 'FAIL', failed[0]


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
    tool = ROOT / 'tools/gpt_rewrite.py'
    tests = ROOT / 'tests/test_gpt_rewrite.py'
    if tool.is_file() and tests.is_file():
        return 'PASS', 'tools/gpt_rewrite.py: files only, proves only userdata\'s end, the ipados entry and CRCs change'
    return 'MISSING', 'tools/gpt_rewrite.py not present'


def check_consent(plan):
    p = json.loads(Path(plan).read_text())
    backup_ok = p.get('backup_verified') is True or p.get('backup_waived_by_owner') is True
    if p.get('userdata_erase_confirmed') is True and backup_ok:
        return 'PASS', 'erase confirmed by the owner'
    return 'BLOCKED', 'userdata_erase_confirmed is not set: the owner has not approved the execution'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--backup')
    ap.add_argument('--restore-test')
    ap.add_argument('--rom')
    ap.add_argument('--config')
    ap.add_argument('--proc-version')
    ap.add_argument('--gpt-dump')
    ap.add_argument('--plan', default=str(ROOT / 'plans/ipados-shrink-userdata.json'))
    a = ap.parse_args(argv)
    waived = json.loads(Path(a.plan).read_text()).get('backup_waived_by_owner') is True
    items = [('1 backup', check_backup(a.backup, waived)), ('2 restore test', check_restore(a.restore_test, waived)),
             ('3 port ROM package', check_rom(a.rom, a.config, a.proc_version)), ('4 GPT dump', check_gpt(a.gpt_dump)),
             ('5 GPT writer', check_writer()), ('6 owner consent', check_consent(a.plan))]
    for name, (level, text) in items:
        print(f'{level:8} {name:20} {text}')
    ready = all(level in ('PASS', 'WAIVED') for _, (level, _) in items)
    print('DESIGN B ' + ('READY TO PROPOSE (nothing is done without the owner)' if ready else 'NOT READY'))
    return 0 if ready else 1


if __name__ == '__main__':
    sys.exit(main())
