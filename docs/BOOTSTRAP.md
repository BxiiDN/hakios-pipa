# Bootstrap dua tahap kernel pipa

## Kenapa perlu

Tiga builder di port EsaiJJ/UniXNU-pipa memeriksa driver-nya terhadap kernel yang **sudah di-prelink**:

| Builder | Yang dibaca dari kernel referensi | Kalau referensi tidak ada |
| --- | --- | --- |
| `build-sheng-hid-input.py` (archive `component:ShengHidInput`) | `build/xnu-prelink/native-owner-ufs-cpu-desktop-*-candidate.macho` + plan `.json` | Gagal: "No reference candidate available" |
| `build-gop-legacy-display.py` | `out/…/kernel/kernel.macho`, disalin ke `…-pipa-candidate.macho`; builder ini juga memanggil builder HID | Gagal: "Missing board kernel" |
| `build-platform-power.py` | `out/…/kernel/kernel.macho` | Rancangan port sendiri: `sheng_pmgr_run` no-op dan pesan "Build the kernel again to link the bridge" |

Isi referensi yang dipakai, dari audit source:

- **Alamat binding** (`IOHIDDevice` C2/D2, `gMetaClass`, vtable, dan slot >= 168) adalah alamat di kext
  **asli** IOHIDFamily dari kernelcache 21H461. Alamat ini hanya bergantung pada kernelcache dan slide
  (`-0x1000000`), tidak pada layout kernel native.
- **Hash `__TEXT_EXEC` IOHIDFamily** (`7e4c5104…`) diambil dari plan prelink.
- **Simbol native** (`__ZTV9IOService`, `___cxa_pure_virtual`, IOService C2/D2) hanya dipakai untuk mengecek
  bahwa kandidat itu sendiri konsisten: vtable asli yang sudah di-rebind harus menunjuk ke IOService native milik
  kandidat yang sama.

Jadi kernel referensi tidak harus kernel akhir. Syaratnya: hasil prelink UniXNU yang sungguhan, dari kernelcache
yang sama dan slide yang sama. Setelah kernel akhir jadi, binding tetap dicek ulang.

## Tahapan (`scripts/kernel-two-stage.sh`, job `macos-kernel`)

1. **Tahap A** menerapkan `patches/stage-a/0001` ke port. Patch ini menghapus dua baris archive
   (`component:ShengHidInput`, `build-gop-legacy-display.py`) dan mengubah `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` menjadi `n`.
   Setelah itu `./unixnu build kernel` membangun XNU, archive lain, link final, dan prelink.
   `tools/candidate_provenance.py record` lalu menolak kandidat yang bukan output prelinker. Yang diperiksa:
   sha256 kandidat = `candidate_sha256` di plan, `images_modified=false`, hash IOHIDFamily asli, extent
   IOHIDFamily `__TEXT_EXEC`, Mach-O arm64, `__TEXT` sejajar 16 KiB, dan ekspor wajib.
   Provenance mencatat commit, hash patch tahap A, dan `boot_candidate: false`. Patch kemudian dicabut lagi.
2. **Tahap B** memasang kandidat tahap A (`…-stagea-candidate.macho`) setelah diverifikasi ulang, lalu membangun
   board lengkap tanpa satu pun pemeriksaan ABI port yang dilemahkan.
3. **Recheck** menjalankan builder HID asli sekali lagi dengan kernel akhir sebagai referensi.
   `compare-bindings` menuntut binding, slot milik driver, ukuran instance, dan hash teks yang identik.

## Batasan tahap A

Kernel tahap A **bukan image boot**. Tahap A tidak memuat:

- touch (`ShengHidInput`);
- archive display legacy, yang juga membawa USB, Wi-Fi, Bluetooth, touch Novatek, tombol, dan objek firmware GMU/SQE/ZAP;
- jembatan PMGR (no-op dari port).

Kernel ini dan kernel akhir mengandung kext Apple, jadi tidak diunggah. Yang diunggah sebagai artefak hanya
plan, provenance, daftar ekspor, hash, dan log.

Test: `tests/test_candidate_provenance.py`, dengan kasus negatif untuk hash salah, file diubah setelah prelink,
arsitektur salah, layout `__TEXT` tidak sejajar, simbol hilang, IOHIDFamily lain, `images_modified`, provenance
kernel lain, input hilang, binding bergeser, binding hilang, layout berbeda, dan recheck terhadap referensi yang sama.
