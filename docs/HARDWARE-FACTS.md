# Fakta hardware pipa dari device tree publik

Sumber: tree live Android yang di-decompile di `xVanTuring/uefi-pipa` `1f6a152`
(`Resources/DTBs/pipa.dts`, model "Qualcomm Technologies, Inc. xiaomi pipa"), dibaca dengan
`tools/pipa_hw_facts.py` (parser `devicetree.py` HakiOS). Tree itu tidak disalin ke sini. Nilai dari unit
penulis tree itu, bukan unit pemilik: ulangi dengan `scripts/extract-live-dt.sh` di tablet sendiri.
Pembanding: Linux mainline `sm8250-xiaomi-pipa.dts` (`4843f687`).

| Bagian | Nilai | Node | Mainline Linux |
| --- | --- | --- | --- |
| Panel | 2 kandidat: `m82 36 02 0a` dan `m82 42 02 0b`, dual DSI D-PHY video mode, 900 × 2880 per DSI (1800 × 2880), dasar 120 Hz, DFPS 120/144/90/60/50/48/30 (porch VFP), bl max 0xfff | `/soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_m82_*` | tidak ada |
| Touch + stylus | `novatek,NVT-ts-spi` di `spi@990000` (QUP SE4), 9,6 MHz, attention TLMM 39, `novatek,pen-support` | `/soc/spi@990000/novatek@0` | tidak ada |
| Speaker (4) | AW882xx: `i2c@984000` 0x36 (ch1, reset 144, irq 129), 0x37 (ch2, reset 62, irq 67); `i2c@98c000` 0x34 (ch0, reset 6, irq 7), 0x35 (ch3, reset 78, irq 92) | `…/aw882xx_smartpa@3x` | tidak ada |
| Backlight | KTZ8866 `i2c@a8c000` 0x11, HWEN TLMM 139 | `…/ktz8866@11` | `i2c11` `backlight@11`, enable TLMM 139 |
| Wi-Fi | `qcom,cnss-qca6390` (PCIe) | `/soc/qcom,cnss-qca6390@b0000000` | `pcie0` aktif, tanpa node Wi-Fi |
| Bluetooth | `qca,qca6390` | `/vendor/bt_qca6390` | tidak ada |
| GPU | chip id 0x06050002, `0x3d00000` size 0x40000, highest-bank-bit 16; bin 0: 587 MHz, bin 1/2/4: 670 MHz, bin 3: 525 MHz | `/soc/qcom,kgsl-3d0@3d00000` | `gpu`, `gmu`, zap `a650_zap.mbn` |
| GMU | `0x3d6a000` size 0x30000, PDC `0xb290000`, `0xb490000` | `/soc/qcom,gmu@3d6a000` | ada |
| cpufreq | `qcom,cpufreq-hw-epss` | `/soc/qcom,cpufreq-hw` | `qcom,sm8250-cpufreq-epss` |

## Kesimpulan yang diambil

- **cpufreq = EPSS**, menurut tree downstream dan mainline. `Documentation/chipsets.md` HakiOS yang menaruh
  SM8250 di tata letak OSM perlu dikoreksi upstream; paket pipa memakai EPSS.
- **144 Hz** ada di daftar DFPS panel, tapi butuh driver DSI/DPU yang bisa mengganti porch. Tidak ada di HakiOS
  maupun UniXNU-pipa (keduanya memakai framebuffer firmware).
- **Backlight** bukan DCS: KTZ8866 lewat I2C. UniXNU-pipa juga menulis "no backlight driver yet".
- `boards.py new --dts` pada tree ini salah memilih tombol (blok PON `PMXPRAIRIE`) dan panel (`sw43404`, panel
  pertama di tree kona). Paket pipa tetap memakai nilai dari mainline untuk tombol. Pelajaran: tree downstream
  memuat banyak node referensi; selalu pilih dengan `--panel` dan cek `compare`.
- Driver audio, sensor (SLPI) dan Wi-Fi/BT yang cocok belum ada di HakiOS; di UniXNU-pipa Wi-Fi/BT "carried over,
  default-off", audio "planned".
