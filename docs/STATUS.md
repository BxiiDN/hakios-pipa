# Status verifikasi — hakios-pipa (sesi 5, 23 Nov 2026)

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
| Paket EFI UniXNU (macos-26, UniXNU `62f203c`) | **PASS**: `UniXNU.efi` `a2ceaf758c2b5892…` (95 232 B), `UniXNUDxe.efi` `1c54e08805827dd8…` (14 336 B), `UniXNURamDiskDxe.efi` `7d7375701159ebc4…` (15 360 B) | run 45081127559 |
| Toolchain Linux UniXNU (ubuntu-24.04) | **PASS** + `--check`: clang 24.0.0git `58c46bae` `602430b2…`, ld64 `c4fa3cd1…`, migcom `a080a836…`, iig `64d7b95c…`, lzfse `73d68a52…` | run 45077836807 |
| Kernel referensi tahap A (bukan image boot) | **PASS (build)**: 18 archive, link final, prelink; `kernel.macho` `510999e4…` / `9a2eec5b…` (51 974 144 B, 22 611 ekspor; **tidak reproducible** antar-run, penyebab belum dicek) | run 45099835381, 45100879621 |
| Kernel board lengkap (tahap B) | **FAIL** di archive 20/21: firmware GMU/SQE/ZAP/touch perangkat tidak ada di CI. 19 archive PASS, termasuk ShengHidInput (ABI HID PASS terhadap kandidat tahap A), PMGR asli, Adreno 650, GPU addon, dan audit ABI display | run 45100879621, [BOOTSTRAP.md](BOOTSTRAP.md) |
| Link final + prelink board lengkap | **BLOCKED**: firmware perangkat, lalu kualifikasi storage asli (butuh observasi live QEMU/gdb yang tidak bisa dibuat dengan UniXNU 62f203c) | [BOOTSTRAP.md](BOOTSTRAP.md) |
| Firmware uefi-pipa (Mu-Silicium pipaPkg + UniXNU + DarwinBoot, CLANGPDB DEBUG) | **PASS (build)**: `SILICIUM_UEFI.fd` `bb3da32b80e2da57…` (3 145 728 B). Sesi 5 (run 45100879621): build PASS lagi, tetapi `6940dbff2d4d7832…`, **bukan bit-identik** dengan sesi 4 (input pin sama; penyebab belum dicek). `UniXNU.efi` `a2ceaf758c2b5892…` identik. Tidak dijalankan di tablet maupun QEMU | [run 45081127559](https://github.com/BxiiDN/hakios-pipa/actions/runs/45081127559) |
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
| Touch | PARTIAL (ABI ShengHidInput PASS offline) | NT36532 SPI; firmware dipilih **hanya** dari panel yang terbaca (`tools/panel_firmware.py`) |
| Stylus | NOT TESTED | — |
| Audio (4 × AW882xx, ADSP) | BLOCKED | Tidak ada jalur ADSP/I2C di port |
| Wi-Fi / Bluetooth / USB / PCIe | BLOCKED | Kode ada, default-off, belum diverifikasi di pipa |
| Sensor SLPI | BLOCKED | Tidak ada klien sensor |
| Baterai / charging | PARTIAL / NOT TESTED | `NativeBattery` host test PASS |
| Thermal / power | NOT TESTED | — |
| Tombol | PARTIAL | Host test PASS |
| Storage UFS | PARTIAL | Root dipindah ke `ipados`; menurut source tidak ada tulis ke `userdata` |
| U-Boot | PARTIAL | Kompilasi + reproducible PASS di CI; belum diuji di tablet |
| UEFI (uefi-pipa) | PARTIAL | Build PASS di CI; belum dijalankan di tablet |
| Android boot | NOT TESTED | Tidak diubah |
| iPadOS boot / userland / SpringBoard | BLOCKED | Kernel dan IPSW |
| Dual boot MODE A | PARTIAL | Menu Android-first dari builder asli, offline |
| Dual boot MODE B | Rancangan | [MODE-B.md](MODE-B.md) |
| Keselamatan `userdata` Android | PASS offline (source + config) | Belum dilihat di tablet |
