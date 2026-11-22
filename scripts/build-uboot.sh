#!/usr/bin/env bash
# The pipa boot manager: hakios-uefi's U-Boot with this repository's profile, packed for `fastboot boot` only.
source "$(dirname "$0")/lib.sh"
need git; need make; need flex; need bison; need aarch64-linux-gnu-gcc; need python3
U=$WORK/hakios-uefi; K=$WORK/hakios-xnu-kernel
[ -d "$U" ] && [ -d "$K" ] || "$ROOT/scripts/fetch-upstream.sh"
PROFILES=$WORK/uefi-profiles; rm -rf "$PROFILES"; cp -r "$ROOT/uefi-profiles" "$PROFILES"
OVERLAY=$PROFILES/xiaomi/pipa/u-boot/files
# hakios-uefi's build fetches U-Boot at its pinned BASE first (apply.sh); the defconfig is made from that tree
UB_BASE=$(cat "$U/u-boot/BASE")
UB_SRC=${U_BOOT_SRC:-$WORK/u-boot-$UB_BASE}
if [ ! -d "$UB_SRC/.git" ]; then git clone -q --depth 1 --branch "$UB_BASE" https://github.com/u-boot/u-boot "$UB_SRC"; fi
mkdir -p "$OVERLAY/configs"
cat "$UB_SRC/configs/qcom_defconfig" "$UB_SRC/board/qualcomm/qcom-phone.config" \
    "$PROFILES/xiaomi/pipa/pipa.config" > "$OVERLAY/configs/xiaomi_pipa_defconfig"
say "defconfig: qcom_defconfig + qcom-phone.config + pipa.config"
export HAKIOS_PROFILE_ROOT=$PROFILES KERNEL_ROOT=$K U_BOOT=$UB_SRC
(cd "$U" && source ./env.sh && u-boot/build.sh xiaomi/pipa)
OUT=$U/build/u-boot-pipa
DTB=$(find "$OUT" -name 'sm8250-xiaomi-pipa.dtb' | head -1)
[ -n "$DTB" ] || die "the build made no sm8250-xiaomi-pipa.dtb"
LOADER=$K/arch/arm64/boot/loader.efi
[ -f "$LOADER" ] || (cd "$K" && arch/arm64/boot/build.sh)
mkdir -p "$ROOT/build"
python3 "$U/u-boot/pack.py" --u-boot "$OUT/u-boot.bin" --loader "$LOADER" --dtb "$DTB" -o "$ROOT/build/hakios-pipa-bootmgr.img"
python3 "$ROOT/tools/verify_bootimg.py" "$ROOT/build/hakios-pipa-bootmgr.img"
say "built: build/hakios-pipa-bootmgr.img (for fastboot boot only)"
