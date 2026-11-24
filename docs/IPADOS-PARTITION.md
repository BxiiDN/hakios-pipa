# Partisi `ipados` — kebutuhan, pemeriksaan read-only, rancangan, backup dan pemulihan (sesi 13)

**Status: belum ada partisi `ipados`, dan belum ada satu pun tulisan ke GPT.** Dokumen ini rencana; setiap langkah yang
menulis ke tablet butuh persetujuan khusus pemilik, terpisah per langkah. `userdata` dan `metadata` tidak dikecilkan,
diformat, atau dihapus oleh apa pun di repo ini.

## 1. Yang sudah dibaca (read-only, tanpa root, tablet tetap di Android)

| Sumber | Hasil |
| --- | --- |
| `adb shell ls -l /dev/block/by-name` | 6 LUN UFS (`sda`–`sdf`), 124 nama. LUN 0 (`sda`): 34 partisi, `userdata` = `sda34` (nomor tertinggi), `metadata` = `sda18`, `super` = `sda29`. Slot aktif `_b` (`ro.boot.slot_suffix`). Pemetaan lengkap disimpan privat (`~/.hakios-private/gpt-sysfs.*`) |
| `/sys/block/*/size`, `/proc/partitions`, descriptor UFS (`geometry_descriptor`, `unit_descriptor/logical_block_count`) | **ditolak SELinux** untuk shell: ukuran LUN, offset, dan ruang kosong tidak terbaca |
| `dumpsys diskstats` | `/data` 236 722 156 KiB, terpakai 30 543 376 KiB (13 %); FBE aktif; partisi metadata 53 232 KiB |
| `board.toml` (pengukuran unit ini, Nov 2026) | `userdata` LBA 4 KiB `0x293000..0x3b037fa` (242,4 GB); awal sama dengan unit 128 GB → hanya ujungnya yang membesar |
| OTA resmi OS2.0.16, metadata partisi dinamis | grup `qti_dynamic_partitions` maks 9 122 611 200 B; isi 6 282 592 256 B → sisa ≈ 2,65 GiB di `super`, dipakai Virtual A/B saat OTA |

Kesimpulan sementara: `userdata` hampir pasti mengisi LUN 0 sampai `last_usable_lba`, jadi ruang kosong ≈ 0. **Belum
terbukti**: angka pastinya hanya ada di GPT (lihat 2).

Batasan yang mengikat rancangan (kode UniXNU-pipa):
- `RootLayout.h findRootLayout`: GPT dibaca dari **LUN 0** saja (`hostRead4k(0, …)`), ≤ 128 entri, LBA cadangan ≤ 2³²
  (READ(10)). Partisi `ipados` di LUN lain tidak terlihat oleh kernel.
- Nama harus persis `ipados` (`native-ufs-root-part=ipados`, patch `unixnu-pipa/0002`).

## 2. Pemeriksaan GPT semua LUN yang masih kurang — pembaca read-only dari RAM

Tanpa root, satu-satunya jalan membaca GPT adalah Linux kecil yang di-boot dari RAM: `package/gpt-reader`
(turunan pembaca log sesi 1, `11cd2f8`).

| Sifat | Bukti |
| --- | --- |
| Tiap disk `sdX`: node blok mode `r--`, `O_RDONLY`, `BLKROSET` sebelum baca pertama; disk tanpa `BLKROGET=1` dilewati tanpa dibaca | `init.c copy_gpt`, `tests/test_gpt_reader_source.py` |
| Yang dibaca: 6 sektor pertama (MBR pelindung, header primer, 4 sektor entri), 5 sektor terakhir (entri + header cadangan), ukuran dan ukuran sektor | idem |
| Yang ditulis: hanya image FAT di RAM (`/log.img`), pmsg/kmsg (RAM), file configfs gadget USB; mount hanya devtmpfs/sysfs/proc/configfs/pstore | idem (sumber setelah preprocessor) |
| Hasil disajikan sebagai disk USB read-only (`PIPALOG`), lalu tablet restart ke fastboot | `init.c start` |

Image: `~/hakios/gpt-reader.*/gpt-reader.img` (54 489 088 B, `a7fa37bb…`; kernel + DTB stock OS2.0.16, tidak di Git).
Analisis: `tools/gpt_capacity.py report LOG.BIN --out DIR` → per LUN: CRC primer/cadangan, salinan entri identik,
ukuran disk = LBA cadangan, ruang kosong, dan apakah partisi `ipados` muat; `DIR/sda.bin` langsung untuk
`tools/pipa_gpt.py check plans/ipados-*.json sda.bin`. Hasil dump juga **backup GPT** untuk pemulihan (bagian 6).

Langkah (butuh persetujuan pemilik karena tablet di-restart; tidak ada yang ditulis ke UFS):
1. Pemilik membawa tablet ke fastboot (`adb reboot bootloader`, atau Power + Vol−).
2. `fastboot getvar current-slot`, `fastboot getvar max-download-size` (read-only).
3. `fastboot boot gpt-reader.img` (RAM). Salin `LOG.BIN` dan `STATUS.TXT` dari drive `PIPALOG`, lalu eject.
4. Tablet kembali ke fastboot → `fastboot reboot` → Android, data utuh.

Risiko yang diketahui: ABL menolak image (pernah terjadi dengan DTB yang salah, 17 Nov) dan menandai slot `_b`
unbootable → pemulihan `fastboot set_active b` (perubahan atribut slot: persetujuan terpisah). Image ini memakai DTB
stock, seperti reader sesi 1 yang boot normal di unit ini.

## 3. Kebutuhan kapasitas (`tools/gpt_capacity.py need`)

Aturan `NativeUfs native_ufs_store_open` + `PersistOverlay.h`, blok 4 KiB:

| Bagian | Byte |
| --- | --- |
| Image root (objek OS + SystemOS, image sesi 1) | 9 457 106 944 |
| Guard setelah image | 4 194 304 |
| Jendela store Data (seed 8 GiB: 1 + 64 + 2 097 152 blok) | 8 590 200 832 |
| Reserve log (`sheng-log-reserve` 1024 MiB) | 1 073 741 824 |
| **Minimum** | **19 126 026 240 (17,81 GiB)** |

| Ukuran | Untuk |
| --- | --- |
| **20 GiB (disarankan, `plans/ipados-*.json`)** | minimum + 2,2 GiB sisa; Data iPadOS tetap 8 GiB (ditentukan seed `data.dbr`) |
| 48 GiB | bila kelak Data 32 GiB: butuh seed baru (macOS `hdiutil`), minimum 41,81 GiB |

Dampak ke Android pada rancangan B: `userdata` 242,4 GB → ±220,9 GB; pemakaian sekarang 31,3 GB.

## 4. Rancangan partisi

### A — tanpa menyentuh data (hanya bila ada ruang kosong ≥ 20 GiB di LUN 0)

- Satu entri GPT baru `ipados`, rata 1 MiB, di rentang yang tidak dipegang partisi mana pun; tidak ada partisi yang
  dipindah, diubah ukurannya, atau diformat. `plans/ipados-free-space.json`: `pipa_gpt.py check` = PASS hanya bila
  ruangnya ada (tes: 0 dan 19 GiB → BLOCKED, 24 GiB → PASS).
- Penulisan: GPT primer + cadangan LUN 0 baru, dibangun offline dari dump pembaca, CRC dihitung ulang, entri lain
  byte-identik. ABL punya jalur tulis GPT (`fastboot flash partition:0`; string "Failed to write Gpt partition",
  "Gpt Image size is invalid") dan menolak "Critical Partitions" bila perangkat tidak critical-unlocked — status
  itu belum dibaca. **Alat tulisnya sengaja belum dibuat.**

### B — mengecilkan `userdata` (DILARANG tanpa persetujuan khusus; menghapus data Android)

- Ujung `userdata` turun 20 GiB, `ipados` mengisi ruang itu. `userdata` adalah f2fs di atas dm-default-key
  (enkripsi metadata, kunci terikat keystore perangkat): f2fs tidak bisa dikecilkan online, dan offline tanpa kunci
  perangkat isinya ciphertext. Jadi B = **format `userdata` + `metadata`**, Android first boot, lalu pulihkan backup.
- `plans/ipados-shrink-userdata.json`: `pipa_gpt.py check` = **FAIL** selama `userdata_erase_confirmed` dan
  `backup_verified` tidak keduanya `true`; file di repo menyimpan keduanya `false` (dites).

Yang tidak dipilih: partisi di LUN 1–5 (tidak terlihat kernel), `super` (sisa 2,65 GiB, milik OTA), partisi kecil
Xiaomi (`rawdump`, `cust`, `rescue`, `bk0x`), file di `userdata` (ciphertext), USB-C (tidak ada driver host).

## 5. Rencana backup (sebelum rancangan apa pun yang menulis)

| Apa | Cara tanpa root | Verifikasi |
| --- | --- | --- |
| Aplikasi + datanya | Backup & restore bawaan HyperOS (cadangan lokal) → `/sdcard/MIUI/backup/AllBackup/…`, lalu salin ke PC | pulihkan satu aplikasi uji dari cadangan itu sebelum langkah tulis |
| Penyimpanan internal (foto, dokumen, unduhan; ±31 GB) | `adb pull /sdcard/` ke PC (ruang kosong WSL 768 GB) | daftar file + SHA-256 di PC, dibandingkan ulang |
| Akun & sinkronisasi | Google / Mi Cloud | login uji di perangkat lain |
| Aplikasi dengan kunci sendiri (2FA, bank, chat) | ekspor/backup milik aplikasi itu (contoh: cadangan WhatsApp, kode pemulihan authenticator) | dicatat pemilik |
| GPT semua LUN | dump pembaca (bagian 2): primer + cadangan per LUN | `gpt_capacity.py`: CRC dan salinan entri |
| Boot chain versi terpasang | ROM fastboot resmi **OS4.0.8.0.XPZCNXM** (versi sama dengan yang terpasang), MD5 resmi; `fastboot getvar anti` dicatat | MD5 cocok |

Catatan: Persetujuan 16 Nov ("tanpa backup, jangan salin /sdcard") berlaku untuk instalasi lama dan **tidak** dipakai
lagi: sekarang data Android harus aman, jadi backup di atas dijalankan pemilik (atau dengan persetujuannya).

## 6. Pemulihan Android

| Kejadian | Pemulihan | Data |
| --- | --- | --- |
| Pembaca GPT ditolak ABL | `fastboot set_active b` (dengan persetujuan), `fastboot reboot` | utuh |
| GPT baru (A) salah / Android tidak boot | tulis kembali GPT dari dump pembaca (`partition:0`), `fastboot reboot` | utuh (A tidak menyentuh isi partisi) |
| B: Android tidak boot setelah format | `flash_all` ROM fastboot OS4.0.8.0 (menghapus data) lalu pulihkan backup | dari backup |
| Boot partition (MODE B) rusak | `fastboot flash boot_b` image stock OS4.0.8.0 dari ROM yang sama | utuh |
| Fastboot sendiri | ABL di partisinya sendiri, tidak pernah ditulis repo ini (`pipa_gpt.py` menolak semua partisi firmware) | — |

## 7. Gerbang persetujuan (berurutan, masing-masing eksplisit)

1. RAM-boot pembaca GPT (bagian 2). Tidak menulis UFS.
2. Bila A memungkinkan: membuat dan menulis GPT LUN 0 dengan entri `ipados`, setelah backup GPT ada.
3. Bila tidak: keputusan pemilik tentang B, **setelah** backup bagian 5 selesai dan satu pemulihan uji berhasil.
4. Menulis image root ke `ipados` (driver menolak jendela tulis pada partisi bernama `userdata`).
