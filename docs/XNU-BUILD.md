# Build XNU 10063 (UniXNU) untuk pipa: status dan dependency

**Status: BLOCKED — kernel belum pernah dikompilasi di sesi mana pun.** Tidak ada klaim build.

## Kenapa belum dibangun

| Kebutuhan | Keadaan di sesi 3 |
| --- | --- |
| Toolchain Linux UniXNU (`scripts/linux/setup-toolchain.py`): clang dari llvm-project `58c46bae` dengan patch `__builtin_xnu_type_*`, cctools-port `1030.6.3-ld64-956.6` (ld64), `bootstrap_cmds-138` (mig), iig-port `ea6d147d`, lzfse `e634ca58`, libdispatch `swift-6.4.0-RELEASE` | Tidak bisa dipasang: lingkungan sesi ini menolak instalasi paket, dan membangun tool dari source juga ditolak pengamannya (dicoba sekali untuk flex 2.6.4; tidak diulang) |
| Paket host (`--print-packages`): `git patch flex bison bzip2 cpio rsync curl wget ca-certificates tcsh unifdef cmake clang lld mtools build-essential pkg-config ninja-build python3 python3-dev xz-utils libssl-dev zlib1g-dev libbsd-dev uuid-dev llvm-dev libclang-dev device-tree-compiler` | Sebagian ada (clang 18, lld, cmake, ninja, bison); flex, dtc, mtools, tcsh, unifdef tidak |
| Input IPSW: `iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw`, produk **iPad7,1** (iPad Pro 12.9" gen 2, `j120ap`), build **21H461**; anggota `KernelCache`, `DeviceTree`, `StaticTrustCache`, `Cryptex1,SystemTrustCache`; dmg `044-76040-038` `3f99b859…`, `044-76034-038` `b4908cde…`; kernelcache `f18b4df8…` (semua di `profiles/os/ipados-17.7.11-21H461/profile.toml`) | Tidak diunduh di sini. `./unixnu ipsw info` / `ipsw fetch` memverifikasi model, build dan digest di mesin pemilik |

Userland yang dipakai adalah IPSW **iPad** (iPad7,1), bukan iPhone; idiom `pad` ditulis di ADT oleh profil.

## Perintah di WSL2 (Claude Code)

```sh
scripts/wsl-setup.sh --install --mu-silicium      # paket apt + venv Mu-Silicium
scripts/wsl-setup.sh --unixnu-toolchain           # LLVM patched + cctools: berjam-jam, sekali
scripts/fetch-unixnu.sh                           # pin + patch 0001/0002 (Android-first, root di "ipados")
cd "$HAKIOS_WORK/UniXNU"
./unixnu defconfig pipa_defconfig -D ../UniXNU-pipa
./unixnu fetch && ./unixnu status --json          # revisi, urutan patch, path
./unixnu ipsw info && ./unixnu ipsw fetch         # model iPad7,1, 21H461, digest
./unixnu build kernel  2>&1 | tee ../logs-kernel.txt   # simpan semua error compile/link
./unixnu build package && ./unixnu build firmware --uefi ../uefi-pipa && ./unixnu bootimg -D ../UniXNU-pipa
cd - && python3 tools/storage_safety.py "$HAKIOS_WORK/UniXNU" "$HAKIOS_WORK/UniXNU-pipa"
python3 tools/verify_bootimg.py --unixnu "$HAKIOS_WORK/UniXNU/out/pipa/…/boot.img"
scripts/readiness.sh --gpt private/gpt --device
```

Build kernel UniXNU juga memverifikasi simbol PMGR (`_sheng_pmgr_run`) untuk root UFS (`check_native_root`).
Periksa ulang reproducibility dengan dua `build kernel` bersih dan bandingkan `kernelcache_sha256`/`payload.json`.
