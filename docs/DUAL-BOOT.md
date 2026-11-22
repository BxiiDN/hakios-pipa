# Dual boot Android/HyperOS + HakiOS di Xiaomi Pad 6

Status: **desain + validator offline. Belum diuji di tablet. Dual boot belum berhasil sampai kedua OS dilihat
berjalan bergantian di Pad 6.**

## Mode 1 — RAM boot (default, dipakai sekarang)

```
Tablet dinyalakan biasa ──> ABL ──> Android/HyperOS (default, tidak berubah)

PC: fastboot boot build/hakios-pipa-bootmgr.img
      └─> U-Boot dari RAM ──> Boot Manager (Vol+/Vol- pilih, Power konfirmasi, 10 s → Android)
            1. Android / HyperOS      → reset → ABL boot Android seperti biasa
            2. HakiOS (Darwin)        → loader.efi → XNU → Darwin, semuanya di RAM
            3. Recovery / Fastboot    → reset sambil tahan Vol+ (recovery) atau Vol- (fastboot)
```

Yang dijamin oleh desain (dan dicek `tools/pipa_gpt.py` + `scripts/preflight.sh`): tidak ada partisi yang ditulis,
slot A/B, `vbmeta`, `super`, `userdata`, OTA dan Recovery tidak tersentuh, reboot selalu kembali ke Android.

Batasan: menu hanya muncul jika dimulai dari PC; tidak ada menu saat cold boot; HakiOS tidak punya penyimpanan
permanen. Entri Recovery/Fastboot bergantung pada ABL membaca tombol saat warm reset — belum diuji.

## Mode 2 — menu saat tablet dinyalakan (belum, digerbang validator)

Butuh mengganti `boot` di slot **aktif** dengan U-Boot yang bisa memuat boot image Android stock (header v3/v4,
`vendor_boot`, AVB, bootconfig). Belum terbukti di pipa, sehingga `pipa_gpt.py check` memberi **BLOCKED** sampai
`android_fallback_tested` diisi setelah jalur Android lewat U-Boot terlihat bekerja dari RAM, dan **FAIL** tanpa
`backup_sha256` boot stock.

Ditolak oleh validator, apa pun isi rencananya:
- Slot inaktif (mis. `boot_b` saat aktif `a`): OTA virtual A/B memasang update di slot inaktif, jadi boot manager
  di sana tertimpa, dan Android bisa mem-boot image yang tidak ia verifikasi. "A untuk Android, B untuk iPadOS"
  tidak dipakai.
- Firmware/kalibrasi (`xbl`, `abl`, `tz`, `modem`, `persist`, `modemst*`, `fsg`, …) dan partisi milik Android
  (`super`, `userdata`, `metadata`, `vbmeta*`, `vendor_boot`, `dtbo`, `misc`, …).

Sebelum OTA di mode 2: flash ulang boot stock yang dibackup (dilakukan pemilik, bukan skrip).

## Penyimpanan

| Opsi | Keadaan |
| --- | --- |
| RAM saja | Sekarang. Aman; tidak ada yang tersimpan. |
| microSD | Tidak tersedia: Pad 6 tidak punya slot. |
| Drive USB-C (image APFS) | BLOCKED: HakiOS belum punya driver USB host untuk Darwin. |
| Partisi internal khusus | Biasanya `userdata` mengisi LUN sampai akhir, jadi ruang = mengecilkan `userdata` = **menghapus semua data Android** (juga enkripsi FBE/metadata). `pipa_gpt.py` memberi BLOCKED, lalu FAIL tanpa `userdata_erase_confirmed` + `backup_verified`. |
| File image di dalam `userdata` | Tidak layak: f2fs + FBE tidak bisa dibaca Darwin. |

Kapasitas nyata (ukuran `userdata`, ruang kosong, sektor 4096 byte, alignment 1 MiB) dibaca dari tablet:

```sh
scripts/dump-gpt.sh ~/pipa-gpt          # Android rooted, hanya membaca (dd if=/dev/block/sdX), salinan ke PC
python3 tools/pipa_gpt.py read ~/pipa-gpt/*.bin
python3 tools/pipa_gpt.py simulate plans/ram-boot.json ~/pipa-gpt/*.bin
```

## Instalasi mode 1 (saat tablet siap diuji)

1. Backup data penting (meski mode 1 tidak menulis apa pun).
2. `scripts/build.sh` lalu `scripts/build-uboot.sh` (butuh aarch64 gcc + flex).
3. Tablet ke fastboot (Vol- + Power). `scripts/preflight.sh --device --gpt ~/pipa-gpt` harus **PREFLIGHT PASS**
   (produk `pipa`, bootloader unlocked, tidak ada skrip yang menulis).
4. `fastboot boot build/hakios-pipa-bootmgr.img`. Catat apa yang tampil.
5. Pilih Android: harus kembali ke HyperOS dengan data utuh. Baru setelah itu coba HakiOS.

## Recovery plan

| Keadaan | Tindakan |
| --- | --- |
| Hang / layar hitam di U-Boot atau HakiOS | Tahan Power ±10–15 s → reboot ke Android (tidak ada yang ditulis). |
| Masuk fastboot | `fastboot reboot`. |
| Mode 2 bootloop | `fastboot flash boot_<slot aktif> <backup stock>` dengan image yang hash-nya sama dengan `backup_sha256`. |
| Android rusak | Fastboot ROM resmi yang **sama versinya** dengan yang terpasang, `flash_all_except_storage` (data tetap). Periksa `fastboot getvar anti` dulu: Xiaomi memakai anti-rollback; jangan flash versi lebih rendah. |
