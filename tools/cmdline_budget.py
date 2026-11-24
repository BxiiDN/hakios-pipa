#!/usr/bin/env python3
"""Every boot line the menu of a payload can hand to XNU, against XNU's limit -- and the Data-initialisation guard.
Reads the payload volume only (docs/IPADOS-PARTITION.md, section 13).

  cmdline_budget.py payload.img

XNU's boot_args CommandLine is BOOT_LINE_LENGTH = 1024 bytes with its NUL (pexpert/arm64/boot.h), so 1023 characters;
DarwinBoot copies at most that much (DarwinBoot.c). UniXNU's menu boots an entry with its args, or -- after a confirm
choice -- with "args + ' ' + confirm_arg" (UniXNULib Main.c). Checked for every entry and choice:
  - the line is at most 1023 characters and printable ASCII;
  - an entry that resets the iPadOS Data store (sheng-data-reset=...) exists only when the root partition is not
    Android's userdata (native-ufs-root-part names another partition) and the store is persistent (sheng-data-persist=2):
    the reset then lands in that partition and nowhere else.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fat_reader import Fat  # noqa: E402

LIMIT = 1023
try:
    import tomllib
except ImportError:                                       # Python < 3.11
    tomllib = None


def lines(menu):
    for e in menu.get('entry', []):
        args = e.get('args')
        if args is None:
            continue
        confirms = e.get('confirm_args') or []
        if not confirms:
            yield e['id'], args
        for c in confirms:
            yield f'{e["id"]} + {c}', f'{args} {c}'


def check(menu):
    results = []
    say = lambda ok, text: results.append(('PASS' if ok else 'FAIL', text))
    for name, line in lines(menu):
        say(len(line) <= LIMIT and all(32 <= ord(ch) < 127 for ch in line), f'{name}: {len(line)} of {LIMIT} characters')
        words = line.split()
        if any(w.startswith('sheng-data-reset=') for w in words):
            part = next((w.split('=', 1)[1] for w in words if w.startswith('native-ufs-root-part=')), 'userdata')
            say(part != 'userdata', f'{name}: resets Data on root partition "{part}", not Android\'s userdata')
            say('sheng-data-persist=2' in words, f'{name}: the store is persistent (sheng-data-persist=2)')
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('payload', type=Path)
    a = ap.parse_args(argv)
    if tomllib is None:
        print('FAIL Python 3.11+ (tomllib) needed')
        return 1
    menu = tomllib.loads(Fat(a.payload.read_bytes()).read('EFI/UniXNU/unixnu.toml').decode())
    res = check(menu)
    for level, text in res:
        print(f'{level:4} {text}')
    bad = any(level == 'FAIL' for level, _ in res)
    print('CMDLINE BUDGET ' + ('FAIL' if bad else 'PASS'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
