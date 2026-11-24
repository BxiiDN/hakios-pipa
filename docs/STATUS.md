# Status verifikasi — hakios-pipa (sesi 13, 24 Nov 2026)

Basis iPadOS 17: UniXNU `62f203c` (sesi 4, sebelumnya `8542980`; alasan di [XNU-BUILD.md](XNU-BUILD.md)) + EsaiJJ/UniXNU-pipa
`c4c1a3a` + patch hakios-pipa 0001–0003 (XNU `10063.141.1`).
Dua status terpisah, tidak pernah disamakan:

- **OFFLINE CHECKS** (`scripts/build.sh`, exit code): PASS — lihat `docs/build-summary-2026-11-23-s3.txt`.
- **READY FOR HARDWARE BOOT** (`scripts/readiness.sh`): **NO** — sesi 11–12: hanya image root partisi `ipados` yang belum ada
  (kernel, firmware, payload, boot image, anchor owner ada dan konsisten); hardware preflight (identitas, GPT, root target, firmware, panel, backup, alat pemulihan) belum
  diverifikasi. **Tablet tidak boleh di-boot.**

## Sesi 13 (persiapan partisi `ipados`; adb read-only; tidak ada boot, flash, atau tulisan GPT)

Rincian: [IPADOS-PARTITION.md](IPADOS-PARTITION.md).

| Pemeriksaan | Hasil |
| --- | --- |
| GPT dari Android tanpa root | hanya nama (`/dev/block/by-name`); ukuran/offset dan descriptor UFS ditolak SELinux. Ruang kosong LUN 0 **belum terukur** |
| Pembaca GPT read-only dari RAM | `package/gpt-reader` dibangun (`a7fa37bb…`, privat); audit sumber: disk `O_RDONLY` + `BLKROSET`, tulisan hanya ke RAM. **Belum dijalankan** (butuh persetujuan: tablet di-restart ke fastboot) |
| Kebutuhan `ipados` | minimum 19 126 026 240 B (17,81 GiB); disarankan 20 GiB; hanya di LUN 0 (`findRootLayout`) |
| Rancangan | A (ruang kosong, tanpa sentuh data): `plans/ipados-free-space.json`; B (kecilkan `userdata` = hapus data): `plans/ipados-shrink-userdata.json`, FAIL sampai dua persetujuan |
| Alat | `tools/gpt_capacity.py`; tes `test_gpt_capacity.py`, `test_gpt_reader_source.py`, `test_ipados_plans.py` |

## Sesi 12 (offline + adb read-only; tidak ada boot, flash, repartisi, atau perubahan slot; data Android utuh)

MODE B rute B5: **TERVALIDASI OFFLINE, BELUM SIAP UNTUK TABLET.** Rincian dan bukti: [MODE-B.md](MODE-B.md), bagian sesi 12.

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Payload | `patches/unixnu-pipa/0012`: `size_mib` 128 → **112**. Isi tetap sama (kernel `1d02cbe8…` setelah probe, ADT, GPU addon `244cc6b8…`, trust cache, seed Data; 65 887 336 B). `payload.img` 117 440 512 B `f5142b35…`; `payload_check.py` **PASS** | `~/hakios/evidence/mode-b-s12.hxWP/payload-check.txt` |
| Boot image MODE A v5 | 120 246 272 B `69525e67…`; **IMAGE CONSISTENT** (dengan `--derive`); ABL layout **PASS** | `~/hakios/evidence/mode-b-s12.hxWP/image-consistency.txt`, `abl-mode-a.txt` |
| Readiness | **NO, 1 syarat**: image root partisi `ipados` | `~/hakios/evidence/mode-b-s12.hxWP/readiness.txt` |
| ABL (biner OTA OS2.0.16) | region kernel 256 MiB dari XBL `uefiplat.cfg`; aturan penempatan + batas `image_size` dibaca dari LinuxLoader; boot stock PASS dengan ruang 234,3 MiB | `tools/abl_layout.py`, `~/hakios/evidence/mode-b-s12.hxWP/abl-stock.txt` |
| Pemilih B5 | dari `/chosen/bootargs` ABL (`force_normal_boot=1` / `mode=charger` → Android tanpa diubah; recovery → menu, initrd = payload). Model + tes, termasuk DTB Android stock asli | `tools/b5_shim_model.py`, `tests/test_mode_b.py` |
| Anggaran B5 | boot image 193 646 592 B ≤ `boot_b` (sisa 7,3 MiB), `image_size` 0xa572000 ≤ 0xea43000: **PASS**; payload maks 119 MiB | `~/hakios/evidence/mode-b-s12.hxWP/b5-budget.txt` |
| Simulasi | B5 tanpa loop di semua kombinasi; fastboot selalu tercapai; loop image MODE A di flash direproduksi | `tools/mode_b_sim.py` |
| GPT | read-only `by-name` (tanpa root): `userdata` = `sda34`, partisi terakhir LUN 0; ukuran/offset tidak terbaca (SELinux). Ruang kosong LUN 0 **tidak terukur**, hampir pasti ≈ 0 | `~/.hakios-private/gpt-sysfs.*` (privat) |
| Partisi `ipados` | **tidak ada; tidak bisa dibuat tanpa mengecilkan `userdata`** (super sisa ≈ 2,65 GiB < root 9,46 GB) | MODE-B.md |
| Artefak dipertahankan | kernel tahap B `1d02cbe8…`, Turnip/AdrenoMetal/addon dari CI 45384828742, payload v4 (`payload-v4.*`) dan v5 (`~/hakios/payload-v5.J1ox`) | lokal |
| Suite tes | 158 tes OK (4 dilewati: input tidak ada) | `python3 -m unittest discover -s tests` |

**Blocker MODE B**: (1) shim assembly belum ditulis; (2) ABL OS4.0.8.0 yang terpasang belum diperiksa; (3) tidak ada
salinan `boot_b` OS4.0.8.0 untuk pemulihan; (4) `max-download-size` belum dibaca; (5) recovery stock hanya lewat jalur
kembali ke Linux (belum ada). **Blocker iPadOS**: partisi root `ipados` — keputusan pemilik (data Android).

## Sesi 11 (WSL2 + GitHub Actions; tidak ada boot, flash, repartisi, atau perubahan slot)

### Stage B lokal

Tahap B (board lengkap, link akhir, prelink) dan `recheck` **hanya lokal**. Archive legacy display menanam firmware unit
ini sendiri: SQE `b4c27420…`, ZAP `.elf` `dd930441…`, touch NT36532 CSOT `ba7d0eb9…`. Tidak ada sumber publiknya
(hanya GMU `df79fa84…` yang byte-identik dengan `qcom/a650_gmu.bin` di linux-firmware; tiga revisi `a650_sqe.fw` di
linux-firmware semuanya lain). Firmware itu tidak pernah keluar dari mesin build: tidak di commit, artifact, log, atau
GitHub Secrets. `scripts/kernel-two-stage.sh b|recheck` menolak jalan di Actions, dan tahap B lokal memeriksa
firmware terhadap pin (`tools/firmware_check.py`) sebelum build.

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| CI run 45292813840 | `macos-firmware`, `macos-qemu-storage` (live, Intel), `macos-gpu` 15-intel dan 26-intel (rerun) **PASS**. `macos-kernel`: stage A, storage statis, Turnip + bridge, GPU addon **PASS**; stage B **FAIL** `Missing GMU firmware …/.cache/firmware/gpu/a650_gmu.bin` (bukan flake jaringan) | artefak `kernel-logs-and-manifest`, `archive-22-build-gop-legacy-display.log` |
| Workflow | stage B + recheck dihapus dari `macos-kernel`; job itu tidak lagi menunggu `macos-qemu-storage` (record live hanya untuk tahap B; `storage-static` tidak membacanya). Job QEMU tetap jalan | `.github/workflows/unixnu-build.yml` |
| Guard | `GITHUB_ACTIONS=true kernel-two-stage.sh b` / `recheck` → `ERROR: stage b is local only …` | lokal |
| Firmware lokal | **FIRMWARE PASS** (4/4 terhadap `proprietary-files.txt` + manifest ROM resmi) | `evidence/readiness-s11.*/firmware-check.txt` |
| Kernel tahap B lokal | Dua clean build baru (TAG v5, path sama, dengan cek firmware): tahap B **`1d02cbe8…` = baseline sesi 10**, tahap A `1b094fd6…`, keduanya **REPRODUCIBLE**. `stage-b.log` tetap berakhir `ERROR: a required archive input was skipped`: hanya `build-pipa-gpu-addon` (Turnip lokal tidak ada; addon = input payload, bukan kernel, diambil dari CI). Cek transfer storage final yang tidak sempat dijalankan skrip, dijalankan terpisah: **STORAGE ABI TRANSFER PASS** | `evidence/repro-v5-run{1,2}` |
| Image consistency | **Koreksi sesi 10**: pada kernel tahap B `1d02cbe8…` cek "payload kernel = kernel yang dibangun" **FAIL**: langkah payload UniXNU menulis ulang kernel (`patch-xnu-entry-probe.py --panic-screen --no-reset`, `scripts/unixnu/payload.py`) → `c0350252…`. Dibuktikan byte-identik dengan mengulang patch pada salinan `1d02cbe8…`. `tools/image_consistency.py --derive 'CMD {}'` kini mengulang derivasi itu (tidak percaya `payload.json`): **IMAGE CONSISTENT** | `evidence/readiness-s11.*/image-consistency.txt`, `tests/test_image_consistency.py` (13) |
| Payload | `tools/payload_check.py` **PASS** lagi; layout DarwinBoot `0x4efc000` dari window `0x170000000` | `…/payload-check.txt` |
| Peta DRAM offline | `tests/test_adt_dram.py`, `test_memory_plan.py` (termasuk sumber pipa asli: window hanya di `0xffe00000..0x280000000`), `test_payload_check.py` **OK** | lokal |
| Boot image | 137 023 488 B ≤ `boot_b` 201 326 592 B; kernel image = BootShim + FD `bd39c37a…`; DTB = `pipa.dtb` | idem |
| Readiness | `scripts/readiness.sh` kini menerima `--out DIR` (berulang) dan `--derive`; dengan `out-repro-v4-run2` + `payload-v4`: **NO, 1 syarat**: image root untuk partisi `ipados` tidak ada | `…/readiness.txt` |
| MODE B | Penyebab loop dipastikan (entri Android = `reset`). Opsi baru B5 (ABL tetap memuat Android; menu lewat kernel Android yang ditambal), anggaran ruang diukur: payload harus ≤ 112 MiB | [MODE-B.md](MODE-B.md) |

**Blocker berikutnya**: root iPadOS butuh partisi `ipados`, yang tidak ada di GPT stock. Membuatnya = mengecilkan
`userdata` = data Android hilang (MODE-B.md, "Root iPadOS terpisah"); ruang kosong di akhir LUN 0 belum pernah diukur.
Itu keputusan pemilik, bukan langkah build.

## Sesi 10 (WSL2 + GitHub Actions Intel; tidak ada boot, flash, atau perubahan slot)

BUILD PASS ≠ RUNTIME PASS ≠ GPU HARDWARE ACCELERATION PASS: semua di bawah adalah build dan pemeriksaan offline.

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Penyebab ADT gagal | generator `devicetree.generate()` UniXNU (pin dan upstream) hanya menerima satu node memory dengan satu rentang; DTS pipa (benar) punya dua bank di sekitar celah bootloader `0xbbb00000..0xc0000000` | [MEMORY.md](MEMORY.md) |
| Representasi RAM | Bank tetap terpisah; ADT `dram-base/size` = span `0x80000000+0x200000000` (dipakai XNU hanya untuk `is_dram_addr`); memori kernel = window DarwinBoot dari satu run conventional UEFI, yang tidak bisa memuat celah. Patch `patches/unixnu/0006` | `tests/test_adt_dram.py` (8) |
| Rencana memori offline (`tools/memory_plan.py`) | **PASS**: window `0x170000000` hanya muat di `0xffe00000..0x280000000`, sisa 258 MiB untuk alokasi UEFI (hanya terbukti saat boot; bila kurang, DarwinBoot menolak dengan "NO WINDOW") | `tests/test_memory_plan.py` (7) |
| UUID volume Data | **Ditemukan**: kernel `81fa3170…` menanam UUID Data penulis port (`73F1FA24…`), seed pemilik `data.dbr` berisi volume lain. UniXNU mengikat keduanya di `runtime.prepare`, yang tidak pernah jalan untuk pipa (tanpa `[payload.runtime]`), dan payload tidak memeriksanya. `kernel-two-stage.sh` kini menerapkan aturan UniXNU sendiri (`HAKIOS_DATA_SEED`); nilai UUID tidak dicatat | `tools/payload_check.py` |
| Kernel tahap B baru | `1d02cbe8d9992f32ad8e96ac2a475e41eba8667fdb7c52d42162e940deb3dc59` (53 899 264 B, 26 409 ekspor): **reproducible** (dua clean build di path sama identik); tahap A tetap `1b094fd6…`. Recheck HID PASS (52 simbol), storage ABI transfer pada kernel final PASS, anchor + 2 kebijakan VerifiedRoot tertanam. `81fa3170…` tetap disimpan sebagai baseline sesi 8 (UUID Data lain) | `evidence/repro-v4-run{1,2}` |
| Addon di tahap B lokal | builder in-tree SKIP (tanpa iphoneos SDK) diterima **hanya** untuk addon eksternal yang lolos `tools/owner_trust.py` (owner-trust = byte CI `89bcf73f…`) | `stage-b.log` |
| Payload | **BUILD PASS**, `payload.img` 128 MiB `2b88a52c…`; `tools/payload_check.py` **PASS** (18 cek: kernel diparse seperti DarwinBoot, ADT span/window/memory-map, trust cache aturan DarwinBoot 2557 hash, addon = addon terverifikasi dan ketiga Mach-O-nya tercakup, UUID seed = kernel, layout window dipakai `0x4efc000`) | `evidence/payload-v4/` |
| Ukuran boot image | **Ditemukan**: dengan `size_mib = 192` boot image 204 132 352 B > `boot_b` 201 326 592 B (ABL menolak dan menandai slot unbootable, 17 Nov). Patch `patches/unixnu-pipa/0011`: 128 MiB → boot image **137 023 488 B**. `image_consistency.py` kini menolak image di atas partisi | `tests/test_image_consistency.py` |
| Firmware uefi-pipa (lokal WSL) | **BUILD PASS**, `SILICIUM_UEFI.fd` `bd39c37a…` (pin hakios, DarwinBoot dengan window) | lokal |
| Image consistency | **IMAGE CONSISTENT**: ramdisk = payload, payload kernel = kernel yang dibangun, kernel image = BootShim + FD, DTB yang ditambahkan = `pipa.dtb`, ukuran ≤ `boot_b`. Penanda IMG4 hanya dari string kernel Apple: NOTE, image lokal saja | `boot.img` `6cbdba80…` |
| Reproducibility Turnip | Penyebab: urutan, bukan isi (18 420 string sama, urutan lain). Dengan `PYTHONHASHSEED=0` dua clean build di runner yang sama **identik** (`e2319655…`, UUID `30C7371C…`, 0 objek/sumber berbeda). Bahwa seed acak adalah satu-satunya penyebab antar-run belum dibandingkan antar-runner | artifact `turnip-repro-*` run 45283950842 |
| CI regression (Intel) | `macos-firmware` **PASS** (run 45283950842), GPU 15/26 lihat di bawah; `macos-qemu-storage` gagal: `patch-xnu-entry-probe.py` mencari `llvm-nm` di `/opt/homebrew` (Homebrew arm64), di Intel ada di `/usr/local` → llvm Homebrew masuk `GITHUB_PATH`; `macos-kernel` di-skip karena bergantung padanya | log job 138075278746 |
| Dual boot MODE A | Menu payload asli: Android default, timeout 10 s, entri android/xnu/recovery/reset/shutdown/tools, storage_safety tanpa FAIL. **Tidak diuji di tablet** | `verify_bootimg.check_unixnu` |
| Dual boot MODE B | **Tidak tercapai**: entri Android kedua menu (UniXNU dan U-Boot) adalah `reset`; dengan menu di `boot_<aktif>` itu kembali ke menu yang sama (loop). Handoff nyata ke boot image Android stock (kernel 4.19, vendor_boot, dtbo, cmdline/bootconfig ABL, AVB) belum ada di firmware mana pun | [MODE-B.md](MODE-B.md) |
| Akselerasi GPU di tablet | **NOT TESTED** (tidak ada boot) | — |

## Sesi 9 (WSL2 + GitHub Actions; push lewat `gh auth login` pemilik)

Audit riwayat sebelum push (71a88ba..bba1a66): tidak ada firmware biner, kunci privat, chip-id platform, serial perangkat,
atau path/nama pribadi; hanya digest SHA-256 publik. Push tanpa force; tablet hanya dibaca (`fastboot getvar`: pipa, slot b
successful), tidak di-flash atau di-reboot.

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Runner GPU | arm64 `macos-15`/`macos-26` tidak pernah didapat ("not acquired by Runner of type hosted", run 45256692481) → matriks `macos-15-intel` + `macos-26-intel`; cross file Mesa menamai target `arm64-apple-ios17.0`, jadi output tetap arm64 iOS | `.github/workflows/unixnu-build.yml` |
| Turnip iOS (`libvulkan_freedreno.dylib`) | **BUILD PASS di kedua image** (run 45271686452): Mach-O arm64 dylib, platform iOS, minos 17.0 (SDK 18.5 / 26.5); `-Dtu-darwin-abi-dir` = `drivers/Adreno650` pipa. RG88/GR88 dan Dl_info dari run 45107232121 **tidak muncul**: tanpa patch Mesa. Yang benar-benar diperbaiki dari log: tree baru tidak berisi `drivers/Adreno650`/`AdrenoMetal` (kini di-link dari port seperti `build-adreno650.py`), retry fetch, path artifact | log job 138032825471 / 138032825204 |
| AdrenoMetal bridge (`libadreno_metal_bridge.a`) | **BUILD PASS**: metal2vulkan `720ef1ce` + 21 patch pipa, identik di kedua image (`91059a95…`). Perbaikan: std `aarch64-apple-ios` untuk Rust 1.98.0 (E0463) | idem |
| GPU addon (`build-pipa-gpu-addon.py`) | **BUILD PASS tanpa SKIP** (stage `gpu-addon`; SKIP atau output hilang = gagal): NativeAdrenoMetal.bundle, adrenoprobed, owner-trust.bundle, gpu-addon-clients.bin (NGPUADD2, 11 file). Perbaikan: `glslc`/`spirv-val` (shaderc, spirv-tools). Modul trust asli dari member IPSW `StaticTrustCache` + `Cryptex1,SystemTrustCache` (`tools/original_trust.py`, digest pin `da88460e…`/`d121ba89…` → bundle `7416ca4f…`, sama dengan di runner) | `gpu-addon-sha256.txt` artifact |
| Rekonstruksi owner-trust lokal (`tools/owner_trust.py`) | **PASS**: CDHash plugin + daemon dihitung dari tanda tangannya sendiri = trust.json; ketiga Mach-O di dalam blob addon (plugin, Turnip bertanda tangan, daemon) tercakup modul owner; bundle hasil rekonstruksi = byte CI (`89bcf73f…` macos-15-intel, `c3c6b6c9…` macos-26-intel). Bundle tidak pernah diunggah (berisi modul Apple) | lokal |
| Kompatibilitas userland 21H461 (`tools/dsc_import_check.py`) | **PASS**: setiap import two-level dylib Turnip (277/278), plugin (370/365) dan adrenoprobed (66/69) ada di library yang dirujuk dalam dyld shared cache 21H461; 0 hilang, 0 weak hilang. Kontrol negatif: kelas Metal iOS 18 (`MTLLogStateDescriptor`, `MTLResidencySetDescriptor`) memang tidak ada | lokal |
| `A650GmuTests` | **PASS** di qemu-aarch64 10.2.1 user mode (gcc + clang, `-Werror`, statis), dengan firmware bawaan test dan dengan `a650_gmu.bin` perangkat (`df79fa84…`): 16 blok, versi 0x20010008, HFI siap | `scripts/a650-gmu-tests.sh` |
| VerifiedRoot (host self-test) | **PASS** dengan kebijakan owner asli (2/2, semua manipulasi ditolak); anchor RSA lain: FAIL seperti seharusnya | `tests/pipa-verified-root-selftest-host.c` (port) |
| Lima simbol backlight | Audit: definisi nyata (driver KTZ8866), bukan stub; `native_backlight_scale` = 256 = nilai fallback pemakai weak, jadi perilaku sama dengan pengikatan-ke-0 ld Apple. Catatan: `sheng_backlight_probe_result = -6` dipakai dua kali (vtable dan start), sama dengan versi yang diuji di tablet, tidak diubah | patch port 0007 |
| Kernel tahap B | `81fa3170…` dipertahankan (v3-run1 = v3-run2). **Koreksi sesi 8**: link dan prelink PASS, tetapi `stage-b.log` berakhir `ERROR: a required archive input was skipped` (addon SKIP karena Turnip belum ada). Addon bukan input `kernel.macho`: ia masuk payload (`--gpu-addon` → `kernel.macho.gpuaddon`, ditulis kernel ke Data) | `repro-v3-run1/stage-b.log` |
| Payload (kernel `81fa3170…` + addon + owner-trust) | **BLOCKED (bukan GPU)**: `unixnu build payload` menerima kernel, addon NGPUADD2 dan trust, lalu berhenti di ADT: "ADT handoff requires one contiguous DRAM range". `dts/pipa.dts` port `c4c1a3a` punya dua rentang (0x80000000+0x3bb00000, 0xc0000000+0x1c0000000; celah bootloader 0xbbb00000..0xc0000000), generator schema-2 UniXNU `62f203c` hanya menerima satu. Tidak ditambal: menggabungkan rentang berarti menebak peta memori | dry-run lokal |
| Reproducibility Turnip | dylib berbeda antar-run dan antar-image (mis. macos-15-intel `2efec90d…` lalu `3440abab…`); bridge identik. Belum diselidiki | log CI |
| Akselerasi GPU di tablet | **NOT TESTED**: tidak ada boot | — |

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
| Turnip iOS / bridge / GPU addon | **NOT BUILT** di sesi 8 (butuh Xcode); dibangun di sesi 9 (di atas). Detail: [ADRENO650.md](ADRENO650.md) | — |
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
