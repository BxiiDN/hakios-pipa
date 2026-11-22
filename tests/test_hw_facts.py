"""tools/pipa_hw_facts.py on a small tree written here in the live-tree style (values from the published pipa tree
of xVanTuring/uefi-pipa 1f6a152, cut down). Needs HakiOS's tools/devicetree.py (HAKIOS_KERNEL); skipped without it."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
KERNEL = Path(os.environ.get('HAKIOS_KERNEL', ROOT.parent / 'hakios-work' / 'hakios-xnu-kernel'))

TREE = r'''/dts-v1/;
/ {
	model = "Qualcomm Technologies, Inc. xiaomi pipa";
	soc {
		qcom,cpufreq-hw { compatible = "qcom,cpufreq-hw-epss"; };
		qcom,kgsl-3d0@3d00000 {
			reg = <0x3d00000 0x40000 0x3d61000 0x800>;
			qcom,chipid = <0x6050002>;
			qcom,highest-bank-bit = <0x10>;
			qcom,gpu-pwrlevels-1 { qcom,speed-bin = <0x01>;
				qcom,gpu-pwrlevel@0 { qcom,gpu-freq = <0x27ef6380>; };
				qcom,gpu-pwrlevel@1 { qcom,gpu-freq = <0x00>; }; };
		};
		qcom,gmu@3d6a000 { compatible = "qcom,gpu-gmu"; reg = <0x3d6a000 0x30000 0xb290000 0x10000>; };
		spi@990000 { novatek@0 { compatible = "novatek,NVT-ts-spi"; reg = <0x00>; spi-max-frequency = <0x927c00>;
			novatek,irq-gpio = <0x65 0x27 0x2001>; novatek,pen-support; }; };
		i2c@984000 {
			aw882xx_smartpa@36 { compatible = "awinic,aw882xx_smartpa"; reg = <0x36>; reset-gpio = <0x65 0x90 0x00>;
				irq-gpio = <0x65 0x81 0x2008>; sound-channel = <0x01>; status = "ok"; };
			aw882xx_smartpa@37 { compatible = "awinic,aw882xx_smartpa"; reg = <0x37>; sound-channel = <0x02>; status = "ok"; }; };
		i2c@98c000 {
			aw882xx_smartpa@34 { compatible = "awinic,aw882xx_smartpa"; reg = <0x34>; sound-channel = <0x00>; status = "ok"; };
			aw882xx_smartpa@35 { compatible = "awinic,aw882xx_smartpa"; reg = <0x35>; sound-channel = <0x03>; status = "ok"; }; };
		i2c@a8c000 { ktz8866@11 { compatible = "ktz,ktz8866"; reg = <0x11>; }; };
		qcom,cnss-qca6390@b0000000 { compatible = "qcom,cnss-qca6390"; };
		qcom,mdss_mdp@ae00000 {
			qcom,mdss_dsi_m82_42_02_0b_dual_dphy_video {
				qcom,mdss-dsi-panel-name = "xiaomi m82 42 02 0b video mode dual dsi dphy panel";
				qcom,mdss-dsi-panel-type = "dsi_video_mode";
				qcom,dsi-supported-dfps-list = <0x78 0x90 0x5a 0x3c>;
				qcom,mdss-dsi-bl-max-level = <0xfff>;
				qcom,mdss-dsi-display-timings { timing@0 { qcom,mdss-dsi-panel-framerate = <0x78>;
					qcom,mdss-dsi-panel-width = <0x384>; qcom,mdss-dsi-panel-height = <0xb40>; }; };
			};
			qcom,mdss_dsi_sw43404_amoled_wqhd_cmd { qcom,mdss-dsi-panel-name = "sw43404 amoled cmd mode dsi boe panel"; };
		};
	};
	vendor { bt_qca6390 { compatible = "qca,qca6390"; }; };
};
'''


@unittest.skipUnless((KERNEL / 'tools' / 'devicetree.py').is_file(), 'HakiOS tools/devicetree.py not found')
class HwFacts(unittest.TestCase):
    def setUp(self):
        os.environ['HAKIOS_KERNEL'] = str(KERNEL)
        import pipa_hw_facts
        self.mod = pipa_hw_facts
        self.f = pipa_hw_facts.facts(TREE)

    def test_panel_is_m82_only_with_144hz(self):
        self.assertEqual(len(self.f['panels']), 1)  # the reference panels of the kona tree are skipped
        panel = self.f['panels'][0]
        self.assertEqual((panel['width_per_dsi'], panel['height'], panel['base_hz']), (900, 2880, 120))
        self.assertIn(144, panel['dfps_hz'])

    def test_touch_speakers_backlight(self):
        self.assertEqual(self.f['touch'][0]['irq_tlmm'], 39)
        self.assertTrue(self.f['touch'][0]['pen'])
        self.assertEqual(self.f['touch'][0]['spi_hz'], 9600000)
        self.assertEqual(sorted(s['channel'] for s in self.f['speakers']), [0, 1, 2, 3])
        self.assertEqual(self.f['backlight'][0]['addr'], 0x11)

    def test_gpu_and_cpufreq(self):
        self.assertEqual(self.f['gpu']['chip_id'], 0x06050002)
        self.assertEqual(self.f['gpu']['bins_mhz'][1], [670, 0])
        self.assertEqual(self.f['gmu']['reg'][0], 0x3d6a000)
        self.assertIn('epss', self.f['cpufreq']['compatible'])

    def test_check_passes_and_a_missing_part_is_reported(self):
        for what, test, _ in self.mod.EXPECTED:
            self.assertTrue(test(self.f), what)
        bare = self.mod.facts('/dts-v1/;\n/ { model = "x"; };\n')
        self.assertIn('touch', bare['missing'])
        self.assertIn('gpu', bare['missing'])


if __name__ == '__main__':
    unittest.main()
