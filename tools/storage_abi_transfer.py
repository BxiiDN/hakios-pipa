#!/usr/bin/env python3
"""May the live storage ABI record of the QEMU board be used by the pipa board? (docs/BOOTSTRAP.md "storage")

  storage_abi_transfer.py --audit interface-audit.json --kernel pipa/kernel.macho --plan pipa/kernel.json
                          [--unixnu UniXNU] [--dwarf mach...unstripped] [--json OUT]

UniXNU's audit-storage-interface.py writes interface-audit.json from a live QEMU/gdb stop of the QEMU board's
prelinked kernel. build-virtio-mmio-bindings.py then binds VirtioMmioBlock/RamBlock to the absolute addresses of the
original IOStorageFamily class recorded there. Those addresses are only right for another kernel when that kernel
carries the same original code at the same place. This checks exactly that, on the pipa kernel, and nothing is relaxed:

  1. the pipa plan is a prelink of the pinned 21H461 kernelcache, the kernel file is the plan's candidate, and the
     IOStorageFamily __TEXT_EXEC bytes in it hash to the plan's original_executable_sha256 (code unchanged);
  2. the recorded vtable, metaclass, protected constructor and base destructor lie in the pipa kernel's
     IOStorageFamily extents, and the vtable is preceded by its 16 zero bytes;
  3. all 190 dispatch slots read from the pipa kernel at the recorded vtable equal the record: an original target
     (no kernel name) must be the same address, a native one must be the pipa kernel's export of the same name;
  4. with --dwarf (the pipa XNU build's iokit/DEVELOPMENT/IOService.cpo), the native IOService is 0x88 bytes, the
     live size the record observed.

Exit 0 only when every check passes. This proves address and ABI identity, not block I/O on the tablet.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

KERNELCACHE = 'f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7'
MODULE = 'com.apple.iokit.IOStorageFamily'


def load_prelink(unixnu):
    sys.path.insert(0, str(Path(unixnu) / 'kits/XnuPrelink'))
    import native_prelink  # UniXNU's own Mach-O reader, the one the audit used
    return native_prelink


def ioservice_size(dwarf):
    """byte sizes of the IOService class definitions in DWARF (the XNU build's iokit/.../IOService.cpo: a linked
    Darwin kernel keeps no DWARF of its own)"""
    import re
    tool = next((t for t in ('llvm-dwarfdump', 'dwarfdump') if subprocess.run(['which', t], capture_output=True).returncode == 0), None)
    if not tool:
        return None, 'no llvm-dwarfdump'
    out = subprocess.run([tool, '--name=IOService', '--show-children=0', str(dwarf)], capture_output=True, text=True).stdout
    sizes = set()
    for die in re.split(r'\n(?=0x[0-9a-f]+: DW_TAG_)', out):   # one block per DIE
        if re.match(r'0x[0-9a-f]+: DW_TAG_(class|structure)_type', die) and 'DW_AT_name\t("IOService")' in die \
                and 'DW_AT_declaration' not in die:
            sizes |= {int(m, 16) for m in re.findall(r'DW_AT_byte_size\t\((0x[0-9a-f]+)\)', die)}
    return sizes, tool


def check(audit, kernel, plan, np, dwarf=None):
    results = []

    def require(ok, what):
        results.append({'check': what, 'pass': bool(ok)})
        return bool(ok)

    require(plan.get('original_sha256') == KERNELCACHE, 'plan: prelink of the pinned 21H461 kernelcache')
    require(hashlib.sha256(kernel).hexdigest() == plan.get('candidate_sha256'), 'kernel file is the plan candidate')
    require(audit.get('live_native_4k') is True and audit.get('method_slots') == 190
            and audit.get('abstract_complete_destructors_trap') is True
            and audit.get('live_instance_sizes') == {'IOBlockStorageDevice': 0x90, 'IOService': 0x88},
            'record: live native 4K, 190 slots, abstract destructors trap, live sizes 0x90/0x88')
    image = np.macho(kernel)
    exports = np.exports(kernel, image)
    by_name = {name: va for va, names in exports.items() for name in names}

    def read(va, length):
        at = np.backed_offset(image['segments'], va, length, len(kernel))
        return kernel[at:at + length]

    extents = [e for e in plan.get('extents', []) if e['module'] == MODULE]
    text = next((e for e in extents if e['segment'] == '__TEXT_EXEC'), None)
    const = next((e for e in extents if e['segment'] == '__DATA_CONST'), None)
    if not require(text and const, 'pipa plan has IOStorageFamily __TEXT_EXEC and __DATA_CONST extents'):
        return results
    require(hashlib.sha256(read(text['va'], text['size'])).hexdigest() == plan['original_executable_sha256'].get(MODULE),
            'IOStorageFamily original executable code unchanged in the pipa kernel')
    inside = lambda e, va: e['va'] <= va < e['va'] + e['size']
    vtable = int(audit['vtable'], 16)
    require(inside(const, vtable) and read(vtable, 16) == bytes(16), 'recorded vtable inside IOStorageFamily __DATA_CONST, 16 zero bytes before it')
    for key in ('original_protected_constructor', 'original_base_destructor'):
        require(inside(text, int(audit[key], 16)), f'recorded {key} inside IOStorageFamily __TEXT_EXEC')
    meta = int(audit['original_metaclass'], 16)
    require(any(inside(e, meta) for e in extents), 'recorded original metaclass inside IOStorageFamily')
    pointers = struct.unpack('<190Q', read(vtable + 16, 190 * 8))
    original = native = 0
    bad = []
    for row, pointer in zip(audit['methods'], pointers):
        if row['kernel_names']:
            ok = any(by_name.get(name) == pointer for name in row['kernel_names'])
            native += ok
        else:
            ok = pointer == int(row['candidate_target'], 16) and inside(text, pointer)
            original += ok
        if not ok:
            bad.append(row['slot'])
    require(not bad, f'190 dispatch slots: {original} original targets at the recorded address, {native} native by export name'
            + (f'; mismatching slots {bad[:12]}' if bad else ''))
    require(audit.get('kernel_bindings') == 176 and native == 176 and original == 14, 'binding shape 176 native + 14 original as recorded')
    if dwarf:
        sizes, tool = ioservice_size(dwarf)
        require(sizes == {0x88}, f'native IOService byte size in the pipa XNU DWARF is 0x88 (found {sorted(hex(s) for s in sizes or [])} via {tool})')
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--audit', required=True, type=Path)
    p.add_argument('--kernel', required=True, type=Path)
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--unixnu', type=Path, default=Path(__file__).resolve().parents[2] / 'hakios-work/UniXNU')
    p.add_argument('--dwarf', type=Path)
    p.add_argument('--json', type=Path)
    a = p.parse_args(argv)
    np = load_prelink(a.unixnu)
    audit = json.loads(a.audit.read_text())
    results = check(audit, a.kernel.read_bytes(), json.loads(a.plan.read_text()), np, a.dwarf)
    for r in results:
        print(('PASS ' if r['pass'] else 'FAIL ') + r['check'])
    ok = all(r['pass'] for r in results)
    summary = dict(audit_sha256=hashlib.sha256(a.audit.read_bytes()).hexdigest(), audit_candidate=audit.get('candidate_sha256'),
                   pipa_kernel_sha256=hashlib.sha256(a.kernel.read_bytes()).hexdigest(), checks=results, transfer=ok)
    if a.json:
        a.json.write_text(json.dumps(summary, indent=2) + '\n')
    print('STORAGE ABI TRANSFER ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
