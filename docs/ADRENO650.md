# Adreno 650: status dan rencana

**Status: tidak ada akselerasi GPU yang terbukti di unit pemilik.** Jalur utama ada di basis UniXNU-pipa.

## Konstanta yang dicek (`tools/a650_check.py`, dari source)

| Nilai | Linux `a6xx_catalog.c` | UniXNU-pipa `A650Gmu.h` | Tree live | HakiOS |
| --- | --- | --- | --- | --- |
| Chip id | 0x06050002, `ADRENO_6XX_GEN3` | 0x06050002 | 0x06050002 | — |
| Chip id untuk GMU | rumus `a6xx_gmu_fw_start` → 0x06050200 | — | — | `adreno642_gmu_chip_id` → 0x06050200 (sama untuk chip ini) |
| Firmware | `a650_sqe.fw`, `a650_gmu.bin`, `a650_zap.mdt` | `a650_*` dari `/vendor/firmware` | zap `a650_zap.mbn` (mainline) | **`a660_*`** |
| GMEM | 1 MiB + 128 KiB | — | — | dari board (`gmem-kb`) |
| `prim_fifo_threshold` | 0x00300200 | — | — | dari board |
| GMU block | — | 0x3d6a000 (+RSCC 0x3de0000, PDC 0xb290000) | 0x3d6a000 | — |

Hasil: chip id dan rumus GMU sepakat; **HakiOS hanya meminta firmware A660 → GAP** (dicatat oleh `build.sh`).

## Kenapa driver HakiOS tidak bisa dipakai langsung

A650 adalah `ADRENO_6XX_GEN3`; driver HakiOS ditulis untuk `GEN4` (keluarga A660). Di Linux `a6xx_gpu.c`, cabang
khusus `adreno_is_a660_family` ada di baris 1310, 1386, 1709, 1988; cabang `a650_family` di 768, 1251, 1279, 1299,
1364; `a6xx_gmu.c`: 700, 739, 789, 889, 954, 2371–2448. Plus tabel `a650_hwcg`, `a650_protect`, `a640_gbif`,
`gmu_cgc_mode 0x00020202`. Port A650 ke HakiOS = memisahkan langkah-langkah itu per keluarga. Tidak dikerjakan di
sesi ini: tidak bisa diuji tanpa hardware, dan basis iPadOS 17 yang dipilih sudah punya driver A650.

## Jalur UniXNU-pipa (basis yang dipilih)

| Target | Komponen | Bukti |
| --- | --- | --- |
| 1. Inisialisasi GPU | `package/GpuProbe.cpp` mode 6 (CX, SMMU GPU, command DB, clock GMU 200 MHz) | host test `GpuPowerBoardTests` PASS di sini; klaim tablet xVanTuring 24 Okt |
| 2. Firmware GMU | `package/A650Gmu.c` mode 7 (urutan a650 Linux v6.6, HFI) | `A650GmuTests` NOT RUN di sini |
| 3. Command submission | `drivers/Adreno650` + `kits/AdrenoPM4` | belum diuji |
| 4. Memori GPU, 5. SMMU | `kits/ArmSmmu4K` (stream 5 / 0x405 ke bank 1) | belum diuji |
| 6. Sinkronisasi | `AdrenoMetal` shared events/fences | belum diuji |
| 7. Rendering hardware, 8. Metal | `AdrenoMetal` → Vulkan (Turnip) | klaim 40–54 fps (unit 16 GB), belum diuji di sini |
| 9. WindowServer, 10. kompositing SpringBoard | backboardd/CoreAnimation lewat Metal plugin, salinan GPU ke framebuffer | klaim; sudut bulat salah di pass GMEM |

Membedakan GPU nyata dari software rendering di tablet (langkah Claude Code): log kernel `gpu:` (mode 7: firmware
GMU 0x20010008, HFI ready, 4 pesan startup), `NativeAdreno` terpublikasi, dan tanpa file publish plugin UI kembali
dirender CPU — bandingkan fps keduanya. Sampai itu terlihat di unit pemilik: **NOT TESTED**.

## Status build per lapisan (sesi 6, CI)

| Lapisan | Status | Bukti |
| --- | --- | --- |
| GPU KERNEL ARCHIVE (`libAdreno650.a`, 31 objek NativeAdreno) | **PASS (build)** | run 45100879621, archive identik antar-run |
| GPU addon (`build-pipa-gpu-addon.py`) | **SKIP = tidak dibangun**. Sesi 5 salah menghitungnya PASS. Builder mencetak "SKIP … missing Turnip libvulkan_freedreno.dylib" dan exit 0. Sekarang SKIP apa pun menggagalkan tahap B | log run 45100879621 |
| GPU USERLAND BUILD: Turnip iOS (`libvulkan_freedreno.dylib`) | **FAIL (compile)**. Sudah lewat: seri patch Mesa (setelah backport header `turnip-frame-diagnostics`), konfigurasi meson, dan parser ir3 (bison 3.8.2). Berhenti dengan 19 error di Mesa util: `PIPE_FORMAT_RG88_UNORM/GR88_UNORM` tidak dideklarasikan di `u_format_gen.h`, `Dl_info`/`dladdr` di `disk_cache.h`. Akar penyebab belum dipastikan | run 45107232121 |
| AdrenoMetal bridge, trust bundle asli | NOT RUN: menunggu Turnip. Trust bundle butuh IPSW lengkap | — |
| GPU INTEGRATION (archive display legacy, GMU/SQE/ZAP tertanam) | BLOCKED: firmware perangkat | `tools/firmware_check.py` |
| `A650GmuTests` | NOT RUN | — |
| GPU HARDWARE ACCELERATION | **NOT TESTED**. Tidak ada klaim | — |

## Status per lapisan (sesi 8, lokal WSL2)

| Lapisan | Status | Bukti |
| --- | --- | --- |
| GPU KERNEL ARCHIVE (`libAdreno650.a`, 31 objek) | **PASS (build)**, ter-link dalam kernel final | `evidence/repro-*/stage-b.log` |
| GPU INTEGRATION (archive display legacy dengan GMU/SQE/ZAP/touch asli, layanan backlight KTZ8866) | **PASS (build + link)** | idem |
| `A650GmuTests` (host test GMU/HFI) | **BUILD PASS untuk aarch64** (`-Werror`, statis, dengan `a650_gmu.bin` asli sebagai argumen). **NOT RUN**: kit HFI hanya untuk AArch64 little-endian, dan host x86 ini tidak punya `qemu-user` (perlu `sudo apt install qemu-user`) | `evidence/host-tests/a650-aarch64` |
| Turnip iOS (`libvulkan_freedreno.dylib`) | **NOT BUILT**: butuh Xcode iphoneos SDK; WSL tidak punya, dan push untuk CI belum bisa (tanpa kredensial) | — |
| Rute ABI Turnip/bridge | **DIPERBAIKI (belum diuji)**: `kernel-two-stage.sh gpu-userland` dulu berjalan di checkout UniXNU, jadi memakai KMD `drivers/Adreno740` dan frontend AdrenoMetal milik UniXNU, bukan milik kernel pipa. Kini di tree pipa: `Adreno740 -> Adreno650` pipa (konstanta dan ukuran sama, plus `MaxQueues`/`MaxBoBytesShift`), `AdrenoMetal` pipa, bridge dari pin translator pipa `720ef1ce` (patch port 0009), seperti build addon pipa yang berhasil di `macos-15-intel` | `scripts/kernel-two-stage.sh` |
| Error RG88/GR88, `Dl_info` | **AKAR BELUM TERBUKTI**. Fakta: `u_format_gen.h` memakai `RG88/GR88` di 17 fungsi inline sendiri (17 + 2 = 19 error), jadi kedua cabang `UTIL_ARCH_*_ENDIAN` tidak terambil; `Dl_info` muncul bila `HAVE_DLADDR` aktif tanpa `HAVE_DLFCN_H`. Header publik Apple (Libc-1752, dyld-1378, xnu-12377) tidak menunjukkan perubahan yang menjelaskannya. Job CI `macos-gpu` (matriks macos-15/macos-26) mengirim error pertama, makro `HAVE_*` dan header SDK sebagai anotasi publik | `.github/workflows/unixnu-build.yml` |
| GPU addon (`NativeAdrenoMetal.bundle`, trust bundle) | **SKIP = FAIL**. Ini input payload (`--gpu-addon`), bukan bagian `kernel.macho` | — |
| GPU HARDWARE ACCELERATION | **NOT TESTED**. Tidak ada klaim | — |

## Status per lapisan (sesi 9, CI Intel + lokal)

| Lapisan | Status | Bukti |
| --- | --- | --- |
| GPU USERLAND BUILD: Turnip iOS | **PASS (build)** di `macos-15-intel` (SDK 18.5) dan `macos-26-intel` (SDK 26.5), run 45271686452: arm64 dylib iOS minos 17.0, ABI KMD `drivers/Adreno650` | `docs/STATUS.md` sesi 9 |
| AdrenoMetal bridge | **PASS (build)**, `91059a95…` di kedua image | idem |
| GPU addon | **PASS (build), tanpa SKIP**; owner-trust direkonstruksi lokal = byte CI; semua import ada di dyld cache 21H461 | idem |
| `A650GmuTests` | **PASS** (qemu-aarch64 user mode, gcc + clang, firmware perangkat) | `scripts/a650-gmu-tests.sh` |
| GPU INTEGRATION (payload) | **BLOCKED** oleh ADT DRAM (dua rentang di DTS port, generator butuh satu); bukan masalah GPU | idem |
| GPU HARDWARE ACCELERATION | **NOT TESTED** | — |
