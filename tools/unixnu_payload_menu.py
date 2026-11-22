#!/usr/bin/env python3
"""Run UniXNU's real payload builder (scripts/unixnu/payload.py build()) on the pipa port's real board.toml and
return the \\EFI\\UniXNU\\unixnu.toml it writes, the kernel command line, and every file it stages.

  unixnu_payload_menu.py UNIXNU UNIXNU-PIPA [--json]

Only what needs Apple's files or host tools that are not part of the menu is replaced, the way UniXNU's own tests do
it (scripts/unixnu/test_*.py use SimpleNamespace contexts):
- the kernel is a 4 KiB stand-in file (payload.py copies it and runs llvm-nm on it for the PMGR check);
- util.run is answered in-process: llvm-nm reports `_sheng_pmgr_run`, the ADT tool writes nothing;
- devicetree.compile_hardware / generate (dtc and the ADT) return stand-ins;
- write_volume (mtools) copies the staged tree out instead of making a FAT image.
Everything that decides the menu and the kernel arguments -- check_args, check_native_root's argument rules,
[payload.install], [payload.dualboot], the menu text -- is UniXNU's own code, run unchanged.
"""
import json
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path
from types import SimpleNamespace


def build_menu(unixnu, port):
    unixnu, port = Path(unixnu).resolve(), Path(port).resolve()
    sys.path.insert(0, str(unixnu / 'scripts'))
    from unixnu import devicetree, payload, util  # noqa: E402  (UniXNU's own modules)

    board = tomllib.loads((port / 'board.toml').read_text())
    captured = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        kernel = tmp / 'kernel.macho'
        kernel.write_bytes(b'\xcf\xfa\xed\xfe' + b'\0' * 4092)

        def fake_run(command, capture=False, **_):
            name = Path(str(command[0])).name
            if 'nm' in name:
                return '0000000000000000 T _sheng_pmgr_run\n'
            captured.setdefault('runs', []).append([str(c) for c in command])
            return '' if capture else None

        def fake_volume(stage, image, label, size_mib):
            out = tmp / 'volume'
            shutil.copytree(stage, out)
            captured['label'], captured['size_mib'] = label, size_mib
            captured['files'] = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
            captured['menu'] = (out / 'EFI/UniXNU/unixnu.toml').read_text()
            image.write_bytes(b'')

        saved = (payload.run, payload.write_volume, payload.tool, devicetree.compile_hardware, devicetree.generate)
        payload.run, payload.write_volume = fake_run, fake_volume
        payload.tool = lambda name, hint='': name
        devicetree.compile_hardware = lambda ctx: kernel
        devicetree.generate = lambda *a, **k: b'ADT stand-in'
        try:
            logs = tmp / 'logs'
            logs.mkdir()
            ctx = SimpleNamespace(board=board, tree=unixnu, work=tmp / 'out', logs=logs, device=port, uefi=None,
                                  schema_version=board.get('schema_version', 1), config={}, config_name=None,
                                  config_path=tmp / 'none.config',
                                  args=SimpleNamespace(kernel=str(kernel), kernel_arg=[], trust_cache=None,
                                                       owner_trust_cache=None, data_ramdisk=None, skip_setup=False,
                                                       gpu_addon=None,
                                                       # the ADT is a stand-in here; the seed only has to be present
                                                       unique_chip_id='0' * 16))
            payload.build(ctx, kernel)
            report = json.loads((tmp / 'out' / 'payload' / 'payload.json').read_text())
        finally:
            (payload.run, payload.write_volume, payload.tool, devicetree.compile_hardware, devicetree.generate) = saved
            sys.path.remove(str(unixnu / 'scripts'))
    return {'menu_text': captured['menu'], 'menu': tomllib.loads(captured['menu']), 'files': captured['files'],
            'kernel_args': report['kernel_args'].split(), 'volume': captured['label'], 'board': board}


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    result = build_menu(argv[1], argv[2])
    if '--json' in argv:
        result.pop('board')
        print(json.dumps(result, indent=1))
    else:
        print(result['menu_text'])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
