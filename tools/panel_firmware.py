#!/usr/bin/env python3
"""Which Novatek touch firmware a pipa unit needs, from the panel its bootloader reported -- and none when the panel is
not known. Never guesses: the two m82 panels need different images.

  panel_firmware.py "msm_drm.dsi_display0=qcom,mdss_dsi_m82_42_02_0b_dual_dphy_video:..."   prints the file name

Maker byte -> image, with where each pairing is recorded:
  0x42 (m82 42 02 0b) -> novatek_nt36532_m82_fw_csot.bin  (EsaiJJ/UniXNU-pipa proprietary-files.txt: the stock
                                                           boot.img's built-in table for display-maker 0x42)
  0x36 (m82 36 02 0a) -> novatek_nt36532_m82_fw_tm.bin    (xVanTuring/UniXNU-pipa README: maker 0x36 pairs with _tm)
"""
import re
import sys

BY_MAKER = {'42': 'novatek_nt36532_m82_fw_csot.bin', '36': 'novatek_nt36532_m82_fw_tm.bin'}


def firmware_for(panel):
    match = re.search(r'mdss_dsi_m82_([0-9a-f]{2})_[0-9a-f]{2}_[0-9a-f]{2}', panel or '', re.I)
    return BY_MAKER.get(match[1].lower()) if match else None


def main(argv):
    name = firmware_for(' '.join(argv[1:]))
    if not name:
        print('panel_firmware: panel not identified (or not an m82 panel): no touch firmware chosen', file=sys.stderr)
        return 1
    print(name)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
