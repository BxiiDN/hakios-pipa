# Status verifikasi — hakios-pipa (sesi 8, 23 Nov 2026)

Basis iPadOS 17: UniXNU `62f203c` (sesi 4, sebelumnya `8542980`; alasan di [XNU-BUILD.md](XNU-BUILD.md)) + EsaiJJ/UniXNU-pipa
`c4c1a3a` + patch hakios-pipa 0001–0003 (XNU `10063.141.1`).
Dua status terpisah, tidak pernah disamakan:

- **OFFLINE CHECKS** (`scripts/build.sh`, exit code): PASS — lihat `docs/build-summary-2026-11-23-s3.txt`.
- **READY FOR HARDWARE BOOT** (`scripts/readiness.sh`): **NO** — kernel, firmware, payload, boot image, root image dan
  anchor kunci owner belum ada; hardware preflight (identitas, GPT, root target, firmware, panel, backup, alat pemulihan) belum
  diverifikasi. **Tablet tidak boleh di-boot.**

## Sesi 8 (lokal WSL2; push belum bisa: tidak ada kredensial GitHub di WSL maupun Windows)

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Lima simbol backlight | **SELESAI dengan driver nyata** (patch port 0007): commit port `421c34b` menghapus driver backlight TB-J716F (AMOLED, skala piksel) tetapi menyisakan referensi `weak_import`; ld Apple mengikatnya ke 0, ld64 cctools di Linux menolak. Kini didefinisikan oleh layanan AppleARMBacklight untuk KTZ8866 lewat master GENI I2C11 (`PipaBacklightService.cpp`, `PipaBacklightAttach.cpp`, `BacklightProbe.c`; kecerahan terlihat berubah di tablet pemilik pada 18 Nov, mati kecuali `sheng-backlight=1`), plus hook swap-cancel slot 345 di NativeLegacyDisplay. `native_backlight_scale` = 256: panel pipa LCD, piksel tetap skala penuh | `kernel-exports.txt` |
| Duplicate symbol storage | **SELESAI** (patch port 0008): NativeUfs dikompilasi `NATIVE_VERIFIED_BLOCK=1` (setiap baca root diperiksa kebijakan owner; jalur kueri root dengan tiga UUID hardcoded tidak di-link), dan ShengUfs tidak mengompilasi `IOBlockStorageDevice` kedua bila audit storage ada | `kernel.log`: 0 duplicate |
| `native_verified_root_probe` | **Kode nyata** (patch port 0010), menggantikan `ret` dari patch 0006: dengan `offline-owner-root-check=1`, kedua kebijakan tertanam harus lolos RSA-3072 lewat `vr_xnu_crypto`, dan tanda tangan, header, kunci serta panjang yang dimanipulasi harus ditolak. Host test dengan kebijakan asli + OpenSSL: PASS (2/2, semua manipulasi ditolak); anchor lain: FAIL | `tests/pipa-verified-root-selftest-host.c` (port) |
| Final link + prelink tahap B | **PASS**: 0 undefined, 0 duplicate. `kernel.macho` `81fa31702fee3cb4f0a2ccf1893fa9c2fe5157984ab670e8b679bda8192ddfd6` (53 899 264 B, Mach-O 64-bit arm64 executable `NOUNDEFS|PIE`, UUID `9fcf0f3e…`, 26 409 ekspor, 18 segmen). Tahap B tetap dilaporkan FAIL oleh skrip karena GPU addon SKIP | `repro-v3-run2/` |
| Reproducibility | **PASS**: dua clean build (direktori output baru, path sama) identik: tahap B `81fa3170…`, tahap A `1b094fd6…`. Build di path berbeda memang berbeda: string `__FILE__` berisi path build (1 294 kemunculan); kode dan data identik | `repro-v3-run{1,2}/sha256.txt` |
| ShengHidInput recheck (kernel final) | **PASS**: teks asli, slot, ukuran instance, slot milik driver, 52 simbol HID asli tidak bergeser | `repro-v3-run2/recheck.log` |
| Storage ABI pada kernel final | **TRANSFER PASS 12/12**; anchor dan kedua kebijakan dalam kernel = file owner byte-per-byte | `storage-transfer-final.json` |
| Root iPadOS | `native-ufs-root-part=ipados`; `tools/storage_safety.py`: STORAGE OFFLINE PASS (default Android, timeout 10 s, entri recovery) | — |
| Turnip iOS / bridge / GPU addon | **NOT BUILT** (butuh Xcode). Rute ABI diperbaiki dan job CI `macos-gpu` ditambahkan, keduanya belum dijalankan. Detail: [ADRENO650.md](ADRENO650.md) | — |
| Host test port | Buttons, GpuPowerBoard, NativeBattery, TouchBoard: PASS (gcc + clang). `A650GmuTests`: build aarch64 PASS, NOT RUN (tanpa `qemu-user`) | `evidence/host-tests/` |
| Akselerasi GPU di tablet | **NOT TESTED** | — |

## Sesi 7 (lokal, Windows 11 + WSL2 Ubuntu 26.04, tablet via adb Windows)

Semua langkah di bawah dijalankan di PC pemilik, bukan CI. Tidak ada flash, repartisi, atau boot di tablet. Firmware,
IPSW, kernel, kebijakan root dan rekaman QEMU disimpan di `~/.hakios-private` / `~/hakios/evidence`, tidak di Git.

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Deteksi perangkat (read-only) | `pipa` / `23043RP34C`, SM8250, MemTotal 7 786 840 kB, HyperOS `OS4.0.8.0.XPZCNXM` (Android 17, slot `_b`, kernel kustom). Tanpa root. Panel: ABL melaporkan `mdss_dsi_m82_42_02_0b` (CSOT) (rekaman cmdline ABL unit ini, 17 Nov) | `adb getprop`, `dumpsys` |
| Firmware `adb` | `/vendor` tidak terbaca (SELinux, tanpa root): GPU tidak ditarik | `collect-firmware.sh adb` |
| Firmware `rom` + `vendor` (OTA resmi `OS2.0.16.0.UMZMIXM`, md5 `c378f929…` cocok) | **FIRMWARE PASS**: GMU `df79fa84…`, SQE `b4c27420…` (= pin port), ZAP `.elf` `dd930441…` (pin ROM resmi; pin port berasal dari port ColorOS), touch CSOT `ba7d0eb9…` (= pin port). ZAP tidak di-rename: segmen `.b00–.b02` identik, ditandatangani Xiaomi Root CA | `manifests/pipa-official-rom-OS2.0.16.0.UMZMIXM.txt` |
| Kernel tahap A (lokal, toolchain Linux UniXNU, kunci owner `e8ae7ddf…`) | **PASS**: `kernel.macho` `7037ae25…` (51 097 600 B, UUID `cf5a56ba…`, 22 611 ekspor), provenance PASS. Build kedua di tree yang sama: hash identik (inkremental, bukan clean-room) | `two-stage/stage-a-provenance.json` |
| Storage ABI LIVE (QEMU 10.2.1 TCG lokal, AAVMF no-secboot) | **PASS**: kernel board QEMU `b1a7c90f…`, `gdb-stop.json` `6620cee8…`, `interface-audit.json` `5105d252…`: 190 slot, 176 binding, ukuran live 0x90/0x88, native 4K. Butuh patch unixnu 0003/0004 dan unixnu-qemu 0004 (toolchain/host, bukan ABI) | `qemu-storage/` |
| Transfer rekaman storage ke kernel pipa (`tools/storage_abi_transfer.py`) | **PASS 12/12** pada kernel tahap A: kernelcache pin, kode IOStorageFamily tidak berubah, vtable/metaclass/konstruktor/destruktor di alamat yang sama, 14 target asli + 176 ekspor native identik, IOService DWARF 0x88 | `storage-transfer-stage-a.json` |
| Tahap B, archive | Storage binding RamBlock + VirtioMmioBlock **PASS**; VerifiedRoot (anchor + 2 kebijakan owner + kit) **PASS**; Adreno 650 **PASS** (31 objek); GOP legacy display (dengan firmware GMU/SQE/ZAP/touch) **PASS**; GPU addon **SKIP = FAIL** (Turnip iOS tidak ada); `check-pipa.py` jalan tetapi melewati cek firmware statisnya ("no uefi-pipa checkout") | `s7-stage-b.log` |
| Link final | **FAIL**: 5 simbol `weak_import` backlight (`native_backlight_scale/stats`, `sheng_backlight_probe{,_result,_stage}`) tidak terdefinisi. ld64 cctools di Linux tidak bisa me-link referensi weak tak terdefinisi pada link statis (diuji: tanpa `-U` "symbol not found", dengan `-U` "branch out of range" ke 0). Tidak ditambal: definisi pengganti mengubah output diagnostik | `kernel.log` |
| Prelink final, recheck HID, uji GPU addon, konsistensi kernel final | **NOT RUN** (butuh link final) | — |
| Userland iPadOS 17.7.11 (IPSW iPad7,1 `21H461`, DMG OS `3f99b859…` + SystemOS `b4908cde…` dibaca in-place lewat 7z) | **USERLAND COMPLETE (bukan uji boot)**: launchd, backboardd, SpringBoard, mediaserverd, configd, wifid, Settings arm64 dan semua library ada; CoreGraphics, QuartzCore, Metal, IOSurface, IOKit, UIKit adalah image di dyld shared cache (54 file); 4 launchd job ada | `userland/userland-21H461.txt` |
| Turnip iOS | **NOT BUILT**: butuh Xcode iphoneos SDK (tidak ada di WSL), dan push ke CI tidak tersedia dari PC ini. Analisis: `u_format_gen.h` memakai `RG88/GR88` di fungsi inline sendiri (17 tempat), jadi error = kedua cabang `UTIL_ARCH_*_ENDIAN` di header itu tidak terambil; `Dl_info` = `HAVE_DLADDR` terdefinisi tanpa `HAVE_DLFCN_H`. Keduanya bergantung pada deteksi header meson dengan SDK Xcode 26.6; build sukses sebelumnya (pipa-gpu-addon, Mesa pin yang sama) memakai `macos-15-intel`. CI kini mengirim diagnostik (`turnip-diagnostics`) sebagai anotasi publik | `scripts/kernel-two-stage.sh` |
| Akselerasi GPU | **NOT TESTED** | — |

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
| Kernel referensi tahap A (bukan image boot) | **PASS (build), reproducible**: `d0ba5de5…` (51 974 144 B, UUID `c700fb3e…`) di tiga run dengan `KERNEL_BUILD_DATE` dipatok; beda di sesi 5 = tanggal build XNU | run 45105668358, 45106011890, 45107232121 |
| Kernel board lengkap (tahap B) | **FAIL** di archive 20/21: firmware GMU/SQE/ZAP/touch perangkat tidak ada di CI. 19 archive PASS, termasuk ShengHidInput (ABI HID PASS terhadap kandidat tahap A), PMGR asli, Adreno 650, GPU addon, dan audit ABI display | run 45100879621, [BOOTSTRAP.md](BOOTSTRAP.md) |
| Link final + prelink board lengkap | **BLOCKED**: firmware perangkat (archive 20). Kualifikasi storage sudah tersedia dari QEMU (`interface-audit.json` `62f14fa0…`), tetapi belum dipasang ke board pipa | [BOOTSTRAP.md](BOOTSTRAP.md) |
| Firmware uefi-pipa | **PASS (build), reproducible**: `SILICIUM_UEFI.fd` `8e989103…` di enam build bersih dari tiga run, dengan `PYTHONHASHSEED=0`. Sebelumnya hanya `PcdDxe.efi` yang berbeda antar-build (urutan PCD database di BaseTools ikut seed hash Python). `UniXNU.efi` `a2ceaf75…` tetap. Tidak dijalankan di tablet maupun QEMU | run 45104257856, 45105536415, 45105668358, 45106011890 |
| Payload, boot image, root image | **BLOCKED** (butuh kernel + firmware) | — |
| Validator userland iPadOS 17 (`tools/userland_check.py`) | Alat + test PASS; **NOT RUN** pada IPSW (tidak diunduh di sesi ini) | — |
| `A650GmuTests` | **NOT RUN** (butuh `kits/AdrenoFirmware`; menjalankannya ditolak pengaman sesi 2, tidak diulang) | — |
| QEMU | **BLOCKED** (tidak ada kernel, tidak ada qemu) | — |
| GitHub Actions | PASS (offline, upstream-tests sebagai root + init_test non-root yang dikenal, upstream-baseline) | [run 45073781629](https://github.com/BxiiDN/hakios-pipa/actions/runs/45073781629) |

## Matriks kompatibilitas (tidak ada yang diuji di Pad 6)

| Komponen | Status | Catatan |
| --- | --- | --- |
| SoC, CPU | PARTIAL | Data board; host test; NOT TESTED |
| GPU Adreno 650 | PARTIAL (archive kernel PASS lokal sesi 7; Turnip iOS belum dibangun; addon SKIP; [ADRENO650.md](ADRENO650.md)) | KMD + GMU di UniXNU-pipa; `A650GmuTests` NOT RUN |
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
| Storage UFS | PARTIAL (ABI storage asli: STATIC VERIFIED dan LIVE VERIFIED di QEMU; hardware NOT TESTED) | Root dipindah ke `ipados`; menurut source tidak ada tulis ke `userdata` |
| U-Boot | PARTIAL | Kompilasi + reproducible PASS di CI; belum diuji di tablet |
| UEFI (uefi-pipa) | PARTIAL | Build PASS di CI; belum dijalankan di tablet |
| Android boot | NOT TESTED | Tidak diubah |
| iPadOS boot / userland / SpringBoard | BLOCKED | Kernel dan IPSW |
| Dual boot MODE A | PARTIAL | Menu Android-first dari builder asli, offline |
| Dual boot MODE B | Rancangan | [MODE-B.md](MODE-B.md) |
| Keselamatan `userdata` Android | PASS offline (source + config) | Belum dilihat di tablet |
