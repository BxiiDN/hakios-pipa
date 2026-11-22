# Status verifikasi — hakios-pipa (sesi 4, 23 Nov 2026)

Basis iPadOS 17: UniXNU `62f203c` (sesi 4, sebelumnya `8542980`; alasan di [XNU-BUILD.md](XNU-BUILD.md)) + EsaiJJ/UniXNU-pipa
`c4c1a3a` + patch hakios-pipa 0001–0003 (XNU `10063.141.1`).
Dua status terpisah, tidak pernah disamakan:

- **OFFLINE CHECKS** (`scripts/build.sh`, exit code): PASS — lihat `docs/build-summary-2026-11-23-s3.txt`.
- **READY FOR HARDWARE BOOT** (`scripts/readiness.sh`): **NO** — kernel, firmware, payload, boot image, root image dan
  anchor kunci owner belum ada; hardware preflight (identitas, GPT, root target, firmware, panel, backup, alat pemulihan) belum
  diverifikasi. **Tablet tidak boleh di-boot.**

## Pemeriksaan offline (dengan bukti)

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Unit + integration test Python (termasuk image consistency 5, userland 5, kedua ejaan boot-arg berbahaya) | PASS (56) | `python3 -m unittest discover -s tests` |
| Host test parser root UFS produksi (`RootLayout.h` + patch 0002) | PASS (14 cek); tanpa patch: tidak terkompilasi | `tests/c/root_layout_test.cpp` |
| Keselamatan storage menu dari builder UniXNU asli | PASS; board lama: 9 FAIL | `tools/storage_safety.py` |
| Defconfig U-Boot lewat Kconfig U-Boot (30 cek) | PASS | `tools/check_uboot_config.py` |
| HakiOS host test (pin + patch upstream, dengan pipa) | PASS | `workbench/run.sh` |
| UniXNU-pipa board check + 18 host test driver | PASS | `logs/unixnu-summary.txt` |
| Loader UEFI HakiOS reproducible | PASS | SHA-256 sama dua build |
| `git diff --check` (tree ter-commit + kerja) | PASS setelah commit sesi 3 | `scripts/build.sh` |
| Kompilasi U-Boot pipa (GitHub Actions, gcc 13.3, flex 2.6.4), dua build bersih | **PASS**: `u-boot.bin` `f6faf8e0…` (1 526 152 B), `u-boot` ELF `6bb971b1…`, DTB pipa `7c3faf93…`, image `hakios-pipa-bootmgr.img` `fa2c0951…` (776 192 B, header v1, page 2048); kedua build identik; tidak ada unresolved symbol; `.config`, env menu terkompilasi, DTB `xiaomi,pipa` dicek. **Menu belum dilihat di tablet** | [run 45073781629](https://github.com/BxiiDN/hakios-pipa/actions/runs/45073781629) |
| Paket EFI UniXNU (macos-26) | **PASS**: `UniXNU.efi` `66f43d77…` (95 232 B), `UniXNUDxe.efi` `c9537e2d…` (14 336 B), `UniXNURamDiskDxe.efi` `c9732e15…` (16 896 B) | run 45077836807 |
| Kernel XNU 10063 | **FAIL**: preflight, 64 patch XNU, compile bootstrap dan 7 archive PASS; berhenti di `ShengHidInput` (kandidat referensi prelink tidak ada) | [XNU-BUILD.md](XNU-BUILD.md) |
| Link final + prelink kernel | **BLOCKED** oleh baris di atas | — |
| Firmware uefi-pipa | **FAIL** (submodule brotli MdeModulePkg, sudah diperbaiki) lalu fetch 403 sementara (retry ditambahkan); hasil berikutnya belum ada | run 45077836807, 45080236671 |
| Payload, boot image, root image | **BLOCKED** (butuh kernel + firmware) | — |
| Validator userland iPadOS 17 (`tools/userland_check.py`) | Alat + test PASS; **NOT RUN** pada IPSW (tidak diunduh di sesi ini) | — |
| `A650GmuTests` | **NOT RUN** (butuh `kits/AdrenoFirmware`; menjalankannya ditolak pengaman sesi 2, tidak diulang) | — |
| QEMU | **BLOCKED** (tidak ada kernel, tidak ada qemu) | — |
| GitHub Actions | PASS (offline, upstream-tests sebagai root + init_test non-root yang dikenal, upstream-baseline) | [run 45073781629](https://github.com/BxiiDN/hakios-pipa/actions/runs/45073781629) |

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
| U-Boot | PARTIAL | Kompilasi + reproducible PASS di CI; belum diuji di tablet |
| UEFI (uefi-pipa) | FAIL → diperbaiki, menunggu CI | Paket EFI UniXNU PASS |
| Android boot | NOT TESTED | Tidak diubah |
| iPadOS boot / userland / SpringBoard | BLOCKED | Kernel dan IPSW |
| Dual boot MODE A | PARTIAL | Menu Android-first dari builder asli, offline |
| Dual boot MODE B | Rancangan | [MODE-B.md](MODE-B.md) |
| Keselamatan `userdata` Android | PASS offline (source + config) | Belum dilihat di tablet |
