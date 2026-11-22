"""tools/panel_firmware.py: the touch firmware follows the panel the bootloader reported, and nothing is chosen when
the panel is unknown."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from panel_firmware import firmware_for  # noqa: E402


class PanelFirmware(unittest.TestCase):
    def test_both_makers(self):
        self.assertEqual(firmware_for('msm_drm.dsi_display0=qcom,mdss_dsi_m82_42_02_0b_dual_dphy_video:config0'),
                         'novatek_nt36532_m82_fw_csot.bin')
        self.assertEqual(firmware_for('msm_drm.dsi_display0=qcom,mdss_dsi_m82_36_02_0a_dual_dphy_video:'),
                         'novatek_nt36532_m82_fw_tm.bin')

    def test_unknown_chooses_nothing(self):
        for panel in ('', 'unknown', 'msm_drm.dsi_display0=qcom,mdss_dsi_m82_99_02_0a_dual_dphy_video',
                      'msm_drm.dsi_display0=qcom,mdss_dsi_sw43404_amoled_wqhd_cmd'):
            self.assertIsNone(firmware_for(panel), panel)


if __name__ == '__main__':
    unittest.main()
