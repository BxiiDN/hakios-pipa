#!/usr/bin/env python3
"""Resolve the pipa U-Boot defconfig against U-Boot's own Kconfig tree, without building, and check what the boot
manager depends on. Uses the kconfiglib that ships with U-Boot (tools/buildman/kconfiglib.py), so the answer is
U-Boot's dependency logic, not a guess.

  check_uboot_config.py UBOOT_TREE [PROFILE_DIR]

UBOOT_TREE: U-Boot at hakios-uefi's BASE_COMMIT with hakios.patch applied (scripts/build-uboot.sh makes one).
Checks: every symbol the pipa fragment sets exists; each ends with the value asked for (a dependency can silently
undo it); the safety switches are off; the tablet's tree is the default tree and exists in dts/upstream.
Exit 0 when every check passes.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What the boot manager needs (y) and what must never be in the image (n), with why.
REQUIRED = {
    'ARCH_SNAPDRAGON': ('y', 'the Qualcomm platform'),
    'CLK_QCOM_SM8250': ('y', 'SM8250 clocks'),
    'PINCTRL_QCOM_SM8250': ('y', 'SM8250 pins'),
    'BUTTON_QCOM_PMIC': ('y', 'PM8150 power / volume-down keys'),
    'BUTTON_REMAP_PHONE_KEYS': ('y', 'volume keys move, power selects in the menu'),
    'CMD_BOOTMENU': ('y', 'the boot menu'),
    'CMD_PAUSE': ('y', 'the menu entries pause to show messages'),
    'CMD_HAKIOS': ('y', 'HakiOS entry (hakios load / boot)'),
    'CMD_BOOTEFI': ('y', 'start loader.efi'),
    'EFI_HAKIOS_USB_DEVICE': ('y', 'the loader USB transport'),
    'VIDEO': ('y', 'menu on the display'),
    'PANIC_HANG': ('y', 'a panic stays on screen instead of rebooting silently'),
    # the commands pipa.env runs
    'HUSH_PARSER': ('y', 'if / then / else in the menu entries; also builds the test command (cmd/Makefile)'),
    'CMD_ECHO': ('y', 'echo'),
    'CMD_BDI': ('y', 'bdinfo (Board information entry)'),
    'CMD_MEMINFO': ('y', 'meminfo (Board information entry)'),
    'CMD_SCSI': ('y', 'scsi scan (preboot)'),
    'FASTBOOT_FLASH': ('n', 'no flashing from this image'),
    'CMD_USB_MASS_STORAGE': ('n', 'no UFS exposed read-write to a PC'),
}


def load_kconfiglib(tree):
    sys.path.insert(0, str(tree / 'tools' / 'buildman'))
    import kconfiglib  # noqa: E402
    return kconfiglib


def merged_defconfig(tree, profile):
    parts = [tree / 'configs' / 'qcom_defconfig', tree / 'board' / 'qualcomm' / 'qcom-phone.config',
             profile / 'pipa.config']
    for part in parts:
        if not part.is_file():
            raise SystemExit(f'check_uboot_config: missing {part}')
    return '\n'.join(part.read_text() for part in parts), parts


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    tree = Path(argv[1]).resolve()
    profile = Path(argv[2]).resolve() if len(argv) > 2 else ROOT / 'uefi-profiles' / 'xiaomi' / 'pipa'
    kconfiglib = load_kconfiglib(tree)
    os.environ.update(srctree=str(tree), ARCH='arm', SRCARCH='arm', UBOOTVERSION='check', CC='cc', HOSTCC='cc',
                      LD='ld', KCONFIG_WARN_UNDEF='', CC_VERSION_TEXT='cc')
    cwd = os.getcwd()
    os.chdir(tree)
    try:
        kconf = kconfiglib.Kconfig('Kconfig', warn=False, warn_to_stderr=False)
    finally:
        os.chdir(cwd)
    text, parts = merged_defconfig(tree, profile)
    merged = Path(os.environ.get('TMPDIR', '/tmp')) / 'xiaomi_pipa_defconfig'
    merged.write_text(text)
    kconf.load_config(str(merged))

    failures = 0

    def report(ok, what):
        nonlocal failures
        print(f'{"PASS" if ok else "FAIL"}  {what}')
        failures += not ok

    # every symbol the pipa fragment names exists in this U-Boot (a typo would be ignored silently by make)
    for line in (profile / 'pipa.config').read_text().splitlines():
        line = line.strip()
        name = None
        if line.startswith('CONFIG_') and '=' in line:
            name = line[7:line.index('=')]
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            name = line[9:-len(' is not set')]
        if name:
            report(name in kconf.syms and kconf.syms[name].nodes, f'pipa.config symbol {name} exists in Kconfig')
    for name, (want, why) in REQUIRED.items():
        sym = kconf.syms.get(name)
        got = sym.str_value if sym is not None and sym.nodes else '(no such symbol)'
        report(got == want or (want == 'n' and got == ''), f'{name}={want} ({why}); resolved: {got or "n"}')
    dt = kconf.syms['DEFAULT_DEVICE_TREE'].str_value
    report(dt == 'qcom/sm8250-xiaomi-pipa', f'DEFAULT_DEVICE_TREE is {dt}')
    report((tree / 'dts' / 'upstream' / 'src' / 'arm64' / 'qcom' / 'sm8250-xiaomi-pipa.dts').is_file(),
           'dts/upstream has sm8250-xiaomi-pipa.dts')
    env = kconf.syms['ENV_DEFAULT_ENV_TEXT_FILE'].str_value
    env_path = profile / 'u-boot' / 'files' / env
    report(env == 'board/xiaomi/pipa.env' and env_path.is_file(), f'ENV_DEFAULT_ENV_TEXT_FILE is {env} (in the overlay)')
    print(f'resolved from: {", ".join(str(p.relative_to(p.parents[2]) if tree in p.parents else p) for p in parts)}')
    print('U-BOOT CONFIG PASS' if not failures else f'U-BOOT CONFIG FAIL ({failures})')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
