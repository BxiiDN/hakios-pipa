# Basis iPadOS 17: HakiOS vs UniXNU (sesi 2, 23 Nov 2026)

Keputusan pemilik: **UniXNU-pipa sebagai basis iPadOS 17**, HakiOS dipakai untuk komponen yang terbukti cocok.
Hasil audit: **UniXNU-pipa memenuhi syarat** untuk target iPadOS 17 asli. Target OS tidak diubah.

## Versi XNU (diverifikasi dari source, commit, dan konfigurasi build)

| Basis | XNU | Commit Apple (tag `^{}`) | Di mana tercatat | OS |
| --- | --- | --- | --- | --- |
| HakiOS `common` 62e09f8 | `xnu-12377.121.6` | `ac9718fb1af6…` | `components/upstream.dts` (`pins`) | Darwin 26/27 (iOS 26/27, file iPhone12,1) |
| HakiOS `legacy-hackios` | `xnu-8796.121.2` | `c54f35ca7679…` | `xnu/apply.sh` (`TAG=`) | iOS 16.5 |
| **UniXNU 8542980, profil `ipados-17.7.11-21H461`** | **`xnu-10063.141.1`** | **`d8b80295118e…`** | `profiles/os/ipados-17.7.11-21H461/profile.toml` (`xnu_revision`), `UniXNU-pipa/unixnu.lock` | **iPadOS 17.7.11, Darwin 23.6.0** |
| BxiiDN/ios-pipa 830ec1c | `xnu-8796.141.3` | — | skrip `tools/` | iOS 16 (`iPhone10,3`, 20H392) |

`scripts/fetch-unixnu.sh` memeriksa ulang setiap kali: profil UniXNU masih menunjuk `d8b80295…`, dan tag
`xnu-10063.141.1` di `apple-oss-distributions/xnu` memang commit itu. Tag lain yang ada: `xnu-10002.{1.13,41.9,61.3,81.5}`
(iPadOS 17.0–17.3) dan `xnu-10063.{101.15,121.3,141.1}`.

## Perbandingan

| Aspek | HakiOS (62e09f8) | UniXNU + UniXNU-pipa (EsaiJJ c4c1a3a) |
| --- | --- | --- |
| XNU | 12377 (Darwin 26/27) | 10063.141.1 (Darwin 23.6) = iPadOS 17 |
| iPadOS 17 | Tidak | Profil 17.7.11 (21H461), identitas `iPad7,1` / `j120ap`, idiom `pad` di ADT |
| Kernel ABI / IOKit | Driver in-kernel HakiOS (`drivers/board/`), stand-in IOKit | Kext Apple dari kernelcache IPSW di-prelink dengan XNU open-source (`kits/XnuPrelink`); ABI dicek per family (`IOGPUFamily`, `IOHIDFamily-2031.120.4`, `IOMobileGraphicsFamily`) |
| Device config | Paket `board.dts`/`soc.dtsi` (hakios-pipa) | `board.toml` (schema 2), `dts/pipa.dts`, `configs/pipa_defconfig`; diukur pada unit 8 GB / 256 GB |
| SMP | PSCI, generik | `ArmCpu` (8 core, IPI lewat SPI) |
| GPU | A660-family saja (`a660_*`) | `Adreno650` KMD + `A650Gmu.c` (urutan a650 Linux v6.6) + `AdrenoMetal` (Metal → Vulkan/Turnip) |
| Touch | Goodix/FocalTech/ST/Synaptics, **tidak ada Novatek** | `QcomGeniSpi` + Novatek NT36532 |
| Storage | `ufshc` (generik) | `ShengUfs` / `PipaUfs`, root APFS di jendela `userdata` |
| UEFI | Mu-Silicium (port dipindah keluar repo) / U-Boot | uefi-pipa (Mu-Silicium + DarwinBoot + menu UniXNU) |
| Bootloader | `fastboot boot` (RAM) | `fastboot boot` (RAM) |
| Userland | Darwin 26/27 | iPadOS 17.7.11 (IPSW iPad7,1), Data seed |
| Build kernel di Linux | Butuh iPhoneOS SDK Apple | Toolchain open-source (clang patched + cctools-port), tanpa Xcode |
| Lisensi | MIT / APSL 2.0 | BSD-2-Clause-Patent; driver MIT (Adreno650, AdrenoMetal), Apache-2.0 (ShengNovatekTouch), BSD-2 (ShengUfs) |

## Bukti yang dapat direproduksi (dijalankan di sesi ini)

- `check-pipa-board.py --ddr-gb 8 --storage-gb 256` UniXNU-pipa: **PASS** (2 bank, 7,93 GiB; userdata 242,4 GB).
- Host test driver pipa, gcc dan clang: Buttons, GpuPowerBoard, NativeBattery, TouchBoard (EsaiJJ), plus Gestures
  (xVanTuring): **18/18 PASS**. `A650GmuTests`: **NOT RUN** (butuh `kits/AdrenoFirmware` lewat `./unixnu fetch`;
  percobaan menjalankannya di sesi ini ditolak oleh pengaman sesi).
- Kernel, payload, firmware UniXNU: **BLOCKED** di sini (toolchain + input IPSW).

## Klaim yang belum terbukti untuk commit yang dipakai

- xVanTuring/UniXNU-pipa `cdb3d62` (README): iPadOS 17.7.11 sampai home screen, touch, tombol, GPU lewat GMU, Metal
  40–54 fps pada unit **16 GB**, 24 Okt 2026. Catatan UniXNU sendiri (`docs/devices/pipa.md`, revisi lebih lama)
  masih menulis berhenti di `Failed to mount root device`. Belum ada log yang bisa diperiksa di sini.
- EsaiJJ/UniXNU-pipa `c4c1a3a`: menulis sendiri bahwa build-nya **belum pernah di-boot** di Pad 6.
- BxiiDN/ios-pipa: README "Operational" bertentangan dengan `HANDOVER_TO_CLAUDE.md` di repo yang sama (touch tidak
  berfungsi, iOS 16, `iPhone10,3`). Satu commit. Bukan basis iPadOS 17.

## Keputusan

1. Basis kernel dan userland iPadOS 17: **UniXNU `8542980` + EsaiJJ/UniXNU-pipa `c4c1a3a`** (nilai unit 8 GB /
   256 GB), dengan **xVanTuring/UniXNU-pipa `cdb3d62`** sebagai referensi bukti hardware dan firmware uefi-pipa `1f6a152`.
2. Dari HakiOS dipertahankan: validator partisi, verifier boot image, tooling device tree (`devicetree.py`),
   paket board pipa (data yang dicek terhadap tree), dan loader/U-Boot sebagai jalur kedua untuk riset Darwin.
3. Kode HakiOS **tidak** dicampur ke kernel UniXNU: arsitektur driver berbeda (in-kernel board driver vs kext/prelink).

## Hambatan teknis yang ditemukan (bukan alasan untuk mengganti target)

- **Root iPadOS di UniXNU-pipa memakai jendela `userdata` Android** (`[userdata] first_lba/last_lba`,
  `native-ufs-root=1`, "flashing it erases Android's data"). Ini bertentangan dengan syarat dual boot. Desain
  perbaikannya ada di [DUAL-BOOT.md](DUAL-BOOT.md#penyimpanan-ipados-permanen); belum dijalankan.
- Firmware touch bergantung pada panel: maker `0x42` → `…_csot.bin` (EsaiJJ), maker `0x36` → `…_tm.bin`
  (xVanTuring). Unit pemilik harus dibaca (`scripts/extract-live-dt.sh`).
