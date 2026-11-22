# hakios-pipa — HakiOS untuk Xiaomi Pad 6 (`pipa`, Snapdragon 870 / SM8250)

Paket perangkat [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel) untuk Xiaomi Pad 6, profil boot manager
U-Boot, validator partisi/dual-boot offline, dan skrip Windows 11 + WSL2.

**Status singkat (sesi 3, 23 Nov 2026): OFFLINE CHECKS PASS, READY FOR HARDWARE BOOT: NO. Belum pernah dijalankan di tablet.** Basis iPadOS 17: UniXNU + UniXNU-pipa
(`xnu-10063.141.1`, iPadOS 17.7.11); HakiOS untuk tooling dan jalur riset kedua. Yang terverifikasi hanyalah sumber,
konfigurasi dan build offline. Detail: [docs/STATUS.md](docs/STATUS.md).

Tidak ada apa pun di repository ini yang menulis ke penyimpanan tablet. Image boot manager hanya untuk
`fastboot boot` (dari RAM); reboot kembali ke Android.

| Dokumen | Isi |
| --- | --- |
| [docs/STATUS.md](docs/STATUS.md) | Matriks verifikasi (SOURCE / BUILD / PREBOOT / HARDWARE / FULLY), 30 komponen hardware, hasil build |
| [docs/BASE-DECISION.md](docs/BASE-DECISION.md) | HakiOS vs UniXNU: versi XNU, driver, bukti, keputusan basis |
| [docs/HARDWARE-FACTS.md](docs/HARDWARE-FACTS.md) | Panel, touch, speaker, Wi-Fi, GPU dari tree publik, dengan node asalnya |
| [docs/ADRENO650.md](docs/ADRENO650.md) | Status dan rencana GPU |
| [docs/UPSTREAM-TESTS.md](docs/UPSTREAM-TESTS.md) | Baseline host test HakiOS dan patch-nya |
| [docs/MODE-B.md](docs/MODE-B.md) | Dual boot permanen (menu saat power-on): pilihan, risiko, root terpisah |
| [docs/XNU-BUILD.md](docs/XNU-BUILD.md) | Build XNU 10063: dependency, input IPSW iPad7,1, perintah |
| [docs/CLAUDE-CODE.md](docs/CLAUDE-CODE.md) | Urutan kerja dengan tablet untuk Claude Code |
| [docs/AUDIT.md](docs/AUDIT.md) | Audit repository sumber: branch, commit, versi XNU, lisensi, dependensi |
| [docs/IPADOS17.md](docs/IPADOS17.md) | Mengapa basis HakiOS saat ini tidak menjalankan iPadOS 17, dan pilihan jalurnya |
| [docs/DUAL-BOOT.md](docs/DUAL-BOOT.md) | Desain dual boot Android + HakiOS, penyimpanan, instalasi, recovery plan |
| [docs/WSL.md](docs/WSL.md) | Windows 11 + WSL2 Ubuntu: setup, build, USB ke tablet |

## Isi

| Path | Apa |
| --- | --- |
| `board.dts`, `soc.dtsi` | Paket perangkat HakiOS (dibuat `tools/device.py init` dari `sm8250-xiaomi-pipa.dts` Linux mainline; offset clock display diisi dari driver clock Linux) |
| `uefi-profiles/xiaomi/pipa/` | Profil U-Boot untuk hakios-uefi: boot menu Android / HakiOS / Recovery-Fastboot (Vol+/Vol-/Power, timeout 10 s ke Android) |
| `tools/pipa_gpt.py` | Pembaca GPT dump + validator rencana dual boot (PASS/FAIL/BLOCKED); `tests/` mengujinya |
| `tools/verify_bootimg.py` | Pemeriksa header Android boot image sebelum `fastboot boot` |
| `tools/mkdts.sh` | Menggabungkan device tree pipa dari Linux (tanpa dtc) |
| `tools/check_uboot_config.py` | Defconfig U-Boot pipa diselesaikan dengan Kconfig U-Boot sendiri |
| `tools/pipa_hw_facts.py` | Fakta hardware dari device tree live, dicek terhadap asumsi repo |
| `tools/firmware_manifest.py`, `manifests/` | Digest firmware milik sendiri vs manifest (tanpa firmware di repo) |
| `tools/storage_safety.py`, `tools/unixnu_payload_menu.py` | Menu dan argumen kernel dari builder UniXNU asli, ditolak bila menyentuh storage Android |
| `tools/fat_reader.py`, `tools/image_root_check.py`, `tools/panel_firmware.py` | Isi volume payload di image; root vs GPT tablet; firmware touch per panel |
| `tools/a650_check.py` | Konstanta Adreno 650: Linux vs UniXNU-pipa vs HakiOS |
| `patches/upstream/` | Perbaikan untuk kernel HakiOS yang dipin |
| `patches/unixnu/`, `patches/unixnu-pipa/` | Menu Android-first untuk payload UniXNU |
| `scripts/` | Setup/build: `wsl-setup.sh`, `fetch-upstream.sh`, `fetch-unixnu.sh`, `build.sh`, `build-uboot.sh`, `unixnu-checks.sh`. Tablet (read-only kecuali `temp-boot.sh` = `fastboot boot`): `detect-device.sh`, `extract-live-dt.sh`, `extract-firmware.sh`, `backup-readiness.sh`, `dump-gpt.sh`, `hw-diag.sh`, `preflight.sh`, `temp-boot.sh`, `capture-boot-log.sh` |
| `plans/ram-boot.json` | Rencana default: tidak menulis partisi apa pun |
| `UPSTREAM` | Commit HakiOS kernel, hakios-uefi dan Linux yang dipin |

## Mulai

```sh
scripts/wsl-setup.sh --install     # sekali
scripts/build.sh                   # semua yang bisa dibangun/diuji tanpa tablet; ringkasan di logs/build-summary.txt
scripts/preflight.sh               # sebelum tablet disentuh
```

Hubungan upstream: paket ini tidak menyalin kode HakiOS. `scripts/fetch-upstream.sh` mengambil commit yang dipin di
`UPSTREAM`, lalu `tools/device.py add --from` memasukkan paket pipa ke checkout itu. Update HakiOS = ganti
`KERNEL_REF`, jalankan `scripts/build.sh`, commit jika lulus.

Tidak ada file Apple, firmware vendor, atau device tree Android di repository ini (`.gitignore`).
