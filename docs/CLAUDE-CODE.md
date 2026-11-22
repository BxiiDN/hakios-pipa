# Untuk Claude Code (Windows 11 + WSL2 Ubuntu): urutan kerja dengan tablet

Aturan: tidak ada `fastboot flash`, tidak ada perubahan partisi. Satu-satunya perintah yang menjalankan sesuatu di
tablet adalah `scripts/temp-boot.sh` (`fastboot boot`, RAM saja). `scripts/preflight.sh` memeriksa bahwa tidak ada
skrip di repo yang menulis tablet.

| # | Langkah | Perintah | Hasil |
| --- | --- | --- | --- |
| 1 | Environment + toolchain (idempoten) | `scripts/wsl-setup.sh --install --mu-silicium` lalu `--unixnu-toolchain` (berjam-jam: LLVM) | `logs/toolchain.txt` |
| 2 | Verifikasi repo dan pin | `scripts/fetch-upstream.sh`, `scripts/fetch-unixnu.sh` (commit pin dicek; tag XNU 10063.141.1 dicek ke Apple) | log |
| 3 | Build offline | `scripts/build.sh`, `scripts/build-uboot.sh` | `logs/build-summary.txt` |
| 4 | Deteksi perangkat | `scripts/detect-device.sh` | `private/device.txt` |
| 5 | Device tree live (read-only, root) | `scripts/extract-live-dt.sh` | `private/phone.dts`, `hw-facts.json`, cek fakta |
| 6 | Firmware milik sendiri + manifest | `scripts/extract-firmware.sh` | PASS/FAIL per digest |
| 7 | Backup | `scripts/backup-readiness.sh`; backup data oleh pemilik | `private/backup/<build>/SHA256SUMS` |
| 8 | GPT read-only | `scripts/dump-gpt.sh private/gpt` | `layout.json` |
| 9 | Inventaris hardware Android | `scripts/hw-diag.sh` | `private/hw-diag.txt` |
| 10 | Build iPadOS 17 | di `$HAKIOS_WORK/UniXNU`: `./unixnu defconfig pipa_defconfig -D ../UniXNU-pipa`, `./unixnu fetch`, `./unixnu ipsw fetch`, `./unixnu build kernel`, `build package`, `build firmware --uefi ../uefi-pipa`, `bootimg` | `out/pipa/…/boot.img` |
| 11 | Preflight | `scripts/preflight.sh --device --gpt private/gpt` | PREFLIGHT PASS |
| 12 | Boot sementara | `scripts/temp-boot.sh out/…/boot.img --yes --gpt private/gpt` | menu: Android default |
| 13 | Uji menu | biarkan 10 s → harus Android; ulangi, pilih iPadOS dengan Vol/Power | catat |
| 14 | Log boot | kembali di Android: `scripts/capture-boot-log.sh` | `logs/boot-*/` |
| 15 | Diagnostik | baris `gpu:`, `battery:`, touch, tombol di log; bandingkan dengan `private/hw-diag.txt` | STATUS.md |

Catat setiap hasil di `docs/STATUS.md` dengan tanggal, commit, build iPadOS, dan log. "Build PASS" tidak sama
dengan "boot di tablet".
