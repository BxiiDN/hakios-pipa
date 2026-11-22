#!/usr/bin/env python3
"""What a pipa device tree says about the hardware a port needs, with the node each value came from.

  pipa_hw_facts.py TREE.dts [--json]        the facts
  pipa_hw_facts.py TREE.dts --check         the facts held to what this repository assumes (exit 1 on a mismatch)

TREE.dts is a decompiled live tree (`dtc -I dtb -O dts /sys/firmware/fdt`, scripts/extract-live-dt.sh) or any source
with its includes merged. It reads values; it invents none: a part the tree does not describe is reported missing.
The parser is HakiOS's tools/devicetree.py (found through HAKIOS_KERNEL, default ../hakios-work/hakios-xnu-kernel),
or a copy of its parse_dts beside this file.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parser():
    kernel = Path(os.environ.get('HAKIOS_KERNEL', ROOT.parent / 'hakios-work' / 'hakios-xnu-kernel'))
    sys.path.insert(0, str(kernel / 'tools'))
    try:
        from devicetree import parse_dts
    except ImportError as error:
        raise SystemExit(f'pipa_hw_facts: needs HakiOS tools/devicetree.py ({error}); set HAKIOS_KERNEL')
    return parse_dts


def cells(value):
    return [int(x, 0) for x in re.findall(r'0x[0-9a-fA-F]+|\b\d+\b', (value or '').split('>')[0])]


def string(value):
    return (value or '').strip().strip('"').split('\\0')[0]


def path_of(node):
    parts = []
    while node is not None:
        parts.append(node.name)
        node = node.parent
    return '/' + '/'.join(p for p in reversed(parts) if p not in ('/', ''))


def compatible(node, *needles):
    text = node.props.get('compatible', '')
    return any(n in text for n in needles)


def facts(text):
    root = parser()(text)
    out = {'model': None, 'panels': [], 'touch': [], 'speakers': [], 'backlight': [], 'wifi': [], 'bluetooth': [],
           'gpu': None, 'gmu': None, 'cpufreq': None, 'missing': []}
    out['model'] = string(root.props.get('model'))
    for node in root.walk():
        where = path_of(node)
        if node.name.startswith('qcom,mdss_dsi_') and 'qcom,mdss-dsi-panel-name' in node.props:
            name = string(node.props['qcom,mdss-dsi-panel-name'])
            if not re.search(r'\bm82\b', name):
                continue
            timing = next((c for c in node.walk() if 'qcom,mdss-dsi-panel-width' in c.props), None)
            out['panels'].append({
                'node': where, 'name': name, 'type': string(node.props.get('qcom,mdss-dsi-panel-type')),
                'dfps_hz': cells(node.props.get('qcom,dsi-supported-dfps-list')),
                'bl_max': (cells(node.props.get('qcom,mdss-dsi-bl-max-level')) or [None])[0],
                'width_per_dsi': (cells(timing.props.get('qcom,mdss-dsi-panel-width')) or [None])[0] if timing else None,
                'height': (cells(timing.props.get('qcom,mdss-dsi-panel-height')) or [None])[0] if timing else None,
                'base_hz': (cells(timing.props.get('qcom,mdss-dsi-panel-framerate')) or [None])[0] if timing else None,
            })
        elif compatible(node, 'NVT-ts-spi', 'novatek,NVT-ts'):
            irq = cells(node.props.get('novatek,irq-gpio'))
            out['touch'].append({'node': where, 'compatible': string(node.props['compatible']),
                                 'bus': node.parent.name if node.parent else None,
                                 'spi_hz': (cells(node.props.get('spi-max-frequency')) or [None])[0],
                                 'irq_tlmm': irq[1] if len(irq) > 1 else None,
                                 'pen': 'novatek,pen-support' in node.props})
        elif compatible(node, 'aw882xx'):
            reset, irq = cells(node.props.get('reset-gpio')), cells(node.props.get('irq-gpio'))
            out['speakers'].append({'node': where, 'bus': node.parent.name, 'addr': cells(node.props.get('reg'))[0],
                                    'channel': (cells(node.props.get('sound-channel')) or [None])[0],
                                    'reset_tlmm': reset[1] if len(reset) > 1 else None,
                                    'irq_tlmm': irq[1] if len(irq) > 1 else None,
                                    'status': string(node.props.get('status'))})
        elif compatible(node, 'ktz8866'):
            out['backlight'].append({'node': where, 'bus': node.parent.name, 'addr': cells(node.props.get('reg'))[0]})
        elif compatible(node, 'cnss-qca6390'):
            out['wifi'].append({'node': where, 'compatible': string(node.props['compatible'])})
        elif compatible(node, 'qca,qca6390'):
            out['bluetooth'].append({'node': where, 'compatible': string(node.props['compatible'])})
        elif node.name.startswith('qcom,kgsl-3d0@'):
            out['gpu'] = {'node': where, 'chip_id': (cells(node.props.get('qcom,chipid')) or [None])[0],
                          'reg': cells(node.props.get('reg'))[:2],
                          'highest_bank_bit': (cells(node.props.get('qcom,highest-bank-bit')) or [None])[0],
                          'bins_mhz': {}}
            for bins in node.walk():
                if bins.name.startswith('qcom,gpu-pwrlevels') and 'qcom,speed-bin' in bins.props:
                    out['gpu']['bins_mhz'][cells(bins.props['qcom,speed-bin'])[0]] = [
                        cells(c.props['qcom,gpu-freq'])[0] // 1000000 for c in bins.children if 'qcom,gpu-freq' in c.props]
        elif node.name.startswith('qcom,gmu@') and compatible(node, 'gpu-gmu'):
            out['gmu'] = {'node': where, 'reg': cells(node.props.get('reg'))}
        elif node.name.startswith(('qcom,cpufreq-hw', 'cpufreq@')) and 'compatible' in node.props:
            out['cpufreq'] = {'node': where, 'compatible': string(node.props['compatible'])}
    for key in ('panels', 'touch', 'speakers', 'backlight', 'wifi', 'bluetooth'):
        if not out[key]:
            out['missing'].append(key)
    for key in ('gpu', 'gmu', 'cpufreq'):
        if out[key] is None:
            out['missing'].append(key)
    return out


# What hakios-pipa and the UniXNU-pipa port assume, each with where the assumption is written.
EXPECTED = [
    ('GPU chip id 0x06050002', lambda f: f['gpu'] and f['gpu']['chip_id'] == 0x06050002,
     'UniXNU-pipa package/A650Gmu.h A650_GMU_CHIP_ID; Linux a6xx_catalog.c'),
    ('GPU block at 0x3d00000', lambda f: f['gpu'] and f['gpu']['reg'][:1] == [0x3d00000], 'GpuPowerBoard.h'),
    ('GMU block at 0x3d6a000', lambda f: f['gmu'] and f['gmu']['reg'][:1] == [0x3d6a000], 'A650Gmu.h'),
    ('cpufreq block is EPSS', lambda f: f['cpufreq'] and 'epss' in f['cpufreq']['compatible'],
     'hakios-pipa soc.dtsi cpufreq { } (EPSS layout)'),
    ('touch: Novatek on SPI, attention on TLMM 39', lambda f: any(t['irq_tlmm'] == 39 for t in f['touch']),
     'UniXNU-pipa README (GPIO39)'),
    ('backlight: KTZ8866 at 0x11', lambda f: any(b['addr'] == 0x11 for b in f['backlight']),
     'Linux sm8250-xiaomi-pipa.dts i2c11 backlight@11'),
    ('panel 2 x 900 x 2880 (1800 x 2880)', lambda f: any(p['width_per_dsi'] == 900 and p['height'] == 2880
                                                       for p in f['panels']), 'docs/STATUS.md display'),
    ('panel lists 144 Hz', lambda f: any(144 in p['dfps_hz'] for p in f['panels']), 'docs/STATUS.md display'),
    ('four AW882xx amplifiers', lambda f: len([s for s in f['speakers'] if s['status'] in ('ok', 'okay')]) == 4,
     'docs/HARDWARE-FACTS.md'),
]


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    found = facts(Path(argv[1]).read_text(errors='replace'))
    if '--check' in argv:
        bad = 0
        for what, test, source in EXPECTED:
            ok = bool(test(found))
            bad += not ok
            print(f'{"PASS" if ok else "FAIL"}  {what}  ({source})')
        for missing in found['missing']:
            print(f'MISSING {missing}: not described by this tree')
        print('FACTS PASS' if not bad else f'FACTS FAIL ({bad})')
        return 1 if bad else 0
    print(json.dumps(found, indent=1, default=lambda v: hex(v) if isinstance(v, int) else str(v)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
