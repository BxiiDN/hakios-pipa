# Status verifikasi — hakios-pipa (sesi 2, 23 Nov 2026)

Basis iPadOS 17: UniXNU `8542980` + EsaiJJ/UniXNU-pipa `c4c1a3a` (XNU `10063.141.1`), keputusan dan bukti di
[BASE-DECISION.md](BASE-DECISION.md). **Tidak ada satu pun komponen yang diuji di Pad 6.** Kolom HARDWARE semuanya
NOT TESTED sampai ada log dari unit pemilik.

## Build dan pengujian (`scripts/build.sh` dari pohon kerja bersih, exit 0)

| Pemeriksaan | Hasil |
| --- | --- |
| Unit test (32): validator partisi 13, env boot manager U-Boot 10, menu UniXNU 5, fakta hardware 4 | PASS |
| Self-test manifest firmware (4), verifier boot image (5) | PASS |
| Device tree pipa digabung; paket masuk kernel; `boards.py check`; `compare` vs Linux | PASS |
| kconfig-check, docs-check HakiOS | PASS |
| Host test HakiOS `workbench/run.sh` (pin 62e09f8 + `patches/upstream/0001`, dengan pipa) | PASS (baseline murni: FAIL, [UPSTREAM-TESTS.md](UPSTREAM-TESTS.md)) |
| Loader UEFI, dua build identik (SHA-256 sama) | PASS |
| Defconfig U-Boot diselesaikan oleh Kconfig U-Boot v2026.07 (30 pemeriksaan: SM8250, tombol PMIC, remap, bootmenu, HakiOS, safety switch off, tree pipa) | PASS |
| UniXNU pin + profil iPadOS 17.7.11 = `xnu-10063.141.1` (`d8b80295…`, dicek ke Apple) | PASS |
| UniXNU-pipa `check-pipa-board.py` 8 GB/256 GB (dengan patch dual boot) | PASS |
| Host test driver pipa UniXNU (gcc+clang): 18 | PASS; `A650GmuTests` NOT RUN |
| Fakta hardware tree publik pipa (9 pemeriksaan) | PASS |
| Konstanta Adreno 650 Linux vs port vs HakiOS | GAP: driver HakiOS hanya A660 |
| Self-audit "tidak ada skrip yang menulis tablet" | PASS |
| Kompilasi U-Boot | BLOCKED: tidak ada `aarch64-linux-gnu-gcc` dan `flex` di sesi ini (install paket diblokir oleh lingkungan) |
| Kernel XNU 10063 (UniXNU) | BLOCKED: toolchain Linux UniXNU + input IPSW iPad7,1 17.7.11 |
| Kernel XNU 12377 (HakiOS) | BLOCKED: iPhoneOS SDK; bukan basis iPadOS 17 |
| Firmware uefi-pipa, payload, boot image UniXNU | BLOCKED |
| Simbol kernel, prelink, QEMU | BLOCKED: tidak ada kernel; tidak ada `qemu-system-aarch64` |
| GitHub Actions | workflow ditulis, belum pernah jalan (repo belum di GitHub) |

## Matriks kompatibilitas

| Komponen | Status | Dasar |
| --- | --- | --- |
| SoC SM8250 | PARTIAL | Data board di kedua basis; UniXNU-pipa board check PASS |
| CPU (8 core, SMP) | PARTIAL | `ArmCpu` (UniXNU), PSCI smc; NOT TESTED |
| GPU Adreno 650 | PARTIAL | Driver A650 + GMU di UniXNU-pipa, host test power-board PASS; HakiOS: GAP |
| Akselerasi GPU / Metal | NOT TESTED | Klaim referensi (unit 16 GB); [ADRENO650.md](ADRENO650.md) |
| Display | PARTIAL | Framebuffer firmware 1800 × 2880; 144 Hz ada di DFPS panel tapi tanpa driver DSI: BLOCKED |
| Kecerahan | BLOCKED | KTZ8866 I2C, tidak ada driver di kedua basis |
| Touchscreen | PARTIAL | NT36532 SPI (UniXNU-pipa), host test TouchBoard PASS; firmware tergantung panel |
| Stylus | NOT TESTED | `novatek,pen-support` di tree; belum ada jalur Apple Pencil |
| Audio (4 × AW882xx, mikrofon) | BLOCKED | Planned di UniXNU-pipa; tidak ada driver |
| Wi-Fi QCA6390 | BLOCKED | Kode ada, default-off, belum diverifikasi |
| Bluetooth | BLOCKED | Sama |
| Storage UFS | PARTIAL | `ShengUfs`; root di `userdata` bertentangan dengan dual boot ([DUAL-BOOT.md](DUAL-BOOT.md)) |
| Memori 8 GB | PARTIAL | Bank diukur pada unit 8 GB (EsaiJJ), board check PASS |
| USB | NOT TESTED | DWC3 CDC-ACM default-off |
| Baterai | PARTIAL | `NativeBattery` PM8150B, host test PASS |
| Charging | NOT TESTED | PMIC mengisi sendiri; pelaporan bergantung baterai |
| Power management | NOT TESTED | `pipa-cpufreq=1`, PMGR bridge |
| Thermal | NOT TESTED | TSENS di paket HakiOS; tidak ada di UniXNU-pipa |
| Tombol | PARTIAL | Power/Vol-/Vol+ (PM8150), host test Buttons PASS |
| Boot chain | PARTIAL | Loader PASS; U-Boot dicek Kconfig; uefi-pipa BLOCKED |
| UEFI (uefi-pipa) | BLOCKED | Build belum dijalankan |
| U-Boot | PARTIAL | Konfigurasi PASS; kompilasi BLOCKED |
| Android boot | NOT TESTED | Tidak diubah; fallback = reset |
| iPadOS boot | NOT TESTED | Kernel belum dibangun |
| Dual Boot Manager | PARTIAL | Dua menu Android-first, timeout 10 s, diuji offline (15 test + Kconfig) |
| iPadOS userland | BLOCKED | Butuh IPSW pemilik |
| SpringBoard tablet UI | NOT TESTED | Identitas `pad`, scale 2 (900 × 1440 pt) di konfigurasi |

## Langkah berikutnya

[CLAUDE-CODE.md](CLAUDE-CODE.md): toolchain di WSL → build U-Boot dan kernel UniXNU → tree live + firmware +
backup (read-only) → `fastboot boot` → uji menu Android-first → log.
