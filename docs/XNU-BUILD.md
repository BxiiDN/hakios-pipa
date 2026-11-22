# Build XNU 10063 (UniXNU) untuk pipa: status dan dependency

**Status (sesi 4): FAIL di tahap archive driver ke-8 (`ShengHidInput`).** Kernel XNU 10063.141.1 sudah dikompilasi
di CI (bootstrap pass). Kernel final belum di-link dan belum di-prelink. Belum ada `kernel.macho`.

Host build: GitHub Actions `macos-26`, Xcode 26.6 (Apple clang 21.0.0), SDK iphoneos 26.5. Jalurnya sama dengan
`.github/workflows/macos.yml` milik UniXNU sendiri. Workflow: `.github/workflows/unixnu-build.yml`.

## Jejak kegagalan dan perbaikan (bukti CI)

| Run | Tahap terjauh | Penyebab | Tindakan |
| --- | --- | --- | --- |
| [45077836807](https://github.com/BxiiDN/hakios-pipa/actions/runs/45077836807) (UniXNU `8542980`) | preflight | `ArmCpu/ArmCpuSleep.h` wajib sejak UniXNU 2e64418, tidak ada di port; `build-verified-root-key.py` tidak ada | Diagnosis lokal (bawah) |
| sama, varian diagnostik | patch XNU ke-64 | `pipa-cryptex-os-view-always.patch` gagal di `kern_exec.c:7642`: UniXNU **4a41c7e** (10 Nov 2026) membuang prefix `sheng-` dari semua boot-arg (`sheng-gpu-addon` → `gpu-addon`), sedangkan port c4c1a3a (13 Nov) masih memakai nama lama | **Pin UniXNU diganti ke `62f203c`** (9 Nov, commit tepat sebelum rename). Diuji lokal: 64/64 patch XNU berlaku, patch dual-boot berlaku, profil iPadOS 17.7.11 memakai xnu `d8b80295` yang sama |
| [45079043160](https://github.com/BxiiDN/hakios-pipa/actions/runs/45079043160) (`62f203c`) | preflight PASS, 64 patch PASS, bootstrap compile XNU PASS, archive ke-1 | Port memakai `-Wno-unused-but-set-global` (ada di LLVM upstream, tidak ada di Apple clang 21) dengan `-Werror` | Patch `unixnu-pipa/0003`: `-Wno-unknown-warning-option` di 5 builder |
| sama | — | `build-verified-root-key.py` tidak ada di repositori publik mana pun (riwayat penuh UniXNU, kedua port, GitHub code search) | 0003 menambah builder sesuai kontrak VerifiedRoot ([OWNER-KEY.md](OWNER-KEY.md)) |
| [45080236671](https://github.com/BxiiDN/hakios-pipa/actions/runs/45080236671) | archive 1–7 PASS (`ArmDTPlatform`, `ArmCpu`, `SoftwareAES`, `RamBlock`, `VirtioMmioBlock --verified-root`, `libVerifiedRootKey.a` kunci ephemeral `9c76d702…`, `ShengUfs`, `AppleKeyStoreState`) | `build-sheng-hid-input.py`: "No reference candidate available" | **Belum diperbaiki**, lihat bawah |

"Link failed" pada bootstrap pass (simbol `_sheng_pmgr_run`, `_native_verified_root_probe`, dan lainnya) sudah
diperkirakan. Pass itu hanya menghasilkan compile record, dan simbol-simbol tersebut berasal dari archive driver
yang dibangun sesudahnya.

## Blocker berikutnya: kandidat referensi HID

`build-sheng-hid-input.py` milik port memeriksa ABI `IOHIDDevice` asli terhadap kernel yang **sudah di-prelink**
(`build/xnu-prelink/native-owner-ufs-cpu-desktop-*-candidate.macho` beserta plan `.json`-nya). Builder ini juga
mengambil alamat binding dari kandidat tersebut. Kandidat itu artefak dari build lokal penulis port dan tidak ada di
repositori. Berarti diperlukan bootstrap dua tahap: prelink sekali tanpa `ShengHidInput` untuk membuat kandidat,
lalu build ulang dengan HID. Tahap 2 tidak boleh memakai alamat binding dari tahap 1 tanpa diverifikasi ulang,
karena layout kernel native bisa berubah. Belum dikerjakan.

## Toolchain Linux

Job `linux-toolchain` membangun toolchain UniXNU (`scripts/linux/setup-toolchain.py`): LLVM `58c46bae` dengan patch,
cctools-port `1030.6.3-ld64-956.6`, `bootstrap_cmds-138`, iig-port, lzfse dan libdispatch. Hasilnya dicache di
`/opt/unixnu-linux`. Jalur Linux tidak dibutuhkan untuk jalur macOS di atas.

## Input IPSW

`iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw`, produk **iPad7,1**, build **21H461**; kernelcache `f18b4df8…`. CI
mengunduhnya dari Apple saat build dan menghapusnya di akhir job. File itu tidak pernah diunggah sebagai artefak dan
tidak di-commit.

## Perintah lokal (Mac atau WSL2 dengan toolchain Linux)

```sh
scripts/fetch-unixnu.sh                            # pin + patch 0001..0003 (selalu diterapkan ulang)
export UNIXNU_OWNER_PUBLIC_KEY=owner/owner-public.pem UNIXNU_OWNER_KEY_SHA256=<anchor> UNIXNU_OWNER_KEY_KIND=owner
cd "$HAKIOS_WORK/UniXNU"
./unixnu defconfig pipa_defconfig -D ../UniXNU-pipa && ./unixnu fetch && ./unixnu status --json
./unixnu build kernel 2>&1 | tee ../logs-kernel.txt
```
