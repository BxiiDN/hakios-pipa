# Peta RAM pipa dan handoff DRAM ke XNU (sesi 10)

Tidak di-boot. Semua di bawah dibaca dari source yang benar-benar dijalankan (UniXNU `62f203c` + patch hakios, DarwinBoot
di dalamnya, XNU `10063` feed `b7545ced`, uefi-pipa `1f6a1520`) dan dicek offline. **Penempatan window yang sebenarnya
hanya diketahui saat boot.**

## Fakta perangkat (unit 8 GB, dicatat read-only dari device tree Android)

| | Alamat | Ukuran |
| --- | --- | --- |
| Bank 1 | `0x80000000` | `0x3bb00000` (≈ 955 MiB) |
| Celah (direservasi bootloader, bukan partisi RAM) | `0xbbb00000..0xc0000000` | `0x4500000` (69 MiB) |
| Bank 2 | `0xc0000000` | `0x1c0000000` (7 GiB) |
| Span (alamat pertama .. akhir terakhir) | `0x80000000` | `0x200000000` (8 GiB) |
| RAM fisik total (jumlah bank) | — | `0x1fbb00000` (≈ 7.93 GiB) |
| Window owned yang diminta (`owned_memory_size`) | dipilih DarwinBoot | `0x170000000` (5.75 GiB) |

Span ≠ RAM: span memuat celah. Window ≠ RAM yang dipakai kernel seluruhnya: kernel hanya mengelola window.

## Penyebab pasti ADT gagal

`unixnu build payload` berhenti di `devicetree.generate()` (UniXNU `62f203c`, sama di upstream `92c7e6d`): hanya
satu node `memory` dengan satu rentang yang diterima. DTS port EsaiJJ `c4c1a3a` (benar, sesuai pengukuran) punya dua
node. Port juga menulis `board.toml [payload.adt] dram_size = 0x200000000` (span) dan `check-pipa-board.py` memeriksa
span dari bank: port dirancang untuk multi-bank, generator pin tidak.

## Siapa membaca apa (kontrak penerima)

| Langkah | Membaca | Dipakai untuk | Sumber |
| --- | --- | --- | --- |
| uefi-pipa `MemoryMapLib.c` | tabel tetap | wilayah reserved/MMIO/DXE heap | `Platforms/Xiaomi/pipaPkg/Library/MemoryMapLib/MemoryMapLib.c` |
| `RamManagerDxe` | partisi RAM firmware Qualcomm (`EFI_RAMPARTITION_PROTOCOL`) | menambah bagian partisi RAM yang tidak tercakup tabel tetap sebagai `EfiConventionalMemory`. **Celah bukan partisi RAM → tidak pernah conventional** | `SiliciumPkg/Drivers/RamManagerDxe/RamManager.c`, `QcomPkg/Library/RamManagerLib/RamManager.c` |
| DarwinBoot `AllocateWindow` | peta memori UEFI | window = `AllocatePages(AllocateAddress)` di dalam **satu run** descriptor conventional yang bersambung (`RunEnd`), awal rata 2 MiB + offset kernel; gagal → "NO WINDOW", boot dibatalkan sebelum ExitBootServices | `drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c` |
| DarwinBoot `Boot` | — | `boot_args.PhysicalBase` = alamat window, `MemorySize` = `MemorySizeActual` = ukuran window; kernel, args, ADT, RAM disk, trust, addon diletakkan di dalam window | idem |
| XNU `arm_init` | `boot_args` | `gPhysBase/gPhysSize`: satu-satunya memori yang dikelola kernel | `osfmk/arm/arm_init.c` |
| XNU `arm_init` | ADT `/chosen dram-base/dram-size` | `gDramBase/gDramSize` → hanya `is_dram_addr()` → atribut cache pemetaan device (`wimg_to_pte`, VM_WIMG_IO/POSTED) | `osfmk/mach/arm/vm_param.h`, `osfmk/arm/pmap/pmap.c` |

Tidak ada pembaca lain `dram-base/dram-size` di XNU, UniXNU (package, drivers, kits, patches) atau port pipa.

## Representasi yang dipilih

- DTS tetap dua bank (tidak digabung).
- Patch `patches/unixnu/0006`: `dram_span()` menolak bank kosong, wrap, atau tumpang tindih; ADT menerima
  `dram-base = 0x80000000`, `dram-size = 0x200000000` (span, seperti iBoot: "actual DRAM base address and size"); window
  yang lebih besar dari setiap bank ditolak (DarwinBoot tidak bisa menempatkannya dalam satu run).
- Celah **tidak pernah** diberikan sebagai memori: ia di luar setiap descriptor conventional, jadi di luar window, jadi
  di luar `gPhysBase/gPhysSize`. Satu-satunya efek span: `is_dram_addr()` benar untuk alamat celah, dan itu hanya mengubah
  atribut cache bila sesuatu memetakan celah sebagai device — tidak ada yang melakukannya.

## Bukti offline (`tools/memory_plan.py`)

| Cek | Hasil |
| --- | --- |
| Tabel tetap uefi-pipa menandai celah sebagai conventional | tidak |
| Run bebas sebelum driver (batas atas) | `0x9e400000+0x1800000`, `0xb1400000+0xa700000`, `0xc0000000+0x3fc00000`, `0xffc20000+0x1803e0000` |
| Run yang bisa memuat window `0x170000000` | hanya `0xffe00000..0x280000000` (bank 2, di atas "Bank 1 Hole" `0xffc00000+0x20000`) |
| Sisa untuk alokasi UEFI di run itu | `0x10200000` (258 MiB) |
| Layout DarwinBoot di window (payload sesi 10) | kernel `0x4385000`, args, ADT, RAM disk packed, trust, addon: dipakai `0x4efc000` dari `0x170000000` − 2 MiB |

Tidak terverifikasi: apakah alokasi DXE (top-down) menghabiskan > 258 MiB di ujung bank 2. Bila ya, DarwinBoot menolak
dengan "NO WINDOW … BIG RUN …" (aman, tidak menulis di luar run). `board.toml` sendiri menulis bahwa ukuran window harus
dikonfirmasi pada boot UEFI pertama; tidak diubah dari host.

Tes: `tests/test_adt_dram.py` (8, generator asli + DTS pipa asli lewat dtc), `tests/test_memory_plan.py` (7),
`tests/test_payload_check.py` (9).
