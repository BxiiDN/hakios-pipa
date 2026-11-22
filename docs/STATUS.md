# Status verifikasi — hakios-pipa (sesi 3, 23 Nov 2026)

Basis iPadOS 17: UniXNU `8542980` + EsaiJJ/UniXNU-pipa `c4c1a3a` + patch hakios-pipa (XNU `10063.141.1`).
Dua status terpisah, tidak pernah disamakan:

- **OFFLINE CHECKS** (`scripts/build.sh`, exit code): PASS — lihat `docs/build-summary-2026-11-23-s3.txt`.
- **READY FOR HARDWARE BOOT** (`scripts/readiness.sh`): **NO** — kernel, firmware, payload, boot image dan root image
  belum ada; hardware preflight (identitas, GPT, root target, firmware, panel, backup, alat pemulihan) belum
  diverifikasi. **Tablet tidak boleh di-boot.**

## Pemeriksaan offline (dengan bukti)

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Unit + integration test Python (validator partisi 13, env U-Boot 10, menu UniXNU 5, fakta hardware 4, builder UniXNU asli 6, image + FAT 5, firmware panel 2) | PASS (45) | `python3 -m unittest discover -s tests` |
| Host test parser root UFS produksi (`RootLayout.h` + patch 0002) | PASS (14 cek); tanpa patch: tidak terkompilasi | `tests/c/root_layout_test.cpp` |
| Keselamatan storage menu dari builder UniXNU asli | PASS; board lama: 9 FAIL | `tools/storage_safety.py` |
| Defconfig U-Boot lewat Kconfig U-Boot (30 cek) | PASS | `tools/check_uboot_config.py` |
| HakiOS host test (pin + patch upstream, dengan pipa) | PASS | `workbench/run.sh` |
| UniXNU-pipa board check + 18 host test driver | PASS | `logs/unixnu-summary.txt` |
| Loader UEFI HakiOS reproducible | PASS | SHA-256 sama dua build |
| `git diff --check` (tree ter-commit + kerja) | PASS setelah commit sesi 3 | `scripts/build.sh` |
| Kompilasi U-Boot | **BLOCKED** (tidak ada `aarch64-linux-gnu-gcc`/`flex`; instalasi dan build tool dari source ditolak lingkungan sesi). Skrip siap: dua build bersih, simbol, `.config`, env terkompilasi, DTB | `scripts/build-uboot.sh` |
| Kernel XNU 10063, firmware uefi-pipa, payload, boot image | **BLOCKED** | [XNU-BUILD.md](XNU-BUILD.md) |
| `A650GmuTests` | **NOT RUN** (butuh `kits/AdrenoFirmware`; menjalankannya ditolak pengaman sesi 2, tidak diulang) | — |
| QEMU | **BLOCKED** (tidak ada kernel, tidak ada qemu) | — |
| GitHub Actions | ditulis ulang tanpa `|| true` / `continue-on-error`; **belum pernah jalan** (repo belum di GitHub) | `.github/workflows/` |

## Matriks kompatibilitas (tidak ada yang diuji di Pad 6)

| Komponen | Status | Catatan |
| --- | --- | --- |
| SoC, CPU | PARTIAL | Data board; host test; NOT TESTED |
| GPU Adreno 650 | PARTIAL | KMD + GMU di UniXNU-pipa; `A650GmuTests` NOT RUN |
| Akselerasi GPU | NOT TESTED | — |
| Display | PARTIAL | Framebuffer firmware; 144 Hz BLOCKED (tidak ada driver DSI/DPU) |
| Kecerahan | BLOCKED | KTZ8866 di I2C11: tidak ada driver GENI I2C maupun KTZ8866 di port |
| Touch | PARTIAL | NT36532 SPI; firmware dipilih **hanya** dari panel yang terbaca (`tools/panel_firmware.py`) |
| Stylus | NOT TESTED | — |
| Audio (4 × AW882xx, ADSP) | BLOCKED | Tidak ada jalur ADSP/I2C di port |
| Wi-Fi / Bluetooth / USB / PCIe | BLOCKED | Kode ada, default-off, belum diverifikasi di pipa |
| Sensor SLPI | BLOCKED | Tidak ada klien sensor |
| Baterai / charging | PARTIAL / NOT TESTED | `NativeBattery` host test PASS |
| Thermal / power | NOT TESTED | — |
| Tombol | PARTIAL | Host test PASS |
| Storage UFS | PARTIAL | Root dipindah ke `ipados`; menurut source tidak ada tulis ke `userdata` |
| U-Boot | PARTIAL | Konfigurasi PASS; kompilasi BLOCKED |
| UEFI (uefi-pipa) | BLOCKED | Build belum jalan |
| Android boot | NOT TESTED | Tidak diubah |
| iPadOS boot / userland / SpringBoard | BLOCKED | Kernel dan IPSW |
| Dual boot MODE A | PARTIAL | Menu Android-first dari builder asli, offline |
| Dual boot MODE B | Rancangan | [MODE-B.md](MODE-B.md) |
| Keselamatan `userdata` Android | PASS offline (source + config) | Belum dilihat di tablet |
