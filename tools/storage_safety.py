#!/usr/bin/env python3
"""Storage safety of an iPadOS image for a tablet whose Android must survive, judged on the menu UniXNU's payload
builder really writes (tools/unixnu_payload_menu.py) and on the tablet's GPT when it is given.

  storage_safety.py UNIXNU UNIXNU-PIPA [--gpt LAYOUT.json|DUMP.bin ...]

Offline verdict (exit 0 / 1): no entry and no kernel argument may reset, erase or write storage outside iPadOS's own
root partition: the root must not be Android's userdata, the Data store (data-persist=2), its reset (data-reset) and the
log window are allowed only with the root on a partition of iPadOS's own (the driver writes them inside the root
partition and refuses all of them on userdata, patch 0002); a confirm choice is judged with its entry's arguments, as the
menu joins them (UniXNULib Main.c); and the menu must be Android-first. With --gpt, also whether the tablet has the root partition
the image names, clear of userdata (exit 2 = BLOCKED: not ready for a hardware boot).

What writes, from UniXNU-pipa drivers/ShengUfs (RootCommands.h hostWrite4k, NativeUfs.cpp): only two windows, the Data
store (sheng-data-persist=2) and the log/export region (sheng-log=1 / log=1), both inside the root partition. The
root volumes themselves are read-only block devices (doFormatMedia: kIOReturnNotWritable). sheng-data-reset=N clears
the Data store. hakios-pipa patch 0002 makes the driver refuse both windows when the root partition is "userdata".
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# argument -> why it is refused (a callable gets the value)
FORBIDDEN = {   # names without the sheng- prefix (args_of folds it)
    'data-reset': 'clears the iPadOS Data store on storage',
    'data-persist': lambda v: 'opens a write window on storage (mode 2)' if v == '2' else None,
    'log': lambda v: 'opens the UFS log/export write window' if v not in ('', '0') else None,
}
WORDS = re.compile(r'erase|wipe|format|reset-data|data-reset', re.I)


def args_of(line):
    """Arguments by name, with UniXNU's two spellings folded together: 4a41c7e (2026-11-10) dropped the sheng- prefix
    of every boot argument (sheng-data-persist is data-persist), and a driver of either age may read either."""
    out = {}
    for item in line.split():
        key, _, value = item.partition('=')
        if key.startswith('sheng-'):
            key = key[len('sheng-'):]
        out.setdefault(key, []).append(value)
    return out


def check_args(where, line, say):
    args = args_of(line)
    root = '1' in args.get('native-ufs-root', [])
    part = (args.get('native-ufs-root-part') or ['userdata'])[-1] if root else None
    own = root and part != 'userdata'
    for key, values in args.items():
        rule = FORBIDDEN.get(key)
        for value in values:
            why = rule(value) if callable(rule) else rule
            if not why:
                continue
            if own:
                say('PASS', f'{where}: {key}={value} writes only inside the root partition "{part}" (refused on userdata)')
            else:
                say('FAIL', f'{where}: {key}={value} (or sheng-{key}) {why}, and the root is not a partition of iPadOS\'s own')
    if root:
        if part == 'userdata':
            say('FAIL', f'{where}: native-ufs-root=1 with the root on Android\'s userdata (add native-ufs-root-part=<own partition>)')
        else:
            say('PASS', f'{where}: root on partition "{part}", not userdata')
        return part
    say('PASS', f'{where}: no UFS root (nothing on the tablet\'s storage is used as root)')
    return None


def judge(built, layouts=None):
    findings = []
    say = lambda level, text: findings.append((level, text))
    menu = built['menu']
    entries = menu.get('entry', [])
    ids = [e.get('id') for e in entries]
    boot = menu.get('boot', {})
    say('PASS' if boot.get('default') == 'android' else 'FAIL', f'default entry: {boot.get("default")}')
    say('PASS' if boot.get('timeout') == 10 else 'FAIL', f'timeout: {boot.get("timeout")} s')
    first = entries[0] if entries else {}
    say('PASS' if (first.get('id'), first.get('type'), first.get('action')) == ('android', 'action', 'reset') else 'FAIL',
        f'first entry: {first.get("id")} ({first.get("type")} {first.get("action")})')
    say('PASS' if 'xnu' in ids else 'FAIL', 'iPadOS entry present')
    say('PASS' if 'recovery' in ids else 'FAIL', 'recovery entry present')
    parts = set()
    for entry in entries:
        where = f'entry {entry.get("id")}'
        if (entry.get('confirm_args') or entry.get('id') == 'install') and entry.get('type') != 'xnu':
            say('FAIL', f'{where}: an install/confirm entry that is not an iPadOS boot ({entry.get("confirm", "")!r})')
        for text in (entry.get('title', ''), entry.get('confirm', '')):
            if WORDS.search(text):
                say('FAIL', f'{where}: destructive wording {text!r}')
        if entry.get('type') == 'xnu':
            parts.add(check_args(where, entry.get('args', ''), say))
        for extra in entry.get('confirm_args', []):
            check_args(f'{where} (confirm choice {extra})', f'{entry.get("args", "")} {extra}', say)
    root_part = next((p for p in parts if p), None)
    verdict = 'FAIL' if any(level == 'FAIL' for level, _ in findings) else 'PASS'
    hardware = None
    if layouts is not None:
        hardware = 'PASS'
        found = [p for t in layouts for p in t['partitions'] if p['name'] == root_part] if root_part else []
        userdata = [p for t in layouts for p in t['partitions'] if p['name'] == 'userdata']
        if not root_part:
            say('INFO', 'no UFS root: nothing on the tablet is read as root')
        elif not found:
            say('BLOCKED', f'the tablet has no partition "{root_part}": the image can boot, but iPadOS has no root')
            hardware = 'BLOCKED'
        else:
            for u in userdata:
                if found[0]['first_lba'] <= u['last_lba'] and u['first_lba'] <= found[0]['last_lba']:
                    say('FAIL', f'"{root_part}" overlaps userdata')
                    hardware = 'FAIL'
            if hardware == 'PASS':
                say('PASS', f'"{root_part}" exists and is clear of userdata')
    return verdict, hardware, findings


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    from unixnu_payload_menu import build_menu
    built = build_menu(argv[1], argv[2])
    layouts = None
    if '--gpt' in argv:
        import pipa_gpt
        layouts = [t for path in argv[argv.index('--gpt') + 1:] for t in pipa_gpt.load_table(path)]
    verdict, hardware, findings = judge(built, layouts)
    for level, text in findings:
        print(f'{level:7} {text}')
    print(f'STORAGE OFFLINE {verdict}')
    if hardware:
        print(f'STORAGE ON THIS TABLET {hardware}')
    if verdict != 'PASS':
        return 1
    return 2 if hardware in ('BLOCKED', 'FAIL') else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
