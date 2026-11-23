# Bootstrap dua tahap kernel pipa

## Kenapa perlu

Tiga builder di port EsaiJJ/UniXNU-pipa memeriksa driver-nya terhadap kernel yang **sudah di-prelink**:

| Builder | Yang dibaca dari kernel referensi | Kalau referensi tidak ada |
| --- | --- | --- |
| `build-sheng-hid-input.py` (archive `component:ShengHidInput`) | `build/xnu-prelink/native-owner-ufs-cpu-desktop-*-candidate.macho` + plan `.json` | Gagal: "No reference candidate available" |
| `build-gop-legacy-display.py` | `out/…/kernel/kernel.macho`, disalin ke `…-pipa-candidate.macho`; builder ini juga memanggil builder HID | Gagal: "Missing board kernel" |
| `build-platform-power.py` | `out/…/kernel/kernel.macho` | Rancangan port sendiri: `sheng_pmgr_run` no-op dan pesan "Build the kernel again to link the bridge" |

Isi referensi yang dipakai, dari audit source:

- **Alamat binding** (`IOHIDDevice` C2/D2, `gMetaClass`, vtable, dan slot >= 168) adalah alamat di kext
  **asli** IOHIDFamily dari kernelcache 21H461. Alamat ini hanya bergantung pada kernelcache dan slide
  (`-0x1000000`), tidak pada layout kernel native.
- **Hash `__TEXT_EXEC` IOHIDFamily** (`7e4c5104…`) diambil dari plan prelink.
- **Simbol native** (`__ZTV9IOService`, `___cxa_pure_virtual`, IOService C2/D2) hanya dipakai untuk mengecek
  bahwa kandidat itu sendiri konsisten: vtable asli yang sudah di-rebind harus menunjuk ke IOService native milik
  kandidat yang sama.

Jadi kernel referensi tidak harus kernel akhir. Syaratnya: hasil prelink UniXNU yang sungguhan, dari kernelcache
yang sama dan slide yang sama. Setelah kernel akhir jadi, binding tetap dicek ulang.

## Tahapan (`scripts/kernel-two-stage.sh`, job `macos-kernel`)

1. **Tahap A** menerapkan `patches/stage-a/0001` ke port. Patch ini tidak menambah apa pun; isinya hanya mematikan:
   - dua baris archive (`component:ShengHidInput` dan `build-gop-legacy-display.py`) beserta pilihan komponen
     ShengHidInput;
   - CONFIG berikut, diubah ke `n`: `NATIVE_LEGACY_DISPLAY`, `NATIVE_ADRENO`, `NATIVE_UFS`, `BOOT_PROGRESS(_STANDALONE)`,
     `NATIVE_RAM_BLOCK`, `NATIVE_VIRTIO_BLOCK`, `VERIFIED_ROOT_PROBE`, dan seluruh `OWNER_*`.

   Archive-nya tetap dibangun, hanya tidak di-link. Alasan tiap pemotongan, dengan bukti CI:
   - Run 45096983204: komponen yang dipilih wajib punya entri archive, jadi ShengHidInput harus dicabut dari pilihan.
   - Run 45097715798: `bindings.json` VirtioMmioBlock/RamBlock tidak ada. Penjelasannya di "Blocker storage" di bawah.
   - Run 45099062345: Adreno mengimpor `native_gop_handoff_call/_memory` dari archive display.

   Setelah itu `./unixnu build kernel` membangun XNU, archive, link final, dan prelink.
   `tools/candidate_provenance.py record` lalu menolak kandidat yang bukan output prelinker. Yang diperiksa:
   sha256 kandidat = `candidate_sha256` di plan, `images_modified=false`, hash IOHIDFamily asli, extent
   IOHIDFamily `__TEXT_EXEC`, Mach-O arm64, `__TEXT` sejajar 16 KiB, dan ekspor wajib.
   Provenance mencatat commit, hash patch tahap A, dan `boot_candidate: false`. Patch kemudian dicabut lagi.
2. **Tahap B** memasang kandidat tahap A (`…-stagea-candidate.macho`) setelah diverifikasi ulang, lalu membangun
   board lengkap tanpa satu pun pemeriksaan ABI port yang dilemahkan.
3. **Recheck** menjalankan builder HID asli sekali lagi dengan kernel akhir sebagai referensi.
   `compare-bindings` menuntut binding, slot milik driver, ukuran instance, dan hash teks yang identik.

## Batasan tahap A

Kernel tahap A **bukan image boot**. Tahap A tidak memuat:

- touch (`ShengHidInput`);
- archive display legacy, yang juga membawa USB, Wi-Fi, Bluetooth, touch Novatek, tombol, dan objek firmware GMU/SQE/ZAP;
- jembatan PMGR (no-op dari port).

Kernel ini dan kernel akhir mengandung kext Apple, jadi tidak diunggah. Yang diunggah sebagai artefak hanya
plan, provenance, daftar ekspor, hash, dan log.

Test: `tests/test_candidate_provenance.py`, dengan kasus negatif untuk hash salah, file diubah setelah prelink,
arsitektur salah, layout `__TEXT` tidak sejajar, simbol hilang, IOHIDFamily lain, `images_modified`, provenance
kernel lain, input hilang, binding bergeser, binding hilang, layout berbeda, dan recheck terhadap referensi yang sama.

## Hasil (sesi 5)

| Run | Hasil |
| --- | --- |
| 45099835381 | **Tahap A PASS**: 18 archive, link final, prelink. `kernel.macho` `510999e4…` (51 974 144 B, 22 611 simbol ekspor), provenance PASS. Tahap B: **ShengHidInput PASS** terhadap kandidat ini ("original HID instruction identity, base imports, call boundaries and exact owned vtable"), lalu PMGR gagal karena path kernelcache |
| 45100879621 | Tahap A PASS lagi (`9a2eec5b…`, ukuran sama). Tahap B: 20 dari 21 langkah archive PASS, termasuk HID, jembatan PMGR asli ("unchanged AMFI read/OR/write and original PMGR provider dispatch", 254 528 B; tahap A hanya no-op 576 B), boot progress, Adreno 650 (31 objek), GPU addon, dan audit ABI display legacy ("358 slots with nine abstract leaves"). Berhenti di `build-gop-legacy-display.py`: **firmware GMU `a650_gmu.bin` tidak ada** |

Hash archive per tahap ada di log job (`stage-a-archives-sha256`, `stage-b-archives-sha256`) dan di artefak
`kernel-logs-and-manifest`. Archive identik antar-run, tetapi `kernel.macho` tahap A tidak: dua run menghasilkan dua
sha256 berbeda dengan ukuran sama. Penyebabnya belum diperiksa. Dugaan saya string versi/tanggal build XNU, tetapi
ini belum dibuktikan.

## Blocker tahap B

1. **Firmware perangkat untuk archive display legacy.** Yang dibutuhkan: `a650_gmu.bin`, `a650_sqe.fw`,
   `a650_zap.elf` (bertanda tangan pipa) dan `novatek_nt36532_m82_fw_csot.bin` (dari kernel stock).
   Semuanya proprietary dan tidak boleh masuk GitHub atau CI publik. Sumbernya
   `scripts/extract-pipa-firmware.py` milik port, yang hanya membaca `/vendor` lewat adb, lalu disimpan di
   `UniXNU-pipa/.cache/firmware` (atau diberikan lewat `PIPA_*_FIRMWARE`) di mesin pemilik.
2. **Kualifikasi storage asli (link final board lengkap).** VirtioMmioBlock dan RamBlock mengimpor
   `IOBlockStorageDevice` asli lewat `build/storage-abi/interface-audit.json`. File itu dibuat oleh
   `audit-storage-interface.py`, yang membutuhkan kandidat `native-apfs-load-positive` dan **observasi live QEMU/gdb**
   (`darwinboot-storage-native-metadata/gdb-stop.json`: ukuran instance 0x90/0x88 dan translasi 4K). Tidak ada script
   di UniXNU 62f203c yang membuat observasi itu, dan tidak ada rekamannya di ref UniXNU mana pun. Board EsaiJJ juga
   tidak punya langkah `build-virtio-mmio-bindings.py`, padahal board xVanTuring punya.
   Alternatif source-based dari UniXNU (`build-sheng-source-storage.py`) mensyaratkan arm64e iPadOS 26, jadi tidak
   berlaku untuk target ini.
   Melonggarkan syarat `live_native_4k` tidak dilakukan, karena itu berarti melemahkan pemeriksaan.

## Sesi 6

**Kernel tahap A reproducible.** Penyebab hash berbeda di sesi 5 ditemukan: `config/newvers.pl` milik XNU
menuliskan `date` ke string versi ("Darwin Kernel Version 23.6.0: Mon Nov 23 03:16:45 UTC 2026; runner:…"),
sedangkan semua archive identik. `KERNEL_BUILD_DATE`, yang oleh XNU sendiri disebut sebagai saklar build
reproducible, sekarang dipatok ke tanggal commit pin UniXNU. Hasilnya, run 45105668358 dan 45106011890 (commit dan
kunci ephemeral berbeda) menghasilkan `kernel.macho` `d0ba5de5…` dengan UUID `c700fb3e…` yang identik, begitu juga
run 45107232121. Sidik jarinya dibuat oleh `tools/macho_fingerprint.py`.

**Storage ABI: tiga status yang dipisahkan.**

| Status | Hasil | Bukti |
| --- | --- | --- |
| ABI STATIC VERIFIED | **PASS**: semua pemeriksaan `audit-storage-interface.py` sebelum langkah live lolos pada kernel tahap A (190 slot, vtable unik, konstruktor/destruktor, getter metaclass) | run 45107232121, `kernel-two-stage.sh storage-static` |
| ABI LIVE VERIFIED | **PASS (guest QEMU virt, TCG)**: kernel board xVanTuring/UniXNU-qemu `fa7a7091…` (IPSW dan kernelcache sama; 10 archive, link, prelink; payload 192 MiB) di-boot di QEMU dan dihentikan oleh `gdb-stop.py` milik UniXNU. Hasil: ukuran instance live IOBlockStorageDevice 0x90 dan IOService 0x88, `live_native_4k` true, 190 slot, 176 binding. `interface-audit.json` `62f14fa0…` ditulis oleh `audit-storage-interface.py` yang tidak diubah. Butuh `patches/unixnu-qemu/0001–0003` (skew nama dan path dengan UniXNU 62f203c, satu perubahan per patch) | run 45111858703 |
| RUNTIME HARDWARE VERIFIED | NOT TESTED (QEMU bukan tablet) | — |

Langkah berikutnya untuk storage: board pipa belum punya langkah `build-virtio-mmio-bindings.py`. Board xVanTuring
punya: `--component VirtioMmioBlock --directory build/virtio-mmio-block-verified` dan `--component RamBlock
--directory build/ram-block`. Kedua langkah itu perlu ditambahkan, lalu `interface-audit.json` dari job QEMU dipakai
sebagai input (job `needs:` atau artefak). Integrasi ini baru bisa diuji ujung-ke-ujung setelah blocker firmware
archive display terpecahkan.

## Sesi 7 (lokal di WSL2)

- **Rekaman storage live dibuat ulang secara lokal** (QEMU TCG, `gdb-stop.py` UniXNU tanpa perubahan pada logika
  observasinya). Perbaikan host: `TargetConditionals.h`/`nm` dari toolchain Linux UniXNU (lingkungan yang sama dengan
  langkah kernel UniXNU), `-Wno-missing-designated-field-initializers` pada objek anotasi (clang 24), output
  `build/DarwinBoot` huruf kecil (DSC), dan tenggat koneksi port gdb 60 s. Tidak ada syarat `audit-storage-interface.py`
  yang dilonggarkan.
- **Patch port 0004** menambahkan dua langkah `build-virtio-mmio-bindings.py` (RamBlock, VirtioMmioBlock) seperti board
  xVanTuring; **stage-a 0002** mematikannya di tahap A. Tahap B memasang `interface-audit.json`
  (`HAKIOS_STORAGE_AUDIT`) hanya setelah `tools/storage_abi_transfer.py` lolos pada kernel tahap A, dan memeriksa ulang
  pada kernel final.
- **Patch unixnu 0005**: pemeriksaan link membaca objek dengan nama runtime-nya (`NativeVirtioBlock.o`,
  `NativeRamBlock.o`) dan kini juga menuntut objek itu identik dengan member arsip yang di-link.
- **Patch port 0005** (QcaBluetooth 22ff97f tanpa `fetch-linux.py`) dan **0006** (arsip VerifiedRoot lengkap: anchor,
  kebijakan OS/SystemOS bertanda tangan owner dari `PIPA_VERIFIED_ROOT`, `verified_root.c`, `xnu_crypto.c`).
- Sumber Ath12kWifi: `fetch-sources.py` meng-clone branch `releng/15.1` yang sudah bergerak; commit terkunci
  `95719d8a…` dipilih manual, sparse-checkout non-cone (git 2.53), lalu `--check` alat itu PASS. Perlu perbaikan di hulu.
- Sisa blocker link: referensi `weak_import` backlight (lihat STATUS.md). Rute yang sesuai rancangan: tahap B di macOS
  (ld Xcode), yang juga diperlukan untuk Turnip.

## Sesi 8

- Link final tahap B lolos setelah patch port 0007 (backlight KTZ8866), 0008 (NativeUfs verified, satu
  `IOBlockStorageDevice`) dan 0010 (self-test owner-root nyata). Prelink selesai; kernel reproducible pada path sama.
- `kernel-two-stage.sh` menerima `UNIXNU_OUT` untuk clean build di direktori baru. Pelajaran: jangan mengedit skrip
  ini selama ia berjalan; bash membacanya bertahap (clean build pertama sesi 8 rusak karena itu, kernelnya tidak dipakai).
- `gpu-userland` kini berjalan di tree pipa (ABI Adreno650, frontend dan pin translator pipa); belum diuji di macOS.
