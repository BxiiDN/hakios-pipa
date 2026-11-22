#!/usr/bin/env python3
"""The Adreno 650 constants as each source states them, side by side, read from the sources themselves.

  a650_check.py --linux LINUX --port UNIXNU-PIPA --hakios HAKIOS-KERNEL [--tree LIVE.dts]

Linux: drivers/gpu/drm/msm/adreno/a6xx_catalog.c (the A650 entry) and a6xx_gmu.c (the GMU chip id rule).
Port: package/A650Gmu.h. HakiOS: drivers/board/adreno_profile.h (its GMU chip id rule) and adreno.c's firmware names.
Exit 1 when two sources disagree on a value both state.
"""
import argparse
import re
import sys
from pathlib import Path


def linux_a650(linux):
    text = (linux / 'drivers/gpu/drm/msm/adreno/a6xx_catalog.c').read_text()
    entry = text[text.index('ADRENO_CHIP_IDS(0x06050002)'):]
    entry = entry[:entry.index('}, {')]
    get = lambda pattern: (re.search(pattern, entry) or [None, None])[1]
    return {'chip_id': 0x06050002, 'family': get(r'\.family = (\w+)'), 'sqe': get(r'ADRENO_FW_SQE\] = "([^"]+)"'),
            'gmu_fw': get(r'ADRENO_FW_GMU\] = "([^"]+)"'), 'zap': get(r'\.zapfw = "([^"]+)"'),
            'gmem': get(r'\.gmem = ([^,]+),'), 'prim_fifo': get(r'prim_fifo_threshold = (0x[0-9a-f]+)')}


def linux_gmu_chip(chip):
    # a6xx_gmu.c, a6xx_gmu_fw_start, for a GPU without a6xx_info->gmu_chipid (A650 has none)
    return (chip & 0xffff0000) | ((chip << 4) & 0xf000) | ((chip << 8) & 0x0f00)


def hakios_gmu_chip(chip):
    # drivers/board/adreno_profile.h adreno642_gmu_chip_id
    return (chip & 0xffff0000) | ((chip >> 8 & 0xff) << 12) | ((chip & 0xf) << 8) | ((chip >> 4 & 0xf) << 28)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--linux', type=Path, required=True)
    ap.add_argument('--port', type=Path, required=True)
    ap.add_argument('--hakios', type=Path, required=True)
    a = ap.parse_args(argv)
    lx = linux_a650(a.linux)
    gmu_h = (a.port / 'package/A650Gmu.h').read_text()
    port_chip = int(re.search(r'A650_GMU_CHIP_ID (0x[0-9a-fA-F]+)', gmu_h)[1], 16)
    adreno_c = (a.hakios / 'drivers/board/adreno.c').read_text()
    hakios_fw = sorted(set(re.findall(r'"(a6\d0_[a-z]+\.[a-z0-9]+)"', adreno_c)))
    rule_text = (a.hakios / 'drivers/board/adreno_profile.h').read_text()
    assert 'adreno642_gmu_chip_id' in rule_text
    bad = 0

    def row(what, ok, detail):
        nonlocal bad
        bad += not ok
        print(f'{"PASS" if ok else "FAIL":5} {what}: {detail}')

    row('chip id, Linux vs port', lx['chip_id'] == port_chip, f'{lx["chip_id"]:#010x} / {port_chip:#010x}')
    lg, hg = linux_gmu_chip(port_chip), hakios_gmu_chip(port_chip)
    row('GMU chip id rule, Linux vs HakiOS, for this chip', lg == hg, f'{lg:#010x} / {hg:#010x}')
    print(f'INFO  Linux A650: family {lx["family"]}, firmware {lx["sqe"]}, {lx["gmu_fw"]}, {lx["zap"]}, gmem {lx["gmem"]}, '
          f'prim_fifo {lx["prim_fifo"]}')
    row('HakiOS adreno.c asks for A650 firmware', any(f.startswith('a650_') for f in hakios_fw),
        f'it names {", ".join(hakios_fw)} (A660 family, Linux ADRENO_6XX_GEN4)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
