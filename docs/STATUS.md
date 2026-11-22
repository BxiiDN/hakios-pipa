# Status verifikasi — hakios-pipa (22 Nov 2026)

Kolom: **SOURCE** (data/kode ada dan konsisten), **BUILD** (terbangun), **PREBOOT** (lulus pemeriksaan tanpa
tablet), **HARDWARE** (dilihat bekerja di Pad 6), **FULLY** (lengkap). Nilai: PASS, FAIL, PARTIAL, BLOCKED,
NOT TESTED. Tidak ada satu pun komponen yang HARDWARE PASS: tablet belum pernah dipakai.

## Build dan pengujian (`scripts/build.sh`, dijalankan dari nol)

| Pemeriksaan | Hasil |
| --- | --- |
| Validator partisi: 13 unit test (GPT 4096/512 byte, CRC, slot, overlap, alignment, aturan tulis) | PASS |
| Verifier boot image: self-test 5 kasus + output `pack.py` hakios-uefi | PASS |
| Device tree pipa dari Linux digabung (`tools/mkdts.sh`) | PASS |
| Paket pipa masuk ke kernel HakiOS (`tools/device.py add`) | PASS |
| `tools/boards.py check` ("2 boards, 2 SoCs: ok") | PASS |
| `tools/boards.py compare pipa` vs tree Linux | PASS (3 offset clock "not in the tree", memang dari driver clock) |
| kconfig-check, docs-check | PASS |
| Host test HakiOS (`workbench/run.sh`) | FAIL — 2 test upstream (`tools_test`, `maintainers_test`) gagal juga tanpa pipa (AUDIT.md) |
| Loader UEFI (`loader.efi`, PE32+ AArch64) | PASS |
| Loader reproducible (2 build, SHA-256 sama `7842bb9b…`) | PASS |
| U-Boot boot manager | BLOCKED di sesi ini (tidak ada aarch64 gcc/flex); skrip siap |
| Kernel XNU | BLOCKED — butuh iPhoneOS SDK Apple |
| Image user space Darwin / iPadOS | BLOCKED — butuh IPSW; lihat IPADOS17.md |
| QEMU | BLOCKED — butuh kernel; tidak ada QEMU di sesi ini |
| Preflight self-audit "tidak ada skrip yang menulis tablet" (diuji positif & negatif) | PASS |

## Hardware (30 komponen)

| # | Komponen | SOURCE | BUILD | PREBOOT | HARDWARE | Catatan |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | SoC SM8250 | PARTIAL | PASS | PASS | NOT TESTED | `soc.dtsi` baru; `io-base/io-size` belum (butuh `loader { }`) |
| 2 | CPU 8 core | PASS | PASS | PASS | NOT TESTED | PSCI smc, MPIDR shift 8, 4+3+1 |
| 3 | Frekuensi CPU | PARTIAL | PASS | PASS | NOT TESTED | Linux: EPSS; HakiOS: OSM. Uji level look-only dulu |
| 4 | GPU Adreno 650 | FAIL | — | — | NOT TESTED | Driver HakiOS hanya A660 (firmware `a660_*`, GMU chip id); `adreno { }` kosong |
| 5 | Akselerasi GPU | BLOCKED | — | — | NOT TESTED | Bergantung #4 |
| 6 | Metal | BLOCKED | — | — | NOT TESTED | Ada untuk A660 di HakiOS, belum untuk A650 |
| 7 | Display controller | PARTIAL | — | — | NOT TESTED | Framebuffer firmware saja (simple-framebuffer); tidak ada driver DPU/DSI |
| 8 | 2880 × 1800 | NOT TESTED | — | — | NOT TESTED | Mengikuti mode framebuffer dari ABL |
| 9 | 144 Hz | BLOCKED | — | — | NOT TESTED | Tanpa driver DSI/DPU mode tidak bisa diganti |
| 10 | Kecerahan | BLOCKED | — | — | NOT TESTED | Backlight pipa = KTZ8866 lewat I2C; HakiOS hanya DCS atau software (`soft` sekarang = fallback, bukan bukti) |
| 11 | Touchscreen | BLOCKED | — | — | NOT TESTED | IC tidak ada di tree mainline; butuh tree Android live. Driver HakiOS: Goodix, FocalTech, ST FTS, Synaptics |
| 12 | Stylus | BLOCKED | — | — | NOT TESTED | Bergantung #11 |
| 13 | Quad speaker | BLOCKED | — | — | NOT TESTED | Amp tidak di tree mainline; driver HakiOS hanya AW88261 |
| 14 | Mikrofon | BLOCKED | — | — | NOT TESTED | `mic-wcd938x` butuh `lpass { }` dan codec yang cocok |
| 15 | Wi-Fi | BLOCKED | — | — | NOT TESTED | Wi-Fi pipa lewat PCIe; HakiOS tidak punya driver PCIe (hanya WCN6750) |
| 16 | Bluetooth | NOT TESTED | — | — | NOT TESTED | `bluetooth-wcn-uart` mungkin cocok; butuh pin dari tree Android |
| 17 | UFS | PARTIAL | PASS | PASS | NOT TESTED | `ufs = <0x01d84000>` dari tree |
| 18 | RAM 8 GB | NOT TESTED | — | — | NOT TESTED | Dari peta memori UEFI/U-Boot |
| 19 | USB-C | BLOCKED | — | — | NOT TESTED | Tidak ada driver USB Darwin di HakiOS (hanya transport loader) |
| 20 | Baterai | BLOCKED | — | — | NOT TESTED | `battery-uefi` butuh protokol charger UEFI Qualcomm; U-Boot tidak punya |
| 21 | Charging | NOT TESTED | — | — | NOT TESTED | PMIC tetap mengisi sendiri; pelaporan bergantung #20 |
| 22 | Termal | PARTIAL | PASS | PASS | NOT TESTED | Alamat TSENS ada; `thermal { }` belum |
| 23 | Sleep/wake | NOT TESTED | — | — | NOT TESTED | Tidak ditemukan dukungan di HakiOS |
| 24 | Tombol Power | PASS | PASS | PASS | NOT TESTED | PM8150 PON (`buttons-pmic` siap di-list) |
| 25 | Volume Up | PASS | PASS | PASS | NOT TESTED | GPIO6 PM8150 |
| 26 | Volume Down | PASS | PASS | PASS | NOT TESTED | RESIN PM8150 |
| 27 | Sensor orientasi | BLOCKED | — | — | NOT TESTED | Sensor pipa di belakang SLPI; HakiOS hanya IMU I2C/SPI langsung |
| 28 | Boot chain | PARTIAL | PARTIAL | PASS | NOT TESTED | Loader PASS; profil U-Boot ditulis, belum dibangun |
| 29 | Layanan sistem iPadOS | BLOCKED | — | — | NOT TESTED | IPADOS17.md |
| 30 | SpringBoard tablet UI | BLOCKED | — | — | NOT TESTED | Butuh IPSW + DeviceTree iPad |

## Ringkasan per area

| Area | Status |
| --- | --- |
| GPU acceleration | FAIL di SOURCE: perlu profil A650 di `drivers/board/adreno.c` |
| iPadOS 17 userland | BLOCKED: versi XNU tidak cocok |
| Android | Tidak diubah; NOT TESTED setelah RAM boot |
| Dual Boot Manager | Profil U-Boot ditulis; BUILD BLOCKED di sesi ini; HARDWARE NOT TESTED |
| Isolasi partisi | PREBOOT PASS (aturan + unit test); belum dicek ke GPT tablet asli |
| Fallback Android | Desain: reset → ABL → Android; NOT TESTED |

## Langkah berikutnya (berurutan)

1. Pilih jalur iPadOS (IPADOS17.md) — keputusan pemilik.
2. Di WSL: `scripts/wsl-setup.sh --install`, `scripts/build.sh`, `scripts/build-uboot.sh`.
3. Dari Android rooted (read-only): `adb shell su -c 'cat /sys/firmware/fdt' > fdt.dtb`,
   `dtc -I dtb -O dts fdt.dtb > phone.dts`, lalu `tools/boards.py compare pipa --dts phone.dts` dan isi touch,
   panel, audio, Wi-Fi dari tree itu. Jangan commit `phone.dts`.
4. `scripts/dump-gpt.sh` → `scripts/preflight.sh --device --gpt DIR`.
5. `fastboot boot` boot manager; uji entri Android dulu.
6. `BENCH_BOARD=pipa`, defconfig `phone_first` (Documentation/porting.md langkah 3–4 HakiOS).
7. Profil A650 untuk driver GPU.
