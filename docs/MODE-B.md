# MODE B: menu Android / iPadOS setiap tablet dinyalakan — rancangan, belum dicoba (audit sesi 11)

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
