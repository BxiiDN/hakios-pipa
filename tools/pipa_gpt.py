#!/usr/bin/env python3
"""Offline GPT reader and dual-boot plan validator for the Xiaomi Pad 6 (pipa).

Nothing here touches a device. It reads GPT dumps that were taken read-only from the tablet (one per UFS LUN), or
a JSON description of them, and holds a proposed dual-boot plan against rules that keep Android, its OTA updates,
its recovery and its data safe.

  pipa_gpt.py read DUMP...                 the partitions of each dump, as JSON (CRCs checked)
  pipa_gpt.py check PLAN TABLE...          PASS / FAIL / BLOCKED for a plan (exit 0 / 1 / 2)
  pipa_gpt.py simulate PLAN TABLE...       the layout the plan would leave, without writing anything

TABLE is a raw dump (dd of the first and last sectors of a LUN is not needed: the primary header and its entries
are enough) or a JSON file written by `read`. How to take a dump read-only: docs/DUAL-BOOT.md.

A/B slot bits in the partition attributes follow Qualcomm's ABL (PartitionTableUpdate.h): priority 48-49,
active 50, retry count 51-53, successful 54, unbootable 55. Confirm with `fastboot getvar current-slot`.
"""
import argparse
import json
import struct
import sys
import uuid
import zlib
from pathlib import Path

GPT_SIGNATURE = b'EFI PART'
MIB = 1024 * 1024

ATTR_ACTIVE = 1 << 50
ATTR_SUCCESSFUL = 1 << 54
ATTR_UNBOOTABLE = 1 << 55

# Never written by a plan, whatever it says: the boot chain, TrustZone, the modem and the calibration a phone
# cannot get back if they are lost. Matched on the name without its _a / _b suffix.
FIRMWARE = {
    'xbl', 'xbl_config', 'abl', 'tz', 'hyp', 'devcfg', 'aop', 'qupfw', 'uefisecapp', 'imagefv', 'shrm', 'cpucp',
    'keymaster', 'km4', 'featenabler', 'multiimgoem', 'storsec', 'cmnlib', 'cmnlib64', 'bluetooth', 'dsp', 'modem',
    'mdtp', 'mdtpsecapp', 'tzsc', 'rtice', 'spunvm', 'xbl_ac_config', 'xbl_ramdump', 'hw_ramdump',
    'persist', 'persistbak', 'modemst1', 'modemst2', 'fsg', 'fsc', 'ssd', 'sec', 'frp', 'devinfo', 'ddr', 'cdt',
    'limits', 'limits-cdsp', 'apdp', 'msadp', 'dip', 'splash', 'logfs', 'oops', 'qmcs', 'secdata', 'toolsfv',
    'connsec', 'cust', 'countrycode', 'ffu', 'minidump', 'rawdump', 'nvcfg', 'nvdata', 'nvram', 'ocdt',
}
# Android's own: written only by Android (OTA, fastboot flash of a stock image), never by this project's plans.
ANDROID = {'super', 'userdata', 'metadata', 'misc', 'vbmeta', 'vbmeta_system', 'vbmeta_vendor', 'dtbo',
           'vendor_boot', 'init_boot', 'recovery', 'cache', 'rescue'}
BOOT = {'boot'}


def base_name(name):
    return name[:-2] if name.endswith(('_a', '_b')) else name


class GptError(Exception):
    pass


def parse_gpt(data, source='<dump>'):
    """The partitions of a raw GPT dump: the protective MBR, the header at LBA 1, the entries. Sector size found by
    where the header is (512 or 4096: UFS LUNs are 4096)."""
    for sector in (4096, 512):
        if data[sector:sector + 8] == GPT_SIGNATURE:
            break
    else:
        raise GptError(f'{source}: no GPT header at LBA 1 (looked for 512- and 4096-byte sectors)')
    header = data[sector:sector + 92]
    (sig, revision, header_size, header_crc, _, current_lba, backup_lba, first_usable, last_usable, disk_guid,
     entries_lba, entry_count, entry_size, entries_crc) = struct.unpack('<8sIIIIQQQQ16sQIII', header)
    blank = bytearray(data[sector:sector + header_size])
    blank[16:20] = b'\0\0\0\0'
    if zlib.crc32(bytes(blank)) & 0xffffffff != header_crc:
        raise GptError(f'{source}: header CRC32 does not match: the dump is damaged or incomplete')
    start = entries_lba * sector
    table = data[start:start + entry_count * entry_size]
    if len(table) < entry_count * entry_size:
        raise GptError(f'{source}: the dump ends before the partition entries do '
                       f'(needs {start + entry_count * entry_size} bytes, has {len(data)})')
    if zlib.crc32(table) & 0xffffffff != entries_crc:
        raise GptError(f'{source}: partition entries CRC32 does not match')
    parts = []
    for i in range(entry_count):
        entry = table[i * entry_size:(i + 1) * entry_size]
        type_guid = entry[0:16]
        if type_guid == b'\0' * 16:
            continue
        first, last, attrs = struct.unpack('<QQQ', entry[32:56])
        name = entry[56:128].decode('utf-16-le').split('\0', 1)[0]
        parts.append({'name': name, 'first_lba': first, 'last_lba': last, 'attributes': attrs,
                      'type': str(uuid.UUID(bytes_le=type_guid)), 'guid': str(uuid.UUID(bytes_le=entry[16:32]))})
    return {'source': str(source), 'sector_size': sector, 'first_usable_lba': first_usable,
            'last_usable_lba': last_usable, 'disk_guid': str(uuid.UUID(bytes_le=disk_guid)),
            'backup_lba': backup_lba, 'partitions': parts}


def load_table(path):
    path = Path(path)
    data = path.read_bytes()
    if data[:1] in (b'{', b'['):
        loaded = json.loads(data)
        return loaded if isinstance(loaded, list) else [loaded]
    return [parse_gpt(data, path)]


def all_partitions(tables):
    for table in tables:
        for part in table['partitions']:
            yield table, part


def active_slot(tables):
    """'a' or 'b' from boot_a / boot_b's attribute bits; None when neither or both say active."""
    flags = {}
    for _, part in all_partitions(tables):
        if part['name'] in ('boot_a', 'boot_b'):
            flags[part['name'][-1]] = bool(part['attributes'] & ATTR_ACTIVE)
    active = [slot for slot, on in flags.items() if on]
    return active[0] if len(active) == 1 else None


def overlaps(a_first, a_last, b_first, b_last):
    return a_first <= b_last and b_first <= a_last


def free_ranges(table):
    """The usable LBA ranges no partition holds, in order."""
    used = sorted((p['first_lba'], p['last_lba']) for p in table['partitions'])
    cursor, free = table['first_usable_lba'], []
    for first, last in used:
        if first > cursor:
            free.append((cursor, first - 1))
        cursor = max(cursor, last + 1)
    if cursor <= table['last_usable_lba']:
        free.append((cursor, table['last_usable_lba']))
    return free


def check_plan(plan, tables):
    """(verdict, findings): verdict PASS, FAIL or BLOCKED; each finding (level, text)."""
    findings = []

    def say(level, text):
        findings.append((level, text))

    names = {part['name']: (table, part) for table, part in all_partitions(tables)}
    seen = {}
    for table, part in all_partitions(tables):
        if part['name'] in seen and seen[part['name']] is table:
            say('FAIL', f'partition name {part["name"]} appears twice in {table["source"]}')
        seen[part['name']] = table
        if part['first_lba'] > part['last_lba']:
            say('FAIL', f'{part["name"]}: first LBA after last LBA')
        if part['first_lba'] < table['first_usable_lba'] or part['last_lba'] > table['last_usable_lba']:
            say('FAIL', f'{part["name"]}: outside the usable area of {table["source"]}')
    for table in tables:
        ordered = sorted(table['partitions'], key=lambda p: p['first_lba'])
        for left, right in zip(ordered, ordered[1:]):
            if overlaps(left['first_lba'], left['last_lba'], right['first_lba'], right['last_lba']):
                say('FAIL', f'{left["name"]} and {right["name"]} overlap in {table["source"]}')

    slot = active_slot(tables)
    if 'boot_a' in names or 'boot_b' in names:
        if slot is None:
            say('BLOCKED', 'the active slot cannot be told from boot_a/boot_b attributes: '
                           'give it with `fastboot getvar current-slot` before any boot-partition plan')
        else:
            say('INFO', f'active slot: {slot} (from the attribute bits; confirm with fastboot getvar current-slot)')

    mode = plan.get('mode', 'ram-boot')
    if mode == 'ram-boot':
        if plan.get('writes') or plan.get('create') or plan.get('resize'):
            say('FAIL', 'mode ram-boot writes nothing, but the plan lists writes, creations or resizes')
        else:
            say('INFO', 'ram-boot: fastboot boot only; no partition is written; a reboot returns to Android')

    for write in plan.get('writes', []):
        name = write.get('partition', '')
        base = base_name(name)
        if name not in names:
            say('FAIL', f'write to {name}: no such partition in the tables given')
        elif base in FIRMWARE:
            say('FAIL', f'write to {name}: firmware or calibration partition; never written by this project')
        elif base in ANDROID:
            say('FAIL', f'write to {name}: Android owns it (OTA, verified boot, data); not written by this project')
        elif base in BOOT:
            if slot and name.endswith('_' + ('b' if slot == 'a' else 'a')):
                say('FAIL', f'write to {name}: the inactive slot is where the next OTA installs; a boot manager '
                            'there is overwritten by it, and Android would boot an image it did not verify')
            elif not write.get('backup_sha256'):
                say('FAIL', f'write to {name}: no backup_sha256 of the stock image taken first')
            elif not plan.get('android_fallback_tested'):
                say('BLOCKED', f'write to {name}: the Android path through the boot manager has not been seen to '
                               'work from RAM (fastboot boot) yet; set android_fallback_tested only after it has')
            else:
                say('WARN', f'write to {name}: allowed with backup {write["backup_sha256"][:12]}...; re-flash the '
                            'stock boot image before every OTA (docs/DUAL-BOOT.md)')
        else:
            say('WARN', f'write to {name}: not a partition this project knows; review by hand')

    for create in plan.get('create', []):
        name, size = create.get('name', ''), int(create.get('size_mib', 0)) * MIB
        if name in names:
            say('FAIL', f'create {name}: a partition of that name exists')
            continue
        if size <= 0:
            say('FAIL', f'create {name}: size_mib must be positive')
            continue
        lun = next((t for t in tables if t['source'] == create.get('lun', t['source'])), None)
        if lun is None:
            say('FAIL', f'create {name}: no table {create.get("lun")}')
            continue
        sector = lun['sector_size']
        sectors = -(-size // sector)
        align = MIB // sector
        fit = None
        for first, last in free_ranges(lun):
            start = -(-first // align) * align
            if start + sectors - 1 <= last:
                fit = (start, start + sectors - 1)
                break
        if fit:
            say('INFO', f'create {name}: fits at LBA {fit[0]}-{fit[1]} (1 MiB aligned) in {lun["source"]}')
            create['_fit'] = fit
        else:
            biggest = max((last - first + 1 for first, last in free_ranges(lun)), default=0) * sector // MIB
            say('BLOCKED', f'create {name}: {size // MIB} MiB does not fit in the free space of {lun["source"]} '
                           f'(largest gap {biggest} MiB); room means shrinking userdata, which erases it')

    for resize in plan.get('resize', []):
        name = resize.get('partition', '')
        if base_name(name) == 'userdata':
            backup_ok = plan.get('backup_verified') is True or plan.get('backup_waived_by_owner') is True
            if plan.get('userdata_erase_confirmed') is not True or not backup_ok:
                say('FAIL', 'resize userdata: erases every Android app and file; needs userdata_erase_confirmed and '
                            'either backup_verified (a backup restored once as a test) or backup_waived_by_owner, set by the owner')
            else:
                say('WARN', 'resize userdata: destructive and confirmed by the owner; not done by any tool here')
        else:
            say('FAIL', f'resize {name}: only userdata may ever be resized, and only with consent')

    levels = {level for level, _ in findings}
    verdict = 'FAIL' if 'FAIL' in levels else 'BLOCKED' if 'BLOCKED' in levels else 'PASS'
    return verdict, findings


def simulate(plan, tables):
    out = json.loads(json.dumps(tables))
    for create in plan.get('create', []):
        if '_fit' in create:
            lun = next(t for t in out if t['source'] == create.get('lun', t['source']))
            lun['partitions'].append({'name': create['name'], 'first_lba': create['_fit'][0],
                                      'last_lba': create['_fit'][1], 'attributes': 0, 'type': create.get('type', ''),
                                      'guid': '(new)'})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    read = sub.add_parser('read')
    read.add_argument('dumps', nargs='+')
    for name in ('check', 'simulate'):
        cmd = sub.add_parser(name)
        cmd.add_argument('plan')
        cmd.add_argument('tables', nargs='+')
    args = parser.parse_args(argv)
    try:
        if args.command == 'read':
            print(json.dumps([t for d in args.dumps for t in load_table(d)], indent=1))
            return 0
        tables = [t for d in args.tables for t in load_table(d)]
        plan = json.loads(Path(args.plan).read_text())
    except (OSError, GptError, json.JSONDecodeError) as error:
        print(f'pipa_gpt: {error}', file=sys.stderr)
        return 2
    verdict, findings = check_plan(plan, tables)
    if args.command == 'simulate':
        for table in simulate(plan, tables):
            print(f'== {table["source"]} ({table["sector_size"]}-byte sectors)')
            for part in sorted(table['partitions'], key=lambda p: p['first_lba']):
                size = (part['last_lba'] - part['first_lba'] + 1) * table['sector_size'] // MIB
                print(f'  {part["first_lba"]:>12} {part["last_lba"]:>12} {size:>8} MiB  {part["name"]}')
    for level, text in findings:
        print(f'{level:7} {text}')
    print(f'VERDICT {verdict}')
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[verdict]


if __name__ == '__main__':
    sys.exit(main())
