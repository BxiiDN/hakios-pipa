# hakios-pipa — HakiOS untuk Xiaomi Pad 6 (`pipa`, Snapdragon 870 / SM8250)

Paket perangkat [HakiOS](https://github.com/oosexgang/hakios-xnu-kernel) untuk Xiaomi Pad 6, profil boot manager
U-Boot, validator partisi/dual-boot offline, dan skrip Windows 11 + WSL2.

**Status singkat (22 Nov 2026): belum pernah dijalankan di tablet.** Yang sudah terverifikasi hanyalah sumber dan
build offline. Tidak ada klaim boot, hardware, iPadOS 17, maupun dual boot. Detail: [docs/STATUS.md](docs/STATUS.md).

Tidak ada apa pun di repository ini yang menulis ke penyimpanan tablet. Image boot manager hanya untuk
`fastboot boot` (dari RAM); reboot kembali ke Android.

| Dokumen | Isi |
| --- | --- |
| [docs/STATUS.md](docs/STATUS.md) | Matriks verifikasi (SOURCE / BUILD / PREBOOT / HARDWARE / FULLY), 30 komponen hardware, hasil build |
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
| `scripts/` | `wsl-setup.sh`, `fetch-upstream.sh`, `build.sh`, `build-uboot.sh`, `preflight.sh`, `dump-gpt.sh` (read-only) |
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
