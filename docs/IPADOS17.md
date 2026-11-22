# iPadOS 17 dan basis HakiOS

## Kesimpulan

Basis HakiOS saat ini **tidak bisa** menjalankan iPadOS 17 tanpa porting kernel besar. **Diputuskan (sesi 2):
opsi 3, UniXNU-pipa**, yang memakai `xnu-10063.141.1` untuk iPadOS 17.7.11: [BASE-DECISION.md](BASE-DECISION.md).

| | Versi Darwin | XNU |
| --- | --- | --- |
| iPadOS 17.x | Darwin 23 | `xnu-10002.*` (17.0–17.3), `xnu-10063.*` (17.4–17.7) |
| HakiOS `common`/`main` | Darwin 26/27 | `xnu-12377.121.6` |
| HakiOS `legacy-hackios` | Darwin 22 (iOS 16.5) | `xnu-8796.121.2` |

User space Darwin dan kernel harus satu generasi: trap Mach dan syscall, antarmuka IOKit user client, sysctl,
`libsystem_kernel`, format trust cache/AMFI, dan dyld shared cache berubah antar versi besar. User space iPadOS 17 di
atas `xnu-12377` atau `xnu-8796` tidak didukung oleh kedua branch.

## Perbedaan iPad vs iPhone

- HakiOS membangun identitas perangkat dari `DeviceTree.bin` iPhone12,1. Idiom tablet SpringBoard (Dock, Stage
  Manager/Split View, Control Center iPad) ditentukan oleh kelas perangkat yang dibaca dari identitas itu, jadi
  butuh IPSW iPad dan DeviceTree model iPad donor.
- Resolusi 2880 × 1800 (16:10) tidak sama dengan iPad mana pun (iPad memakai 4:3 atau mendekatinya); scaling
  SpringBoard harus diuji.

## Pilihan jalur

1. **Tetap di HakiOS `common` (Darwin 26/27), donor iPad generasi yang sama.** Paling sedikit kerja kernel; hasilnya
   bukan iPadOS 17.
2. **Backport HakiOS ke `xnu-10063` (iPadOS 17.7).** Patch kernel dan puluhan ribu baris driver HakiOS dibawa ke kernel
   yang lebih tua; pekerjaan besar, tidak bisa diuji tanpa iPhoneOS SDK yang sesuai dan tablet.
3. **UniXNU-pipa** (sudah menargetkan pipa) sebagai basis iPadOS 17, paket ini hanya sebagai referensi data.

## Lisensi

Repository ini tidak memuat file Apple. Lisensi perangkat lunak iPadOS membatasi pemakaian pada perangkat bermerek
Apple; menjalankannya di Xiaomi Pad 6 berada di luar lisensi itu, terlepas dari cara file diperoleh.
