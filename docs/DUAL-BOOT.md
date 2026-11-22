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
| Entri (dari builder UniXNU yang sebenarnya, `tools/unixnu_payload_menu.py`) | 1 Android (reset) · 2 iPadOS 17.7.11 (`xnu`) · 3 Recovery/Fastboot (reset) · Restart · Power off · Tools. **Tidak ada** "Install and boot" (dihapus oleh `patches/unixnu-pipa/0002`) | 1 Android (reset) · 2 HakiOS · 3 Recovery/Fastboot · shell · info |
| Tombol | Vol+/Vol- = atas/bawah, Power = Enter (sesuai keymap firmware; belum dilihat) | `BUTTON_REMAP_PHONE_KEYS`: VOLUMEUP→UP, VOLUMEDOWN→DOWN, POWER→ENTER (dicek di source U-Boot) |
| Timeout/default | `[boot] timeout`/`default`; entri dengan `confirm` tidak pernah dipilih oleh countdown | `bootmenu_delay`, `bootmenu_default` (dicek di `cmd/bootmenu.c`, `common/menu.c`) |
| Uji offline | `tests/test_unixnu_menu.py` (5), `tests/test_payload_integration.py` (6, builder asli), `tests/test_unixnu_image.py` (5, image + volume FAT) | `tests/test_bootmgr_env.py` (10), `tools/check_uboot_config.py` (Kconfig U-Boot) |

## Handoff dan kegagalan

| Keadaan | Apa yang terjadi |
| --- | --- |
| Tidak ada tombol 10 s | entri Android → reset → ABL → Android |
| Pilih iPadOS | DarwinBoot memuat `Payloads/kernel.macho` + `.adt` (+ trust cache), XNU 10063 |
| Kernel panic | UniXNU-pipa: layar panic, lalu restart ke fastboot dengan log di ramoops (referensi xVanTuring) → `scripts/capture-boot-log.sh` di Android |
| Hang tanpa log | tahan Power 10–15 s → Android |
| Recovery / Fastboot | entri reset sambil menahan Vol+ (recovery) / Vol- (fastboot); ABL membaca tombol saat reset — **belum diuji**. Cara pasti tetap: matikan, Vol- + Power |
| Image tidak diterima ABL | tablet tetap di fastboot; `fastboot reboot` |

## Keselamatan data Android (sesi 3)

`fastboot boot` tidak menjamin apa pun: image di RAM tetap bisa mengakses UFS. Hasil audit driver UFS UniXNU-pipa
(`drivers/ShengUfs`): satu-satunya perintah tulis adalah `hostWrite4k` (WRITE(10)), dan hanya di dalam dua jendela —
store Data (`sheng-data-persist=2`) dan log/export (`sheng-log=1`, juga `log=1`) — yang keduanya terletak **di dalam
partisi root**, yang di port asli adalah `userdata` Android. Volume root sendiri read-only
(`doFormatMedia` → `kIOReturnNotWritable`). `sheng-data-reset=1/2` mengosongkan store Data.

Perbaikan (`patches/unixnu-pipa/0002`, sumber dan board):

| Sebelum | Sesudah |
| --- | --- |
| `[payload.install]` "ERASE all iPadOS user data…" dengan `sheng-data-reset=1`/`=2` | dihapus |
| `sheng-data-persist=2` (jendela tulis di akhir `userdata`) | dihapus |
| root dicari di partisi bernama `userdata` (konstanta di `RootLayout.h`) | nama dari `native-ufs-root-part=ipados`; default lama tetap untuk port lain |
| — | driver **menolak** membuka jendela store/log bila partisi root bernama `userdata` |

Bukti: `tools/storage_safety.py` (builder asli → PASS; board lama → 9 FAIL), `tests/test_payload_integration.py`,
`tests/c/root_layout_test.cpp` (parser produksi `RootLayout.h`, 14 cek; tidak terkompilasi tanpa patch). Menurut source
(belum dilihat di tablet): tanpa partisi `ipados`, kernel berhenti di mount root dan tidak membuka jendela tulis.

Root permanen dan MODE B: [MODE-B.md](MODE-B.md).

## Recovery plan

| Keadaan | Tindakan |
| --- | --- |
| Hang di menu/iPadOS/HakiOS | Tahan Power 10–15 s → Android (tidak ada yang ditulis) |
| Masuk fastboot | `fastboot reboot` |
| Android tidak boot setelah percobaan RAM | Tidak seharusnya terjadi (tidak ada tulis). Cek `fastboot getvar current-slot`; boot normal |
| Setelah repartisi (masa depan) | Fastboot ROM resmi versi **sama** (`flash_all` mengembalikan GPT stock, menghapus data) + pulihkan backup. Cek `fastboot getvar anti` (anti-rollback) |
| Boot image rusak (mode flash masa depan) | `fastboot flash boot_<aktif> private/backup/<build>/boot_<aktif>.img`, hash sama dengan `SHA256SUMS` |
