# Partisi `ipados` — kebutuhan, pemeriksaan read-only, rancangan, backup dan pemulihan (sesi 13–21)

**Status (24 Nov, terukur di tablet): LUN 0 tidak punya ruang kosong; Rancangan A tidak mungkin. Belum ada partisi `ipados`, dan belum ada satu pun tulisan ke GPT.** Dokumen ini rencana; setiap langkah yang
menulis ke tablet butuh persetujuan khusus pemilik, terpisah per langkah. `userdata` dan `metadata` tidak dikecilkan,
diformat, atau dihapus oleh apa pun di repo ini.

## 1. Yang sudah dibaca (read-only, tanpa root, tablet tetap di Android)

| Sumber | Hasil |
| --- | --- |
| `adb shell ls -l /dev/block/by-name` | 6 LUN UFS (`sda`–`sdf`), 124 nama. LUN 0 (`sda`): 34 partisi, `userdata` = `sda34` (nomor tertinggi), `metadata` = `sda18`, `super` = `sda29`. Slot aktif `_b` (`ro.boot.slot_suffix`). Pemetaan lengkap disimpan privat (`~/.hakios-private/gpt-sysfs.*`) |
| `/sys/block/*/size`, `/proc/partitions`, descriptor UFS (`geometry_descriptor`, `unit_descriptor/logical_block_count`) | **ditolak SELinux** untuk shell: ukuran LUN, offset, dan ruang kosong tidak terbaca |
| `dumpsys diskstats` | ukuran `/data` cocok dengan `userdata`; FBE aktif (pemakaian data tidak dicatat di repo) |
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
| Hasil disajikan sebagai disk USB read-only (`PIPALOG`); setelah di-eject (atau 60 s), pembaca **mematikan tablet begitu kabel USB dicabut** (maks. 600 s); tidak ada restart ke fastboot | `init.c start`, `test_gpt_reader_source.py` |

Image sesi 13 `~/hakios/gpt-reader.*/gpt-reader.img` (`a7fa37bb…`, kernel 4.19 OS2.0.16) **tidak boleh dipakai** (bagian 8, `DO-NOT-USE.txt`). Image yang sah hanya dibangun dari boot/vendor_boot ROM terpasang dan harus lulus `tools/rom_match.py`; jalur lain: plugin UEFI (bagian 9).
Analisis: `tools/gpt_capacity.py report LOG.BIN --out DIR` → per LUN: CRC primer/cadangan, salinan entri identik,
ukuran disk = LBA cadangan, ruang kosong, dan apakah partisi `ipados` muat; `DIR/sda.bin` langsung untuk
`tools/pipa_gpt.py check plans/ipados-*.json sda.bin`. Hasil dump juga **backup GPT** untuk pemulihan (bagian 6).

Langkah (butuh persetujuan pemilik karena tablet di-restart; tidak ada yang ditulis ke UFS):
1. Pemilik membawa tablet ke fastboot (`adb reboot bootloader`, atau Power + Vol−).
2. `fastboot getvar current-slot`, `fastboot getvar max-download-size` (read-only).
3. `fastboot boot gpt-reader.img` (RAM). Salin `LOG.BIN` dan `STATUS.TXT` dari drive `PIPALOG`, lalu eject.
4. Cabut kabel USB → pembaca mematikan tablet → pemilik menyalakan dengan Power → Android, data utuh. **Tidak** memakai
   `fastboot reboot` (pada ROM port ini tablet macet di logo setelahnya; pemulihan: tahan Power 15–20 s).

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

Dampak ke Android pada rancangan B: `userdata` 242,4 GB → ±220,9 GB (pemakaian saat ini dicatat privat, jauh di bawah itu).

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
| Penyimpanan internal (foto, dokumen, unduhan) | `adb pull /sdcard/` ke PC (cek ruang kosong PC dulu) | daftar file + SHA-256 di PC, dibandingkan ulang |
| Akun & sinkronisasi | Google / Mi Cloud | login uji di perangkat lain |
| Aplikasi dengan kunci sendiri (2FA, bank, chat) | ekspor/backup milik aplikasi itu (contoh: cadangan WhatsApp, kode pemulihan authenticator) | dicatat pemilik |
| GPT semua LUN | dump pembaca (bagian 2): primer + cadangan per LUN | `gpt_capacity.py`: CRC dan salinan entri |
| Boot chain versi terpasang | ROM fastboot resmi **OS4.0.8.0.XPZCNXM** (versi sama dengan yang terpasang), MD5 resmi; `fastboot getvar anti` dicatat | MD5 cocok |

Catatan: Persetujuan 16 Nov ("tanpa backup, jangan salin /sdcard") berlaku untuk instalasi lama dan **tidak** dipakai
lagi: sekarang data Android harus aman, jadi backup di atas dijalankan pemilik (atau dengan persetujuannya).

## 6. Pemulihan Android

| Kejadian | Pemulihan | Data |
| --- | --- | --- |
| Pembaca GPT ditolak ABL | `fastboot set_active b` (dengan persetujuan), lalu tahan Power 15–20 s / nyalakan biasa (bukan `fastboot reboot`) | utuh |
| GPT baru (A) salah / Android tidak boot | tulis kembali GPT dari dump pembaca (`partition:0`), lalu nyalakan ulang dengan Power | utuh (A tidak menyentuh isi partisi) |
| B: Android tidak boot setelah format | `flash_all` ROM fastboot OS4.0.8.0 (menghapus data) lalu pulihkan backup | dari backup |
| Boot partition (MODE B) rusak | `fastboot flash boot_b` image stock OS4.0.8.0 dari ROM yang sama | utuh |
| Fastboot sendiri | ABL di partisinya sendiri, tidak pernah ditulis repo ini (`pipa_gpt.py` menolak semua partisi firmware) | — |

## 7. Gerbang persetujuan (berurutan, masing-masing eksplisit)

1. RAM-boot pembaca GPT (bagian 2). Tidak menulis UFS.
2. Bila A memungkinkan: membuat dan menulis GPT LUN 0 dengan entri `ipados`, setelah backup GPT ada.
3. Bila tidak: keputusan pemilik tentang B, **setelah** backup bagian 5 selesai dan satu pemulihan uji berhasil.
4. Menulis image root ke `ipados` (driver menolak jendela tulis pada partisi bernama `userdata`).

## 8. Sesi 14: preflight pembaca terhadap ROM yang terpasang

### ROM terpasang (adb + `fastboot getvar`, read-only; data mentah di `~/.hakios-private`, tidak di Git)

| Fakta | Nilai |
| --- | --- |
| ROM | custom/port dari Xiaomi Pad 8/8 Pro (keterangan pemilik); `OS4.0.8.0.XPZCNXM`, Android 17; tidak ada rilis resmi pipa dengan versi ini |
| Kernel | **koreksi sesi 18:** `4.19.325-cip136-st20-N0-kernel++` (`/proc/version`); `uname -r` 5.10.241 adalah spoof. Tercatat semula: `5.10.241 #18 SMP PREEMPT Thu Oct 29 19:56:25 CST 2026` (`ro.kernel.version` tetap `4.19`); `CONFIG_IKCONFIG_PROC=y` |
| Driver yang dibutuhkan pembaca | built-in: UFS QCOM, configfs, mass storage gadget, initrd gzip/lz4, pstore/ramoops, msm_poweroff; `CONFIG_DEVTMPFS` tidak ada (pembaca membuat node sendiri) |
| Boot | `ro.boot.dtb_idx=0`, `ro.boot.dtbo_idx=9`, `verifiedbootstate=orange`, `ro.boot.vbmeta.digest` kosong (AVB tidak bisa menjamin image) |
| Slot | `current-slot:b`; b: successful=yes, unbootable=no, retry 6; **a: successful=no** (bukan cadangan yang terbukti) |
| Fastboot | `max-download-size` 805 306 368; `anti:1`; `unlocked:yes`; `snapshot-update-status:none` |
| Data | pemakaian `/data` sama sebelum dan sesudah pemulihan (angka disimpan privat) |

### Kejadian `fastboot reboot` (24 Nov)

`adb reboot bootloader` → `getvar all` → `fastboot reboot`: tablet berhenti di logo, pulih dengan menahan Power 15–20 s
(reset PMIC), lalu boot normal; `persist.sys.boot.reason.history` = `bootloader,…`. Tidak ada `SYSTEM_LAST_KMSG`,
`SYSTEM_RESTART`, atau log kernel awal yang tersisa, jadi **penyebabnya tidak terbukti**. Fakta: dua reboot dari Android
(`reboot,userrequested`) normal; yang macet hanya restart dari mode fastboot ABL. Konsekuensi: alur uji tidak lagi
diakhiri `fastboot reboot`; pembaca kini mematikan tablet setelah kabel USB dicabut, lalu pemilik menyalakan dengan Power.

### Preflight image pembaca lama: TIDAK LULUS

Image `a7fa37bb…` memakai kernel 4.19 dan DTB dasar kona OS2.0.16 (`board-id <0 0>`): ABL wajib menerapkan `dtbo_b` ROM
port (dari ROM lain, bukan pasangan DTB dasar OS2.0.16) dan, bila overlay gagal, menghentikan boot (ABL `.text 0x17394`). Ditandai
`DO-NOT-USE.txt`, tidak dihapus. `tools/rom_match.py` menolaknya (banner, uname -v, config tertanam).

### Pembaca yang disesuaikan (offline, siap begitu image ROM port ada)

- `build-gpt-reader.py` menerima boot/vendor_boot **v3 dan v4**, menyimpan kernel dan DTB **byte-identik** (tanpa edit
  warm-reboot), dan **menolak membangun** kecuali `tools/rom_match.py` PASS terhadap `/proc/config.gz`, `uname -r`,
  `uname -v` tablet. Dengan kernel + DTB milik ROM sendiri, ABL menerapkan `dtbo_b` miliknya sendiri, sama seperti boot
  normal.
- Init berakhir dengan power-off (setelah kabel dicabut), bukan restart ke fastboot.
- Tes: `test_rom_match.py` (7), `test_gpt_reader_build.py` (v4 ujung-ke-ujung), `test_gpt_reader_source.py` (6).

Sumber image yang benar: **paket ROM port yang dulu di-flash pemilik** (`boot.img`, `vendor_boot.img`, `dtbo.img`). Image
versi lain hanya dipakai bila `rom_match.py` PASS. Paket yang sama sekaligus jadi backup pemulihan `boot_b`/`vendor_boot_b`/
`dtbo_b` lewat fastboot.

### Jalur alternatif tanpa image ROM port (belum dibuat)

`pipa.dtb` uefi-pipa khusus papan (`msm-id 0x164/0x20001`, `board-id 0x34`); bila ABL menganggapnya "Exact DTB match", ABL
melewati dtbo, dan firmware MODE A tidak bergantung pada kernel/dtbo ROM port (image MODE A sudah boot di unit ini di
bawah ROM sebelumnya). Firmware itu punya UFS lewat UEFI dan menu Tools berbasis plugin (`UniXNUMenuPlugin.h`): sebuah
plugin read-only bisa menampilkan GPT LUN 0 (ukuran LUN, partisi terakhir, ruang kosong) di layar. Butuh plugin baru +
build firmware + persetujuan RAM-boot.

### Apakah ROM custom ini bisa dipertahankan untuk dual boot?

| Bagian | Bergantung pada ROM Android? | Penilaian |
| --- | --- | --- |
| iPadOS (kernel tahap B, payload, GPU addon, DarwinBoot) | tidak: jalan dari firmware sendiri, DTB `pipa.dtb` | tetap |
| MODE A (`fastboot boot`) | hampir tidak (DTB khusus papan); `dtbo_b` port belum terbukti dilewati | uji RAM diperlukan |
| B5 (menu di `boot_b`) | ya: shim masuk ke kernel port (4.19.325); pemilih `bootargs` cocok dengan ABL OS2.0.16 (tanpa bootconfig) | layak, tapi butuh `boot.img` port asli dan diulang tiap update ROM port |
| Partisi `ipados` | tidak (GPT) | masalah ruang tetap sama |
| Pemulihan | ya: tanpa paket ROM port tidak ada image `boot_b` untuk dipulihkan | **blocker** |

## 9. Sesi 15: pencarian image ROM port dan plugin UEFI "GPT (read only)"

### Pencarian image ROM terpasang (read-only)

Dicari di `C:\Users\<user>` (Downloads, Desktop, Documents, `pipa-flash`), drive D:/E:/F: dan home WSL: arsip
(zip/7z/rar/tgz/tar), `payload.bin`, `super*.img`, nama berisi pipa/HyperOS/OS4/XPZ/Pad 8, dan semua `*.img` 8–256 MiB
diperiksa magic `ANDROID!` serta banner kernelnya. Hasil:

| Temuan | Isi | Cocok dengan ROM terpasang? |
| --- | --- | --- |
| `Downloads\boot.img`, `vendor_boot.img`, `dtbo.img` (19 Nov 06:58, ukuran = partisi: dump) | boot v3, kernel **4.19.325-perf+**; vendor_boot 3 DTB (`msm-id 0x164`); dtbo 13 entri | **Tidak**: `rom_match.py` FAIL (banner, `uname -v`, config tertanam). Kemungkinan dump ROM custom sebelumnya |
| Paket ROM port | — | tidak ditemukan saat itu; ditemukan sesi 18 (`HyperOS4.0_pipa_port-from-yupei-beta`) |

Salinan privat (tidak di Git): `~/.hakios-private/port-rom-downloads.*` (SHA-256 sama dengan aslinya: `56a71abe…`,
`6dabbe97…`, `fbbe0fab…`). File itu **bukan** salinan pemulihan untuk ROM sekarang; jangan di-flash.

### Plugin UEFI (patch `unixnu/0007`, `uefi-pipa/0001`)

Karena image ROM port tidak ada, pembacaan GPT dipindah ke firmware MODE A sendiri: entri Tools → **"GPT (read only)"**.

| Sifat | Bukti |
| --- | --- |
| Hanya `EFI_BLOCK_IO_PROTOCOL.ReadBlocks`: header primer (LBA 1), array entri, header cadangan (LBA terakhir), pada disk utuh (`LogicalPartition = FALSE`) | `GptViewDxe.c`; `test_gpt_view.py` menolak `WriteBlocks`, `FlushBlocks`, `DiskIo`, `SimpleFileSystem`, `EraseBlocks`, `SetVariable`, `ResetSystem`; INF hanya BlockIo + protokol plugin; biner: GUID BlockIo ada, BlockIo2/DiskIo/SimpleFileSystem tidak |
| Logika (`GptScan.c`): CRC header dan entri, geometri, salinan cadangan, tumpang tindih, ruang kosong, partisi terakhir, `userdata`/`ipados` | 10 tes host: file dari patch dikompilasi `-DGPT_SCAN_HOST`, hasil = `pipa_gpt.py` (partisi, jumlah/terbesar ruang kosong) |
| LUN 0 = disk yang memuat `userdata` (seperti `sda34` di Android); ditampilkan lengkap, disk lain satu baris; baris juga ke log (`GPTVIEW:`) | `GptViewDxe.c` |
| Kesimpulan di layar: `DESIGN A FITS` / `no room without resizing userdata` / `UNKNOWN (table not sound)` terhadap 19 126 026 240 B | sama dengan `gpt_capacity.py need` (dites) |
| Build lokal | firmware PASS; `GptViewDxe.efi` 27 648 B di FVMAIN; FV terkompresi 0x195a40/0x300000; FD `bf7e98f0…` (FD sebelumnya `bd39c37a…` disimpan di `~/hakios/fd-baseline.*`) |
| Image MODE A uji (payload v5, FD baru) | `~/hakios/payload-v6-gptview.*/…/boot.img` `a8d40a90…` 120 248 320 B: IMAGE CONSISTENT, ABL LAYOUT PASS, menu: default Android, entri Tools ada. **Belum dijalankan di tablet** |

Rencana uji (butuh persetujuan terpisah; tidak menulis UFS): `fastboot boot` image itu → menu → Tools → GPT (read
only) → foto layar → kembali → **Power off** dari menu (bukan Restart/`fastboot reboot`) → nyalakan dengan Power →
Android. Risiko yang tersisa: `pipa.dtb` khusus papan (`board-id 0x34`) diharapkan "Exact DTB match" sehingga `dtbo_b`
port dilewati — belum dibuktikan pada ROM port ini; bila ABL menolak, pemulihannya seperti bagian 6.

## 10. Sesi 16: GPT LUN 0 terbaca di hardware nyata

### Bukti (plugin "GPT (read only)", `fastboot boot` image `a8d40a90…`, 24 Nov; foto di tangan pemilik)

| Baris di layar | Nilai |
| --- | --- |
| LUN 0 | 241 720 MiB, blok 4096 B, 34 partisi |
| Usable LBA | 6..61 880 314 |
| Partisi terakhir | `userdata`, berakhir di LBA 61 880 314 |
| Ruang kosong | 0 MiB |
| Pemeriksaan | entri OK, cadangan OK, tidak ada tumpang tindih |
| `ipados` | tidak ada; butuh 18 240 MiB → **no room without resizing userdata** |

Pemeriksaan silang (`tests/test_measured_lun0.py`, tata letak `tests/data/pipa-lun0-layout.json`): urutan `by-name` +
ukuran `fastboot getvar partition-size` dari LBA 6 tanpa celah menempatkan `userdata` tepat di `0x293000..0x3b037fa`
(= `board.toml`, diukur 16 Nov) dan jumlah 34 partisi = 241 720,0 MiB = seluruh area usable. Tiga sumber independen
(GPT di firmware, `getvar`, rekaman lama) sepakat. Setelah uji: slot `b` successful=yes, unbootable=no, retry 6.

**Rancangan A: tidak mungkin** (`pipa_gpt.py check` → BLOCKED pada tabel ini).

### Alternatif tanpa menghapus data Android (audit)

| Alternatif | Kapasitas / syarat | Penilaian |
| --- | --- | --- |
| Ruang kosong GPT LUN 0 | 0 MiB (terukur) | tidak |
| Partisi kecil yang mungkin tak terpakai (`rawdump` 128, `cust` 1024, `rescue` 128, `minidump` 96, `logdump` 64, `bk0x` ±90 MiB) | jumlah < 2 GiB, tidak bersebelahan, sebagian dipakai Xiaomi | tidak |
| `super` | 8 704 MiB total, berisi Android (partisi dinamis + Virtual A/B) | tidak |
| LUN 1–5 | kecil (partisi boot/firmware); kernel hanya membaca LUN 0 (`findRootLayout`) | tidak |
| File di `/data` | f2fs di atas dm-default-key (kunci terikat TEE): blok mentah ciphertext bagi XNU | tidak |
| Kecilkan root (seed Data lebih kecil, butuh macOS) | root 9,46 GB tetap butuh ruang yang tidak ada | tidak membantu |
| Root di RAM | 8 GB RAM < root 9,46 GB | tidak |
| Kecilkan f2fs `userdata` di tempat | tidak ada alat yang bisa: f2fs tidak menyusut online; offline butuh kunci metadata perangkat (hanya vold Android) | tidak |
| **Drive USB-C eksternal** | kernelcache iPadOS membawa tumpukan USB host Apple; DWC3 SM8250 punya mode host xHCI; port ini hanya punya gadget (diagnostik). Butuh: mode host + PHY + VBUS (PMIC), node ADT, pengikatan driver XHCI, lalu root di drive; tablet harus memakai drive (dan hub berdaya) setiap boot iPadOS | **satu-satunya jalan tanpa hapus data**; riset besar, belum ada bukti kelayakan |

Kesimpulan: dengan perangkat ini sekarang, root iPadOS internal **hanya** bisa lewat Rancangan B (mengecilkan
`userdata` = format `userdata` + `metadata`). Jalan tanpa kehilangan data hanya drive USB-C, sebagai proyek riset.

### Rancangan B, angka untuk tabel ini (tidak ditulis)

`ipados` = LBA 56 637 184..61 880 314 (rata 1 MiB, 21 475 864 576 B ≥ 19 126 026 240); `userdata` = 0x293000..56 637 183
(220,93 GB untuk Android). Hanya dua entri GPT berubah; partisi lain tidak bergeser.

### Prasyarat sebelum Rancangan B boleh diusulkan untuk disetujui (semua belum terpenuhi)

| # | Prasyarat | Alat / status |
| --- | --- | --- |
| 1 | Backup data pengguna di PC, terverifikasi | `scripts/backup-android.sh backup DIR` lalu `verify DIR` (disiapkan, **belum dijalankan**: butuh persetujuan karena menyalin data pribadi); ditambah backup HyperOS bawaan (masuk lewat `/sdcard`), Google/Mi Cloud, ekspor tiap aplikasi (chat, authenticator) |
| 2 | Uji pulih satu kali | pulihkan satu aplikasi dari backup HyperOS + buka beberapa file dari salinan PC |
| 3 | Paket ROM port yang terpasang (`boot`, `vendor_boot`, `dtbo`, `vbmeta*`, `super`/image partisi) | **tidak ada** di mesin ini: harus didapat dari porter; tanpa itu Android tidak bisa dipasang ulang bila first boot setelah format gagal |
| 4 | Dump GPT mentah LUN 0 (primer + cadangan) untuk mengembalikan tabel | plugin hanya menampilkan; perlu fitur ekspor read-only (mis. QR, seperti plugin Advanced Logger) — belum dibuat |
| 5 | Alat penulis GPT yang hanya mengubah dua entri dan dicek ulang byte demi byte | belum dibuat (sengaja) |
| 6 | Persetujuan pemilik: `userdata_erase_confirmed` dan `backup_verified` | `pipa_gpt.py` tetap FAIL sampai keduanya |

Pemulihan bila B gagal: GPT lama dari dump (#4) lewat `fastboot flash partition:0`, lalu format `userdata` dan
first boot Android dengan ROM port yang sama (#3), lalu pulihkan backup (#1). Fastboot (ABL) tidak tersentuh oleh semua
langkah ini.

## 11. Sesi 17: persiapan Rancangan B (belum ada persetujuan mengubah data)

### Prasyarat, diperiksa alat (`tools/design_b_readiness.py`; hari ini: **NOT READY**)

| # | Prasyarat | Status | Yang dibutuhkan |
| --- | --- | --- | --- |
| 1 | Backup terverifikasi | MISSING | persetujuan pemilik untuk `scripts/backup-android.sh backup ~/android-backup-…` (layar di-unlock, baterai ≥ 50 %) |
| 2 | Uji pulih | MISSING | pemilik memulihkan satu aplikasi/berkas, mencatat `result: OK` |
| 3 | Paket ROM port terpasang | MISSING | dari porter: boot/vendor_boot/dtbo (lulus `rom_match.py`), vbmeta/vbmeta_system, super atau image partisinya |
| 4 | Dump GPT LUN 0 | MISSING | jalankan Tools → "GPT export (QR)" (butuh persetujuan RAM-boot) dan terima dengan OneSend; `gpt_export_decode.py` |
| 5 | Penulis GPT | MISSING (sengaja) | dibuat setelah 1–4 |
| 6 | Persetujuan | BLOCKED | `userdata_erase_confirmed` + `backup_verified` |

### Backup (`scripts/backup-android.sh`, diaudit dan diperbaiki)

- `adb` di sini adalah `adb.exe` Windows: path PC sekarang selalu `wslpath -w` (dulu path Linux hanya kebetulan jalan
  dari direktori kerja di UNC WSL). Diuji pada file sistem non-pribadi: hash tablet = hash PC (`1a7eccd7…`), 37 MB/s.
- Setiap file `/sdcard` dan setiap split APK di-hash **di tablet** (`sha256sum` toybox, read-only) dan di PC, lalu
  dibandingkan; file 0 byte dari pull yang gagal tertangkap. `verify` memeriksa keutuhan dan kelengkapan.
- `plan` (preflight tanpa menyalin), `restore-plan` (hanya mencetak `adb push` / `adb install-multiple`).
- Menolak direktori di repo dan di drive Windows (`/mnt/*`, NTFS menolak sebagian nama berkas Android).
- Menolak bila penyimpanan pengguna masih terkunci: pada 24 Nov user 0 `RUNNING_LOCKED` (layar belum di-unlock sejak
  restart) → `/sdcard` tidak terpasang untuk adb. `need_android` juga diperbaiki (CRLF `adb.exe`: `device\r`).
- 7 tes dengan adb palsu (`tests/test_backup_android.py`).
- Tidak tercakup oleh adb tanpa root: data privat aplikasi, akun, SMS/log panggilan, kunci Wi-Fi → backup HyperOS
  bawaan (arsipnya ikut lewat `/sdcard/MIUI/backup`), Google/Mi Cloud, ekspor milik aplikasi.

### Ekspor GPT LUN 0 (plugin "GPT export (QR)", `patches/unixnu/0007`)

- Hanya `ReadBlocks`: LBA 0..5 (MBR pelindung, header + entri primer) dan 5 LBA terakhir (entri + header cadangan) dari
  disk yang memuat `userdata`. Wadah `HKGPT1` (CRC32) dalam amplop `LMS1` dan frame OneSend `OS` 720 B — format yang
  sama dengan plugin Advanced Logger UniXNU — sebagai 63 QR yang berputar; diterima aplikasi OneSend di ponsel lain
  (`UniXNU docs/porting/log-capture.md`) sebagai `pipa-lun0-gpt.hkgpt`.
- `tools/gpt_export_decode.py`: menerima wadah, amplop, atau frame mentah (urutan bebas, berulang boleh), memeriksa
  semua CRC, GPT primer dan cadangan, menulis `head.bin`/`tail.bin` (sektor persis untuk pemulihan) dan `sda.bin`.
- Tes (`test_gpt_export.py`, 5): kode C pengekspor dari patch → frame → dekoder = byte-identik dengan LUN 0 terukur;
  frame hilang/rusak ditolak; cadangan rusak dilaporkan.
- Build lokal: driver 47 616 B (dua plugin), FV 0x197ba8/0x300000, FD `5d7a523f…`; image MODE A
  `~/hakios/payload-v7-gptexport.*/…/boot.img` `9c100b1d…` 120 258 560 B: IMAGE CONSISTENT, ABL LAYOUT PASS.
  **Belum dijalankan.**

### Rencana pemulihan Android untuk Rancangan B (urutan bila kelak disetujui)

1. Semua prasyarat 1–4 PASS; baterai ≥ 80 % dan diisi; `fastboot getvar current-slot` terbaca.
2. **Tulis GPT baru saja** (penulis #5): hanya ujung `userdata` turun ke LBA 56 637 183 dan entri `ipados`
   56 637 184..61 880 314 ditambah. Isi `userdata` belum disentuh.
   - Gagal / Android tidak mau mount (f2fs lebih besar dari partisinya — diharapkan): tulis kembali `head.bin`/`tail.bin`
     dari #4 → tabel lama → **data Android utuh** (belum ada yang ditulis di wilayah `ipados`). Titik balik terakhir.
3. Format `userdata` + `metadata` (enkripsi metadata terikat kunci baru) → first boot Android dengan ROM yang sama.
   - Android tidak boot: flash ulang paket ROM port #3, format lagi, first boot.
4. Pulihkan: backup HyperOS bawaan, lalu `backup-android.sh restore-plan` (berkas, aplikasi), lalu cloud/ekspor aplikasi.
5. Baru kemudian image root iPadOS ditulis ke `ipados` (driver menolak jendela tulis pada `userdata`).

Fastboot (ABL) tidak tersentuh di langkah mana pun. Belum diketahui: apakah ABL mengizinkan `fastboot flash partition:0`
tanpa critical-unlock pada perangkat ini (string ABL: "Flashing is not allowed for Critical Partitions") — dibaca
dengan `getvar` sebelum #5 dibuat.

## 12. Sesi 18–19: set pemulihan, alat USB read-only, penulis GPT

### Set pemulihan ROM terpasang

- Paket porter `HyperOS4.0_pipa_port-from-yupei-beta` (salinan privat + SHA-256): `boot`/`vendor_boot`/`dtbo`/`vbmeta`/
  `vbmeta_system` dan `super.img` sparse yang mengembang tepat ke 9 126 805 504 B (liblp, `system/system_ext/product/
  vendor/odm` a/b). Skrip porter (`FlashLinux.sh`) memakai `set_active b`, flash firmware `*_ab`, `super`, opsional erase
  `metadata`/`userdata` — tidak menulis GPT.
- `boot.img` paket = kernel ROM `4.19.325-cip135-st19`; terpasang `cip136-st20-N0-kernel++` (config tertanam sama, build
  lain). Pemulihan dengan paket menghidupkan Android dengan kernel ROM; kernel N0 harus dipasang ulang dari paketnya sendiri
  (tidak ditemukan di PC) — atau `boot_b` yang terpasang diambil persis lewat alat USB di bawah.

### Alat USB read-only (Tools di firmware MODE A, `patches/unixnu/0007`)

"USB disk: LUN 0 (read only)" / "USB disk: boot LUN (read only)": disk (dicari dari nama partisi `userdata` / `boot_b`)
diserahkan ke `UsbMsdDxe` lewat BlockIo pembungkus: `ReadBlocks` diteruskan, `WriteBlocks` = `EFI_WRITE_PROTECTED`,
`Media->ReadOnly = TRUE`; tidak ada panggilan tulis/flush ke disk (`test_gpt_view.py`). Di PC (Administrator):
`scripts/windows/dump-pipa-usb.ps1` (disk dibuka `FileAccess.Read`, hanya BusType USB): boot LUN utuh (±2 GiB) dan
LUN 0 dari byte 0 sampai awal `userdata` (±10,3 GiB: GPT, `super`, `persist`, …) + 5 sektor terakhir. Lalu
`tools/usb_dump_check.py` memeriksa SHA-256, kedua GPT, tata letak terukur, `super` liblp, dan `rom_match.py` → `recovery/`.

### Penulis GPT (`tools/gpt_rewrite.py`, hanya berkas)

Dari sektor GPT asli: `userdata` berakhir di 56 637 183, entri `ipados` 56 637 184..61 880 314 (tipe APFS, GUID uuid5
dari GUID disk), CRC entri + kedua header dihitung ulang. Bukti di alat: kedua GPT baru sah, cadangan = primer, dan setiap
byte berbeda berada di ujung `userdata`, slot entri baru, atau field CRC (53 byte per salinan pada LUN 0 terukur);
MBR pelindung wajib `55 AA` + tipe `0xEE` (pemeriksaan ABL `.text 0x28140`, yang juga meminta ukuran > 2 blok dan header
di blok 1 — tata letak `gpt_both0.bin` = sektor primer + sektor cadangan). 6 tes. `image_root_check.py` pada image MODE A:
GPT sekarang → BLOCKED (tidak ada `ipados`), GPT baru → PASS.

### Image root iPadOS

`userdata-root.img` 9 457 106 944 B, SHA-256 `f7c29dc9…` = catatannya; objek `OS.vroot`/`SystemOS.vroot` = kebijakan
`policy.json` (`95e446dc…`) dan kunci owner (`e8ae7ddf…`) yang tertanam di kernel tahap B `1d02cbe8…`. Muat di
`ipados` (21,48 GB). Akan di-flash ke `ipados` (sparse FILL), bukan ke `userdata`.

### Yang masih terbuka untuk iPadOS (bukan Android)

Patch `0002` mematikan `sheng-data-persist=2` dan entri Install karena dulu store Data ada di `userdata`. Dengan root di
`ipados`, store ada di ujung `ipados` (driver menolak `userdata`), jadi keduanya boleh kembali — tetapi cmdline payload
sudah 974 dari ±1000 byte: `sheng-data-persist=2` (21 B) muat, entri inisialisasi Data sekali (`sheng-data-reset=1`) tidak
tanpa membuang argumen diagnostik. Tanpa ini iPadOS boot dengan Data volatil (tidak tersimpan). Keputusan + uji hardware.

## 13. Sesi 20: Data iPadOS persisten, critical unlock, verifikasi menyeluruh, preflight RAM-boot

### Data iPadOS persisten (`unixnu-pipa/0013`)

`sheng-data-persist=2` kembali dan entri menu **"Initialise iPadOS Data (first boot)"** (konfirmasi: `sheng-data-reset=1`
atau `=2`). Batas XNU sebenarnya 1023 karakter (`BOOT_LINE_LENGTH 1024`, DarwinBoot menyalin paling banyak itu), bukan
±1000: entri iPadOS 995, entri inisialisasi 1014 — **tidak ada argumen diagnostik yang perlu dibuang**
(`tools/cmdline_budget.py` pada payload v10). Pengaman: reset hanya ada bila root = partisi bernama selain `userdata` dan
store persisten; NativeUfs menolak jendela store bila root = `userdata` (`0002`, dites dari patch). Store berada di ujung
`ipados` (19,1 GB minimum ≤ 21,48 GB). Payload/MODE A v10: `~/hakios/payload-v10.*` (`boot.img` 103 481 344 B).

### Penulisan GPT lewat ABL: critical unlock **wajib**

Dari biner ABL (OTA OS2.0.16): `IsCriticalPartition` (`.text 0x3e948`) memakai tabel 24 nama di `0xc3548`:
`abl rpm tz sdi xbl hyp pmic bootloader devinfo **partition** devcfg ddr frp cdt cmnlib cmnlib64 keymaster mdtp aop
multiimgoem secdata imagefv qupfw uefisecapp`. Alur flash (`.text 0x3a6d4..0x3a748`): selain `crclist`/`sparsecrclist`,
bila perangkat tidak critical-unlocked dan nama termasuk tabel → "Flashing is not allowed for Critical Partitions".
Jadi `fastboot flash partition:0 gpt_both0.bin` hanya diterima bila **critical-unlocked**. Petunjuk tidak langsung:
skrip porter menulis `abl_ab`, `xbl_ab`, `tz_ab`, `hyp_ab`, `keymaster_ab`, `aop_ab`, `qupfw_ab`, `uefisecapp_ab`,
`devcfg_ab`, `cmnlib*_ab` (semua di tabel itu); bila skrip itu dulu berhasil di tablet ini, ABL menerima flash critical.
Pemastian read-only: `fastboot oem device-info` ("Device critical unlocked: …") pada sesi fastboot berikut. Tidak ada
unlock yang dilakukan atau diusulkan; bila tidak critical-unlocked, jalan lain (penulis GPT di firmware UEFI, dari image
yang sama) perlu dibuat dulu.

### Recovery Android setelah B5

Dengan B5, permintaan recovery (Vol+, `adb reboot recovery`, BCB) membuka menu; timeout/entri Android → Android normal
(tidak pernah loop, `mode_b_sim.py`). Jalur kembali ke recovery stock yang selalu tersedia: Vol− → fastboot (ABL di
partisinya sendiri) → `fastboot flash boot_b boot_b-asli.img` (dari dump USB boot LUN) → Vol+ → recovery stock.

### Verifikasi menyeluruh (`tools/final_verify.py`, 25 Nov)

20 dari 21 PASS: kernel tahap B `1d02cbe8…` + kunci owner, anchor dan kedua manifest root tertanam; MODE A v10 (konsisten,
payload + GPU addon, menu/cmdline, ABL); image root (ukuran, SHA-256, OS/SystemOS, `.vroot` = kebijakan owner); B5
(ABL, code0 → shim, BootShim+FD, payload). Satu FAIL yang memang diharapkan: basis B5 pratinjau = kernel ROM, bukan
kernel N0 terpasang — `b5_compose.py --require-installed` menolaknya; basis akhir menunggu dump `boot_b`.

### Preflight RAM-boot berikutnya (belum diizinkan)

Image: **MODE A v9** (`a1ce6a26…`, 103 481 344 B; Tools: GPT view/export, USB disk LUN 0 / boot LUN read-only; tanpa
entri inisialisasi Data, jadi tidak ada entri yang menyentuh store). ABL layout PASS; < `max-download-size` 768 MiB;
< `boot_b`. Slot terakhir terbaca: `b` successful, unbootable=no.

| Langkah | Tulis ke tablet? |
| --- | --- |
| `adb reboot bootloader` (atau Power + Vol−); `fastboot getvar …`, `fastboot oem device-info` | tidak |
| `fastboot boot` image v9 (RAM) → menu → Tools | tidak |
| "USB disk: boot LUN (read only)" → di PC (Administrator) `dump-pipa-usb.ps1 -Mode boot` → Power di tablet | tidak (WriteBlocks ditolak) |
| "USB disk: LUN 0 (read only)" → `-Mode lun0` | tidak |
| menu → **Power off**; nyalakan dengan Power → Android | tidak |

Risiko dan pemulihan: (1) ABL menolak image → slot `_b` bisa ditandai unbootable → `fastboot set_active b` (butuh izin
terpisah); (2) `UsbMsdDxe` (biner Qualcomm) macet atau Windows meminta "format" → batalkan; tahan Power 15–20 s →
Android (cara yang sudah terbukti); (3) jangan memilih entri iPadOS (belum ada `ipados`: panic → restart otomatis
→ Android) atau Restart; (4) dump berisi `persist`/`modemst` (data kalibrasi): hanya di `~/.hakios-private`.

## 14. Sesi 21: dump read-only dari tablet (RAM-boot MODE A v9, disetujui pemilik)

- Preflight: Android normal (kernel N0, `RUNNING_UNLOCKED`), baterai 88 %, slot `b` successful / not unbootable / retry 6,
  v9 `a1ce6a26…` = catatan (dicek ulang sebelum setiap `fastboot boot`). `fastboot oem device-info`: **Device critical
  unlocked: true** (tidak ada unlock yang dilakukan). Slot tidak pernah berubah selama sesi.
- Kejadian: entri menu "Android / HyperOS" = reset, dan selama sesi (`adb reboot bootloader`) ABL membawa reset itu ke
  fastboot — tiga kali; tidak ada kerusakan. Alat USB kedua dalam satu boot tidak menyala (UsbMsdDxe tidak bisa
  di-start ulang setelah `StopDevice`); LUN 0 diambil di boot terpisah. Dua bug `dump-pipa-usb.ps1` tertangkap di
  perangkat dan diperbaiki dengan uji PowerShell: `xbl_b` ada di LUN 2 (bukan boot LUN) dan `[math]::Min` Int32 untuk
  disk > 2 GiB.
- Hasil (`~/.hakios-private/usb-dump-s21.*`, tidak di Git): `boot-lun.img` 2 281 701 376 B (65 partisi),
  `lun0-head.img` 11 056 185 344 B (sampai awal `userdata`), `lun0-tail.bin`. `usb_dump_check.py`: SHA-256, kedua GPT,
  tata letak terukur, `super` liblp, `rom_match` → **RECOVERY SET VERIFIED**. `boot_b` = kernel N0 terpasang
  (banner = `/proc/version`); `vendor_boot_b`/`dtbo_b` terpasang berbeda dari paket porter (dump ini yang dipakai).
- GPT asli → `gpt_rewrite.py`: 53 byte berubah per salinan, `ipados` 56 637 184..61 880 314; `image_root_check.py`
  image MODE A v10 dengan GPT baru → PASS.
- B5 di atas `boot_b` N0 (`--require-installed`): 176 832 512 B (`31ad7b77…`), sisa 24,5 MB; `final_verify.py` **21/21**.
- `design_b_readiness.py`: 1–2 WAIVED, 3 PASS (boot chain terpasang persis), 4 PASS, 5 PASS, 6 BLOCKED (persetujuan).
