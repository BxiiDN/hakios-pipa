#!/usr/bin/env python3
"""Every symbol an iOS Mach-O imports, looked up in the library it is bound to inside a dyld shared cache.

The GPU addon pieces (libvulkan_freedreno.dylib, NativeAdrenoMetal.bundle, adrenoprobed) are built with a newer
iphoneos SDK than the target (18.5 / 26.5 against iPadOS 17.7.11). minos 17.0 makes the linker weak-bind what is
marked newer, but a symbol the 17.7.11 libraries do not export at all is a dyld failure at load. This answers, from
the target's own cache, whether each two-level import resolves:

  dsc_import_check.py --cache dyld_shared_cache_arm64 --ipsw-tool ipsw [--json OUT] MACHO...

The exports come from `ipsw dyld tbd` (text stubs generated from the cache, re-exported libraries followed); the
imports from `llvm-nm -m -u` ("(from Foundation)"). Weak imports that are missing are reported separately: dyld
binds them to 0, so they are only a finding if the code calls them unguarded. Nothing from the cache is written
outside the scratch directory given by --work (the .tbd files are Apple-derived: keep them local).
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

LIST_KEYS = ('symbols', 'objc-classes', 'objc-eh-types', 'objc-ivars', 'weak-symbols', 'thread-local-symbols')


def tbd_exports(text):
    """(exported names with the Mach-O spelling, re-exported install names) of a tbd-v4 document."""
    names, reexports = set(), []
    # flatten the YAML flow lists: "key: [ a, b,\n c ]"
    for key, body in re.findall(r'^\s*(?:- )?\s*([a-z-]+):\s*\[([^\]]*)\]', text, re.M | re.S):
        items = [x.strip().strip("'\"") for x in body.replace('\n', ' ').split(',') if x.strip()]
        if key == 'libraries':
            reexports += items
        elif key == 'objc-classes':
            for c in items:
                names.update({f'_OBJC_CLASS_$_{c}', f'_OBJC_METACLASS_$_{c}'})
        elif key == 'objc-eh-types':
            names.update(f'_OBJC_EHTYPE_$_{c}' for c in items)
        elif key == 'objc-ivars':
            names.update(f'_OBJC_IVAR_$_{c}' for c in items)
        elif key in LIST_KEYS:
            names.update(items)
    return names, reexports


def imports(macho):
    """[(symbol, library leaf, weak)] from llvm-nm's two-level namespace output."""
    out = subprocess.run(['llvm-nm', '-m', '-u', str(macho)], capture_output=True, text=True, check=True).stdout
    result = []
    for line in out.splitlines():
        m = re.match(r'\s*\(undefined\)\s+(weak\s+)?external\s+(\S+)(?:\s+\(from ([^)]+)\))?', line)
        if m:
            result.append((m.group(2), m.group(3), bool(m.group(1))))
    return result


def dylibs(macho):
    out = subprocess.run(['llvm-objdump', '--macho', '--dylibs-used', str(macho)], capture_output=True, text=True,
                         check=True).stdout
    return [line.strip().split(' (')[0] for line in out.splitlines()[1:] if line.strip()]


def leaf(install_name):
    name = install_name.rsplit('/', 1)[-1]
    return re.sub(r'(\.[A-Z0-9]+)?\.dylib$', '', name) if name.endswith('.dylib') else name


def main():
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('--cache', required=True)
    a.add_argument('--ipsw-tool', required=True)
    a.add_argument('--work', type=Path)
    a.add_argument('--json', type=Path)
    a.add_argument('machos', nargs='+', type=Path)
    args = a.parse_args()
    work = args.work or Path(tempfile.mkdtemp(prefix='dsc-tbd-'))
    work.mkdir(parents=True, exist_ok=True)
    cache = {}

    def exports_of(install_name, seen=()):
        if install_name in cache:
            return cache[install_name]
        out = work / (install_name.strip('/').replace('/', '_') + '.d')
        out.mkdir(exist_ok=True)
        r = subprocess.run([args.ipsw_tool, 'dyld', 'tbd', args.cache, install_name, '-o', str(out)],
                           capture_output=True, text=True)
        files = list(out.glob('*.tbd'))
        if r.returncode or not files:
            cache[install_name] = None   # not in the cache
            return None
        names, reexports = tbd_exports(files[0].read_text())
        for sub in reexports:
            if sub not in seen and sub != install_name:
                more = exports_of(sub, seen + (install_name,))
                if more:
                    names |= more
        cache[install_name] = names
        return names

    report, failed = {}, False
    for macho in args.machos:
        libs = {leaf(d): d for d in dylibs(macho) if not d.startswith('@')}
        entry = dict(libraries={}, missing=[], missing_weak=[], unresolved_library=[], checked=0)
        for d in libs.values():
            entry['libraries'][d] = exports_of(d) is not None
            if not entry['libraries'][d]:
                entry['unresolved_library'].append(d)
        for sym, lib, weak in imports(macho):
            if lib is None or lib not in libs:
                continue   # flat or own (@rpath) binding: not a cache lookup
            names = exports_of(libs[lib])
            entry['checked'] += 1
            if names is None or sym not in names:
                entry['missing_weak' if weak else 'missing'].append(f'{sym} ({lib})')
        failed |= bool(entry['missing'] or entry['unresolved_library'])
        report[str(macho)] = entry
        print(f"{'FAIL' if entry['missing'] or entry['unresolved_library'] else 'PASS'}  {macho.name}: "
              f"{entry['checked']} imports from {len(libs)} libraries; missing {len(entry['missing'])}, "
              f"missing weak {len(entry['missing_weak'])}, libraries not in cache {len(entry['unresolved_library'])}")
        for s in entry['missing'][:40] + entry['unresolved_library']:
            print('   ', s)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + '\n')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
