# Windows 11 + WSL2 Ubuntu

1. PowerShell (admin): `wsl --install -d Ubuntu-24.04`, lalu buka Ubuntu.
2. Clone **di dalam WSL** (`~`), bukan di `/mnt/c`: lebih cepat dan mode file benar.
   ```sh
   git clone https://github.com/BxiiDN/hakios-pipa ~/hakios-pipa && cd ~/hakios-pipa
   git checkout pipa-bringup
   scripts/wsl-setup.sh --install
   ```
3. Build dan cek: `scripts/build.sh` (log di `logs/`, ringkasan `logs/build-summary.txt`),
   `scripts/build-uboot.sh` untuk boot manager.
4. USB ke tablet, pilih salah satu:
   - usbipd-win: PowerShell `winget install usbipd`, `usbipd list`, `usbipd bind --busid X-Y`,
     `usbipd attach --wsl --busid X-Y`. Ulangi attach saat tablet pindah mode (Android → fastboot mengganti ID USB).
   - atau `adb`/`fastboot` Windows (Platform Tools) dengan image dari `\\wsl$\Ubuntu-24.04\home\<user>\hakios-pipa\build\`.
5. Kernel XNU butuh iPhoneOS SDK (`IPHONEOS_SDK=/path`); tanpa itu `build.sh` menulis BLOCKED, bukan FAIL.

Untuk Claude Code: mulai dari `docs/STATUS.md` ("Langkah berikutnya") dan jalankan `scripts/build.sh` dulu.
