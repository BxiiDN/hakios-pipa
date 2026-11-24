# MODE B: menu Android / iPadOS setiap tablet dinyalakan — rancangan, belum dicoba (audit sesi 11–12)

| Mode | Cara | Status |
| --- | --- | --- |
| **A — Temporary boot** | PC: `scripts/temp-boot.sh IMAGE --gpt DIR --yes` (`fastboot boot`, RAM). Menu UniXNU: Android default 10 s → reset → ABL → Android | Konfigurasi dan pengujian offline selesai; **belum boleh dijalankan** (`scripts/readiness.sh` = NO) |
| **B — Persistent dual boot** | Menu muncul sendiri saat power-on biasa | **Rancangan saja**. Butuh menulis partisi boot; tidak dilakukan |

## Kenapa MODE A tidak bisa langsung dipakai sebagai MODE B

Entri Android di MODE A adalah `reset`. Itu hanya kembali ke Android karena image menu tidak ada di flash. Kalau image
menu ditaruh di `boot_<aktif>`, `reset` akan kembali ke **menu yang sama**: Android tidak akan pernah jalan. MODE B
butuh handoff Android yang nyata.

## Pilihan, dinilai

| Opsi | Cara kerja | Yang harus dibuktikan dulu | Risiko | Penilaian |
| --- | --- | --- | --- | --- |
| B1. Menu di `boot_<aktif>`, Android dimuat oleh firmware | uefi-pipa/U-Boot di `boot_a`; entri Android memuat kernel+ramdisk stock (boot, `vendor_boot`, `dtbo`) dengan cmdline/bootconfig yang biasanya diisi ABL (`androidboot.*`, slot, status verified boot, serial) | Kernel stock pipa (4.19) bisa di-boot dari UEFI/U-Boot (`bootm`/`abootimg` U-Boot, atau EFI stub) dengan DTB + overlay yang dipilih ABL; Android lulus boot tanpa nilai ABL yang hilang | Tinggi: semua argumen ABL harus ditiru; OTA mengganti `boot` slot baru → menu hilang setelah update (aman, tapi harus dipasang ulang); AVB: perangkat unlocked tetap boot (orange state), belum diverifikasi di pipa | Paling dekat dengan target; **BLOCKED** sampai handoff Android terbukti dari RAM (MODE A) |
| B2. Menu di partisi `recovery` (jika ada) | `boot_a` tetap stock; menu dipanggil dengan kombinasi tombol recovery saat power-on | Apakah pipa punya `recovery_a/_b` terpisah (baca dari `scripts/dump-gpt.sh`) | Kehilangan recovery stock selama terpasang | Bukan "setiap power-on", tapi Android tidak tersentuh. Bergantung GPT |
| B3. Slot A = Android, slot B = iPadOS | `set_active` berganti | — | OTA virtual A/B menulis slot inaktif → merusak OS kedua atau Android | **Ditolak** (`pipa_gpt.py` FAIL untuk slot inaktif) |
| B4. Tetap dari PC | MODE A | — | Tidak ada | Aman, tapi bukan target |
| B5. Android tetap dimuat ABL; kernel Android membawa menu (pola *dual-boot kernel patcher* komunitas WoA; sumbernya belum diaudit) | `boot_<aktif>` = boot Android stock yang kernel-nya diberi shellcode kecil di entry: tanpa tombol → lanjut ke kernel Android asli (semua `androidboot.*`, AVB, DTB/overlay tetap dari ABL); dengan tombol → lompat ke FD uefi-pipa yang ikut disematkan, lalu DarwinBoot | (a) ABL menerima kernel blob sebesar itu (batas region kernel ABL belum diukur); (b) FD bisa jalan setelah ABL sudah menyiapkan Linux (tanpa layanan ABL); (c) DarwinBoot menemukan payload bukan di ramdisk boot image (ramdisk = milik Android) | Sedang: semuanya bisa **dibuktikan dari RAM** (`fastboot boot` image Android yang ditambal; tidak menulis apa pun); OTA mengganti `boot` → menu hilang, Android tetap jalan | **Kandidat terbaik**, karena entri Android = kernel Android asli, bukan `reset` → tidak ada loop. Belum dibangun |

### Audit sesi 11 (offline, tanpa tablet)

Penyebab loop MODE A di flash, dipastikan: entri Android menu = `reset`; ABL lalu memuat `boot_<aktif>` lagi = menu. B1
memindahkan semua tugas ABL ke firmware kita (paling berisiko). B5 membiarkan ABL tetap memuat Android dan hanya
menyisipkan percabangan di entry kernel Android.

Anggaran ruang B5, diukur dari OTA resmi `OS2.0.16.0.UMZMIXM` (`boot.img` header v3, kernel Image mentah 52 826 128 B,
ramdisk 20 159 971 B) dan FD `bd39c37a…` (3 145 728 B), halaman 4 KiB, `boot_b` = 201 326 592 B:

| Isi `boot_<aktif>` | Ukuran | Muat? |
| --- | --- | --- |
| kernel Android + FD + ramdisk Android + payload 128 MiB sekarang | 210 358 272 B | **tidak** (lebih 8,6 MiB) |
| sisa untuk payload | 119,4 MiB | payload ≤ 112 MiB (isi yang dipakai DarwinBoot sekarang ≈ 79 MiB, `0x4efc000`) |

Yang belum diketahui dan harus dibuktikan dari RAM, berurutan: (1) image Android stock yang hanya ditambal (tanpa FD)
boot sampai home screen lewat `fastboot boot`; (2) dengan FD + tombol, menu uefi-pipa muncul; (3) DarwinBoot memuat
payload dari tempat baru. Root iPadOS tetap butuh partisi `ipados` (bagian bawah): MODE B tanpa root itu hanya menu.

Urutan pembuktian sebelum B1: (1) MODE A berhasil dan kembali ke Android; (2) dari RAM, firmware memuat Android stock
sampai home screen (dengan `boot_<aktif>` tetap stock); (3) backup boot-chain terverifikasi (`backup-readiness.sh`);
(4) baru menulis `boot_<aktif>` sekali, dengan rencana yang lulus `pipa_gpt.py check` (`android_fallback_tested`).
Sesi ini tidak melakukan satu pun.

## Root iPadOS terpisah: bisa tanpa repartisi?

| Tempat root | Hasil |
| --- | --- |
| Partisi `userdata` Android (rancangan asli UniXNU-pipa) | **Ditolak**: `fastboot flash userdata` menghapus Android |
| File di dalam `userdata` | Tidak bisa: f2fs + FBE, Darwin tidak membacanya |
| RAM (payload `fastboot boot`) | Payload yang diterima ABL ±200 MB (referensi xVanTuring 204 MB); root iPadOS 17 berukuran GB. Tidak cukup |
| Drive USB-C | Butuh driver host USB di kernel; DWC3 di UniXNU-pipa hanya gadget/diagnostik, default-off |
| Ruang kosong GPT LUN 0 | Mungkin ada sisa kecil di akhir LUN; ukur dengan `pipa_gpt.py read` (jendela EsaiJJ: `userdata` sampai `0x3b037fa`) |
| **Partisi `ipados` baru** | Satu-satunya pilihan untuk root permanen. Hampir pasti butuh mengecilkan `userdata` |

**Mengecilkan `userdata` = memformat ulang `userdata` (dan `metadata` untuk kunci FBE): semua data Android hilang**,
lalu dipulihkan dari backup. Prosedur (tidak dijalankan):

1. Backup penuh data Android oleh pemilik, dipulihkan sekali sebagai uji; backup boot-chain (`backup-readiness.sh`).
2. Rencana partisi lulus `pipa_gpt.py check` dengan `userdata_erase_confirmed` dan `backup_verified`.
3. Repartisi dari PC (bukan dari skrip repo ini), format `userdata`/`metadata`, Android first boot, pulihkan data.
4. Tulis image root iPadOS hanya ke `ipados`. Image memakai `native-ufs-root-part=ipados` (patch `0002`), dan driver
   menolak membuka jendela tulis apa pun pada partisi bernama `userdata`.
5. Pemulihan bila gagal: fastboot ROM resmi dengan **versi sama** (`flash_all` mengembalikan GPT stock dan menghapus
   data) + backup; periksa `fastboot getvar anti` sebelumnya.

## Sesi 12: B5 divalidasi offline (tanpa tablet, tanpa flash)

### ABL, dari biner

Sumber: OTA resmi `OS2.0.16.0.UMZMIXM`, partisi `abl` (`652491b4…`) dan `xbl` (`076b2dab…`) diekstrak dengan
`tools/ota_extract.py` (hash tiap partisi = `new_partition_info` manifest; `boot` hasil ekstraksi byte-identik dengan
ekstraksi sesi 1). FV LinuxLoader dibuka (LZMA) dan di-disassemble; file disimpan di `~/.hakios-private`, tidak di Git.
**Tablet kini menjalankan OS4.0.8.0**: aturan di bawah milik ABL OS2.0.16 dan harus dicocokkan dengan ABL yang terpasang
sebelum boot apa pun.

| Aturan | Bukti | Dipakai di |
| --- | --- | --- |
| Region kernel ABL = `0xA0000000 + 0x10000000` (256 MiB) | XBL `uefiplat.cfg`: `0xA0000000, 0x10000000, "Kernel"`; ABL membacanya sebagai variabel UEFI `KernelBaseAddr`/`KernelSize` (`.text 0x16550/0x16598`), fallback base + `0x5600000` | `tools/abl_layout.py` |
| KernelLoadAddr = base + `0x80000` (Image arm64) | `.text 0x16658` | idem |
| Ramdisk di ujung region: end − ALIGN(ramdisk + vendor ramdisk, page) − page; DTB = ramdisk − page − 2 MiB; DTB ≤ kernel ditolak | `.text 0x16680..0x166b8` | idem |
| Image `ARMd`: `image_size` (header +0x10) ≤ DTB − kernel, kalau tidak "DTB header can get corrupted due to runtime kernel size" | `.text 0x169c0..0x16a20` | idem |
| Image > partisi boot ditolak ("Image is too large for the partition") | `.text 0x379c4`; cocok dengan pengamatan 17 Nov | idem |
| "Ramdisk size is over the limit" hanya cek overflow alamat | `.text 0x17000` | — |
| Boot normal: ABL menambah ` androidboot.force_normal_boot=1`; charger: `androidboot.mode=charger`; recovery (Vol+, `reboot recovery`) tanpa keduanya. pipa tidak punya partisi `recovery` | string LinuxLoader; `/dev/block/by-name` (read-only) | `tools/b5_shim_model.py` |
| `max-download-size` fastboot | nilai runtime, **tidak** bisa diturunkan statis; yang terbukti: image 130,7 MiB diterima `fastboot boot` | terbuka |

Hasil `abl_layout.py`: boot stock (v3, Image `image_size` 61,3 MiB, ramdisk 19,2 MiB) → kernel `0xa0080000`, DTB
`0xaeac3000`, ramdisk `0xaecc4000`, ruang kernel **234,3 MiB**: PASS. Image MODE A v5 (v1, gzip, ramdisk 112 MiB): PASS.

### Rancangan B5 (pemilih tanpa membaca tombol sendiri)

`boot_<aktif>` = header + ramdisk Android stock; kernel = Image Android stock + shim + FD uefi-pipa + payload. Shim di
entry Image memakai keputusan ABL sendiri:

1. tree di x0 tidak valid, tanpa `/chosen/bootargs`, charger, atau `force_normal_boot=1` → lanjut ke kode Image stock
   tanpa mengubah apa pun (**boot Android normal tidak memakai reset**: ABL yang memuatnya, seperti biasa);
2. boot recovery (tahan Vol+) → timpa `/chosen linux,initrd-start/-end` di tempat (panjang sama) dengan alamat payload,
   lalu BootShim dengan x0 sama. `ShengBootMemoryDxe`/`UniXNURamDiskDxe` membaca payload dari properti itu; region
   `Kernel` bertipe Reserv sehingga kernel/ramdisk/DTB Android tidak disentuh UEFI.

Spesifikasi yang bisa dites: `tools/b5_shim_model.py` (tes dengan tree dtc dan dengan **DTB Android stock asli** dari
`vendor_boot`, properti `/chosen` diisi seperti ABL). Shim assembly **belum ditulis**; ia harus lulus kasus yang sama.

Anggaran (`abl_layout.py --b5`, payload v5 112 MiB): shim di `0x3262000`, FD `0x3272000`, payload `0x3572000` setelah
awal Image (boleh di dalam bss Linux: di jalur Android shim sudah melompat sebelum Linux menghapus bss; di jalur menu
Linux tidak jalan). `image_size` baru `0xa572000` ≤ ruang ABL `0xea43000`; boot image **193 646 592 B ≤ `boot_b`
201 326 592 B (sisa 7,3 MiB)**: PASS. Payload maksimum B5 = 119 MiB; 128 MiB sesi 10 tidak muat.

### Simulasi jalur boot (`tools/mode_b_sim.py`, `tests/test_mode_b.py`)

| Skenario | Hasil |
| --- | --- |
| B5, power-on biasa / charger | Android / charger, langsung |
| B5, Vol+ → menu, timeout atau entri Android | reset → boot normal → **Android** (tidak loop) |
| B5, Vol+ → iPadOS tanpa partisi root | panic → restart → **Android** |
| B5 ditolak ABL | fastboot (slot lain tidak diandalkan) |
| Semua kombinasi B5 (tombol × charger × pilihan menu × root × diterima) | tidak ada loop; fastboot (Vol−) selalu tercapai |
| Image MODE A di flash | MENU → reset → MENU: **loop** (desain yang ditolak, direproduksi) |

Konsekuensi yang harus diterima pemilik: dengan B5 terpasang, recovery stock hanya bisa lewat entri menu
"Android recovery" (butuh jalur kembali ke Linux, belum ditulis) atau dengan memulihkan boot stock dari fastboot.

### Prasyarat sebelum B5 boleh disentuh di tablet (belum ada yang terpenuhi)

1. ABL yang **terpasang** (OS4.0.8.0) diperiksa ulang dengan aturan di atas (OTA OS4.0.8.0 atau dump read-only).
2. Salinan `boot_b` **yang sedang terpasang** (OS4.0.8.0), bukan OS2.0.16, sebagai jalan pulang lewat fastboot: butuh
   OTA yang sama atau akses root; tablet tidak di-root.
3. Shim assembly ditulis dan lulus `tests/test_mode_b.py` di emulasi (QEMU, x0 = DTB Android stock).
4. Uji RAM: `fastboot boot` image B5 (tanpa menulis) — butuh `max-download-size` ≥ 193 646 592 B, dibaca dengan
   `fastboot getvar` (read-only) saat pemilik sendiri membawa tablet ke fastboot.
5. Baru setelah itu menulis `boot_b` sekali, dengan persetujuan pemilik.

## GPT dan partisi `ipados` (sesi 12)

Sesi 13: kebutuhan, pembaca GPT read-only, rancangan, backup dan pemulihan di [IPADOS-PARTITION.md](IPADOS-PARTITION.md).

Read-only, tanpa root: `/dev/block/by-name` terbaca (nama → nomor), ukuran/offset tidak (SELinux menolak
`/sys/block/*/size`, `/proc/partitions`). Rekaman lama (`board.toml`): `userdata` = `sda34`, LBA 4 KiB
`0x293000..0x3b037fa` (242,4 GB). `sda34` adalah nomor tertinggi di LUN 0 dan awalnya sama dengan unit 128 GB (hanya
ujungnya yang membesar): `userdata` mengisi LUN sampai habis. **Ruang kosong di akhir LUN 0 tidak terukur** (butuh root
atau dump GPT); bila ada, paling banyak sisa perataan, bukan GB.

| Kandidat root iPadOS (butuh 9 457 106 944 B, image root sesi 1) | Hasil |
| --- | --- |
| Ruang kosong LUN 0 | tidak terukur; hampir pasti ≈ 0 |
| `super` (grup `qti_dynamic_partitions` maks 9 122 611 200 B; isi OS2.0.16 6 282 592 256 B) | sisa ≈ 2,65 GiB, dipakai Virtual A/B saat OTA: **tidak** |
| `rawdump`, `cust`, `rescue`, `bk0x`, `logdump`, `minidump` | kecil / dipakai Xiaomi; ukuran tak terbaca tanpa root: **tidak** layak |
| File di `userdata` | f2fs + enkripsi metadata/FBE: blok mentah ciphertext: **tidak** |
| USB-C | butuh driver host USB di XNU port ini: **tidak ada** |
| Mengecilkan `userdata` | satu-satunya jalan; menghapus data Android: **dilarang di sesi ini** |

Status partisi `ipados`: **TIDAK ADA dan tidak bisa dibuat tanpa menghapus data Android.** B5 tanpa root hanya
memberi menu; entri iPadOS berakhir panic → Android.

## Sesi 19: B5 dibangun dan diuji (offline; belum di tablet)

- Shim `package/b5-shim` (`entry.S` + `shim.c`, `build-shim.py`): 10 137 B, independen posisi (di-link pada 0 dan
  0x7ff000 → biner identik, tanpa relokasi). Paritas: `shim.c` di host = `b5_shim_model.py` (termasuk DTB stock).
  **QEMU `virt`** (biner asli, `/chosen` dari `-append`/`-initrd` seperti ABL): `force_normal_boot=1` dan
  `mode=charger` → kode Image sendiri, DTB tak tersentuh; recovery → menu dengan `linux,initrd-start/-end` = payload
  tepat; recovery tanpa initrd → Android (`tests/test_b5_shim_qemu.py`).
- `tools/b5_compose.py`: Image Android (code0 → `b shim`; code0 asli `b` direlokasi, stub EFI `add` disalin) + shim +
  BootShim+FD (dari kernel MODE A) + payload; `image_size` dinaikkan; ramdisk/header stock tetap. Menolak bila ABL akan
  menolak.
- Ramdisk ROM port 35 151 423 B (OTA resmi 19,2 MiB) → payload diturunkan ke **96 MiB** (`unixnu-pipa/0012`; isi 62,8 MiB).
- Image B5 nyata dari `boot.img` paket + MODE A v9 + payload v9: **189 026 304 B** (`1901c2fa…`), sisa 12,3 MB di
  `boot_b`, ABL LAYOUT PASS; isi diverifikasi byte demi byte. Basis yang lebih tepat: `boot_b` terpasang (kernel N0) dari
  dump USB — komposisi diulang dengan itu.
- Image MODE A v9 (FD `da68d465…`, Tools lengkap, payload 96 MiB): `a1ce6a26…`, IMAGE CONSISTENT, payload_check PASS.
