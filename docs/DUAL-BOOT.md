# Dual boot Android/HyperOS + iPadOS 17 di Xiaomi Pad 6

Status: **desain, konfigurasi dan pengujian offline. Belum diuji di tablet. Dual boot belum berhasil sampai Android
dan iPadOS dilihat berjalan bergantian di Pad 6.** Sesi ini tidak mem-flash dan tidak mengubah partisi.

## Prinsip

1. Tablet dinyalakan biasa → ABL → Android/HyperOS. Tidak ada yang berubah di jalur ini.
2. OS kedua selalu dimulai **dari RAM** (`fastboot boot`, `scripts/temp-boot.sh`), jadi reboot apa pun kembali ke
   Android. Slot A/B tidak dipakai sebagai "dua OS": OTA virtual A/B menulis ke slot inaktif, dan
   `tools/pipa_gpt.py` menolak rencana yang menulis ke sana.
3. Boot manager adalah menu di image RAM itu sendiri: Android (default, timeout 10 s), iPadOS 17, Recovery/Fastboot.

## Dua image, dua menu

| | iPadOS 17 (basis utama) | Riset Darwin HakiOS (jalur kedua) |
| --- | --- | --- |
| Image | uefi-pipa + payload UniXNU (`./unixnu bootimg`) | U-Boot hakios-uefi + `loader.efi` (`scripts/build-uboot.sh`) |
| Menu | menu UniXNU (`\EFI\UniXNU\unixnu.toml`), dibuat `scripts/unixnu/payload.py` | `bootmenu` U-Boot (`board/xiaomi/pipa.env`) |
| Android-first | `patches/unixnu/0001` + `patches/unixnu-pipa/0001` (`[payload.dualboot]`, `timeout = 10`) | `bootmenu_default=0`, `bootmenu_delay=10` |
| Entri | 1 Android (reset) · 2 iPadOS 17.7.11 (`xnu`) · [Install and boot, dengan konfirmasi] · 3 Recovery/Fastboot (reset) · Restart · Power off | 1 Android (reset) · 2 HakiOS · 3 Recovery/Fastboot · shell · info |
| Tombol | Vol+/Vol- = atas/bawah, Power = Enter (sesuai keymap firmware; belum dilihat) | `BUTTON_REMAP_PHONE_KEYS`: VOLUMEUP→UP, VOLUMEDOWN→DOWN, POWER→ENTER (dicek di source U-Boot) |
| Timeout/default | `[boot] timeout`/`default`; entri dengan `confirm` tidak pernah dipilih oleh countdown | `bootmenu_delay`, `bootmenu_default` (dicek di `cmd/bootmenu.c`, `common/menu.c`) |
| Uji offline | `tests/test_unixnu_menu.py` (5) | `tests/test_bootmgr_env.py` (10), `tools/check_uboot_config.py` (Kconfig U-Boot) |

## Handoff dan kegagalan

| Keadaan | Apa yang terjadi |
| --- | --- |
| Tidak ada tombol 10 s | entri Android → reset → ABL → Android |
| Pilih iPadOS | DarwinBoot memuat `Payloads/kernel.macho` + `.adt` (+ trust cache), XNU 10063 |
| Kernel panic | UniXNU-pipa: layar panic, lalu restart ke fastboot dengan log di ramoops (referensi xVanTuring) → `scripts/capture-boot-log.sh` di Android |
| Hang tanpa log | tahan Power 10–15 s → Android |
| Recovery / Fastboot | entri reset sambil menahan Vol+ (recovery) / Vol- (fastboot); ABL membaca tombol saat reset — **belum diuji**. Cara pasti tetap: matikan, Vol- + Power |
| Image tidak diterima ABL | tablet tetap di fastboot; `fastboot reboot` |

## Penyimpanan iPadOS permanen

UniXNU-pipa meletakkan root iPadOS (volume OS + SystemOS) di **jendela `userdata` Android**
(`board.toml [userdata] first_lba 0x293000 … last_lba 0x3b037fa`, `native-ufs-root=1`), dan menulisnya dengan
`fastboot flash userdata` — itu **menghapus data Android**. Tidak dipakai.

Desain yang menjaga Android (belum dijalankan; butuh persetujuan dan backup):

1. Backup penuh (`scripts/backup-readiness.sh` + backup data milik pemilik, dipulihkan sekali sebagai uji).
2. Ukuran `userdata` baru dan partisi `ipados` di akhir LUN 0 (sda), 1 MiB-aligned, dicek dulu:
   `pipa_gpt.py check plans/<rencana>.json private/gpt/*.bin` → harus PASS dengan `userdata_erase_confirmed` dan
   `backup_verified`. Mengecilkan `userdata` = format ulang `userdata` (FBE): **semua data Android hilang sekali**,
   lalu dipulihkan dari backup.
3. `board.toml [userdata]` UniXNU-pipa diarahkan ke LBA partisi `ipados` (bukan `userdata`), lalu image root ditulis
   ke `ipados` saja. Android kembali memakai `userdata` yang lebih kecil.
4. OTA Android tidak menyentuh partisi baru, tapi tool flash Xiaomi (`flash_all`) bisa menulis ulang GPT dan
   menghapusnya: dokumentasikan sebelum update besar.

Tanpa repartisi, iPadOS hanya bisa dicoba dengan root di RAM/initrd (keterbatasan ukuran; belum dievaluasi untuk
17.7.11) atau di unit yang Android-nya boleh dihapus.

## Recovery plan

| Keadaan | Tindakan |
| --- | --- |
| Hang di menu/iPadOS/HakiOS | Tahan Power 10–15 s → Android (tidak ada yang ditulis) |
| Masuk fastboot | `fastboot reboot` |
| Android tidak boot setelah percobaan RAM | Tidak seharusnya terjadi (tidak ada tulis). Cek `fastboot getvar current-slot`; boot normal |
| Setelah repartisi (masa depan) | Fastboot ROM resmi versi **sama** (`flash_all` mengembalikan GPT stock, menghapus data) + pulihkan backup. Cek `fastboot getvar anti` (anti-rollback) |
| Boot image rusak (mode flash masa depan) | `fastboot flash boot_<aktif> private/backup/<build>/boot_<aktif>.img`, hash sama dengan `SHA256SUMS` |
