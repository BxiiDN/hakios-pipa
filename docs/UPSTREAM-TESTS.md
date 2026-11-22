# Host test HakiOS: baseline dan perbaikan

| Pohon | `tools_test` | `maintainers_test` | `workbench/run.sh` | lint |
| --- | --- | --- | --- | --- |
| Parent `958c773`, murni | PASS | FAIL (`arch/arm64/boot/u-boot/BASE` tidak dimiliki entri MAINTAINERS) | — | — |
| `62e09f8`, murni | FAIL (tautan ke `arch/arm64/boot/u-boot/README.md`, 5 rujukan `arch/arm64/boot/uefi/`) | FAIL (`LOADER: F: arch/arm64/boot/uefi/ names nothing`) | exit 1 | FAIL |
| `62e09f8` + `patches/upstream/0001` | PASS | PASS | **exit 0** | FAIL (hanya old-name, lihat bawah) |
| `62e09f8` + patch + paket pipa | PASS | PASS | **exit 0** | sama |

**Penyebab:** source upstream. Commit `62e09f8` memindahkan `arch/arm64/boot/uefi/` dan `arch/arm64/boot/u-boot/`
ke repository pendamping, tapi dokumen, entri `LOADER` di MAINTAINERS, dan komponen `mu-silicium`
(`pinned-in = "arch/arm64/boot/uefi/BASE"`) masih menunjuk ke sana. Bukan test yang rusak, bukan dependency,
toolchain, platform Linux, atau integrasi pipa (gagal sama persis tanpa pipa).

**Perbaikan** (`patches/upstream/0001-Documentation-MAINTAINERS-components-drop-references.patch`, terpisah dari
paket pipa, diterapkan oleh `scripts/fetch-upstream.sh`; `HAKIOS_UPSTREAM_PATCHES=0` untuk baseline murni):
dokumen menunjuk ke `oosexgang/hakios-uefi`, pola MAINTAINERS yang kosong dihapus, pin Mu-Silicium yang filenya
sudah tidak ada dihapus. Tidak ada test yang diubah atau dilewati.

**Tidak diperbaiki:** lint `old name` — banner "HackiOS" yang ditambahkan upstream sendiri di `a6d538c`
(`arch/arm64/boot/src/console.c`, `arch/arm64/boot/README.md`). Itu keputusan branding upstream.

CI: job `upstream-host-tests` (dengan patch, harus lulus) dan `upstream-baseline` (murni, `continue-on-error`).

## `init_test` sebagai pengguna biasa (temuan CI pertama, 23 Nov 2026)

Di runner GitHub (bukan root) `workbench/run.sh` gagal satu cek: `init_test.c:512`, "dark appearance: Success".
Direproduksi di sini dengan `setpriv --reuid=65534`: 1910 cek, 1 gagal; sebagai root: 1920 cek, 0 gagal.
Penyebab: `put_preferences` (`init/init.c`) memanggil `fchown(fd, 501, 501)`, yang hanya berhasil sebagai root (init di
tablet berjalan sebagai root); test baris 512 tidak dijaga `as_root` seperti cek kepemilikan lainnya. Pesan "Success"
berasal dari `errno` yang dibaca setelah `close()`. Jadi: asumsi test upstream terhadap platform, bukan integrasi pipa.
CI menjalankan suite sebagai root, lalu menjalankan `init_test` sebagai pengguna biasa dan mewajibkan tepat kegagalan
yang sudah diketahui ini.
