# Audit repository sumber (22 Nov 2026)

## oosexgang/hakios-xnu-kernel

- Branch: `common` (default, HEAD `62e09f850f1f713192228cb9031da256033ede93`, 22 Nov 2026, "Prepare Darwin
  bring-up for companion loader repo"), `main` (`63fc2b46…`), `legacy-hackios` (`88513176…`), `mtk` (`a9627984…`).
  `hackios-xnu-kernel` mengarah ke repository yang sama.
- Kernel: Apple XNU `xnu-12377.121.6` (Darwin 26/27) + patch dan driver HakiOS. Status yang dicatat upstream:
  home screen Darwin 27.2 (24B119, file iPhone12,1) dan Darwin 26.6.2 di ponsel Snapdragon 7-series, dari RAM.
  Metal di Adreno 642L dengan `gpu=1 metal=1` (Documentation/metal-glass.md).
- `legacy-hackios`: XNU `xnu-8796.121.2` + iOS 16.5 (Darwin 22), POCO X5 Pro (redwood).
- Userland sudah berada di `userland/` repository ini; `oosexgang/hackios-xnu-userland` hanya penunjuk ("Moved").
- Lisensi: karya HakiOS MIT; bagian yang memperluas XNU APSL 2.0 (`NOTICE.md`). Tidak ada file Apple di repo;
  `tools/check-publishable.sh` memeriksanya.
- Build kernel butuh iPhoneOS SDK Apple (tidak bisa didistribusikan). Loader UEFI hanya butuh clang + lld.
- Dukungan SM8250 yang sudah ada: hanya cpufreq (`drivers/board/cpufreq.c`, tata letak OSM). Tidak ada paket SoC
  sm8250 sebelumnya. Driver GPU hanya keluarga A660 (642/642L/643): firmware `a660_*`, GMU chip id A660.
- Tidak ada driver USB, PCIe, backlight I2C, atau touch Novatek di `drivers/board/`.
- **Regresi upstream di 62e09f8:** `make check` gagal di lint dan dua host test (`tools_test`,
  `maintainers_test`) karena tautan ke `arch/arm64/boot/uefi/` dan `arch/arm64/boot/u-boot/` yang dipindah keluar
  repo oleh commit itu. Dibuktikan gagal juga tanpa paket pipa.
- Template CI yang dibuat `tools/device.py init` menunjuk `oosexgang/xnu-kernel-qcom`, yang tidak bisa di-clone
  publik; di repo ini diganti ke `oosexgang/hakios-xnu-kernel` dengan commit yang dipin.

## oosexgang/hakios-uefi

- HEAD `93e98ee8f8b9ca42f43dbbfd91b10566ba8d328c`. U-Boot `v2026.07` (`ece349ad…`) + `hakios.patch`
  (`CMD_HAKIOS`, `EFI_HAKIOS_USB_DEVICE`), `pack.py` (Android boot image untuk RAM boot), belum ada profil perangkat.
- Jalur SD card tidak berlaku untuk Pad 6 (tidak ada slot microSD).

## Sumber lain

- Linux mainline (`4843f687…`): `sm8250-xiaomi-pipa.dts` ada (Luka Panio, 2023). Mendeskripsikan: GPU + GMU + zap
  shader, backlight KTZ8866 (I2C11), tombol, UFS, USB, PCIe0, ADSP/CDSP/SLPI, simple-framebuffer di
  `cont_splash`. **Tidak** mendeskripsikan panel DSI, touch, stylus, audio amp, Wi-Fi/BT, sensor.
  `sm8250.dtsi` memakai `qcom,sm8250-cpufreq-epss`, berbeda dengan catatan HakiOS (OSM) — harus dilihat di hardware.
- U-Boot `v2026.07`: `clock-sm8250.c`, `pinctrl-sm8250.c`, `qcom_defconfig`, `qcom-phone.config` (boot menu,
  tombol sebagai input). Fastboot U-Boot tidak punya backend UFS.
- Mu-Silicium: HakiOS memakai port Mu-Silicium untuk ponsel pertamanya. Port Pad 6 tidak diverifikasi di sesi ini.
- Mesa Freedreno/Turnip: mendukung A650 di Linux; HakiOS memakai Mesa di Darwin untuk A660. Porting profil A650
  belum dilakukan.
- UniXNU-pipa (fork `BxiiDN/UniXNU-pipa`): proyek lain yang sudah menargetkan pipa; tidak diaudit di sesi ini.
