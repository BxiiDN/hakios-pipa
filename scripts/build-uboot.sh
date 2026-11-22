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
# reproducible: U-Boot stamps its build time; take it from the U-Boot commit instead
export SOURCE_DATE_EPOCH=$(git -C "$UB_SRC" log -1 --format=%ct)
LOADER=$K/arch/arm64/boot/loader.efi
[ -f "$LOADER" ] || (cd "$K" && arch/arm64/boot/build.sh)
mkdir -p "$ROOT/build"
A=$ROOT/logs/uboot-artifacts.txt; : > "$A"
# Both rounds build in the same output directory (U-Boot records its build paths), each from an empty one; what a
# round made is moved to u-boot-pipa-roundN before the next starts.
BUILD=$WORK/u-boot-pipa-build
for round in 1 2; do
	rm -rf "$BUILD" "$WORK/u-boot-pipa-round$round"
	(cd "$U" && source ./env.sh && U_BOOT_OUT="$BUILD" u-boot/build.sh xiaomi/pipa) > "$ROOT/logs/uboot-build$round.log" 2>&1 \
		|| { tail -30 "$ROOT/logs/uboot-build$round.log"; die "U-Boot build $round failed (logs/uboot-build$round.log)"; }
	DTB=$(find "$BUILD" -name 'sm8250-xiaomi-pipa.dtb' | head -1)
	[ -n "$DTB" ] || die "build $round made no sm8250-xiaomi-pipa.dtb"
	python3 "$U/u-boot/pack.py" --u-boot "$BUILD/u-boot.bin" --loader "$LOADER" --dtb "$DTB" -o "$BUILD/hakios-pipa-bootmgr.img" >/dev/null
	for f in "$BUILD/u-boot" "$BUILD/u-boot.bin" "$DTB" "$BUILD/hakios-pipa-bootmgr.img"; do
		echo "build$round $(sha256sum "$f" | cut -d' ' -f1) $(stat -c %s "$f") ${f#$BUILD/}" >> "$A"
	done
	mv "$BUILD" "$WORK/u-boot-pipa-round$round"
done
cat "$A"
# 1. the two clean builds are identical; if not, say which files and where the first bytes differ
if ! diff <(awk '$1=="build1" {print $2, $4}' "$A") <(awk '$1=="build2" {print $2, $4}' "$A"); then
	for f in u-boot u-boot.bin; do
		cmp "$WORK/u-boot-pipa-round1/$f" "$WORK/u-boot-pipa-round2/$f" | head -1 || true
	done
	strings "$WORK/u-boot-pipa-round1/u-boot.bin" | grep -E 'U-Boot 20|\(.*[0-9]{4} - [0-9:]+' | head -3 || true
	strings "$WORK/u-boot-pipa-round2/u-boot.bin" | grep -E 'U-Boot 20|\(.*[0-9]{4} - [0-9:]+' | head -3 || true
	die "the two clean builds differ (logs/uboot-artifacts.txt)"
fi
say "PASS  two clean builds identical"
OUT=$WORK/u-boot-pipa-round1
DTB=$(find "$OUT" -name 'sm8250-xiaomi-pipa.dtb' | head -1)
# 2. no unresolved symbols in the linked ELF
undef=$(aarch64-linux-gnu-nm -u "$OUT/u-boot" | grep -v ' w ' || true)
[ -z "$undef" ] && say "PASS  no unresolved symbols" || { echo "$undef"; die "unresolved symbols in u-boot"; }
# 3. the target, the tree and the safety switches, from the build's own .config
for want in CONFIG_ARCH_SNAPDRAGON=y CONFIG_CLK_QCOM_SM8250=y CONFIG_PINCTRL_QCOM_SM8250=y CONFIG_BUTTON_QCOM_PMIC=y \
            CONFIG_BUTTON_REMAP_PHONE_KEYS=y CONFIG_CMD_BOOTMENU=y CONFIG_CMD_HAKIOS=y \
            'CONFIG_DEFAULT_DEVICE_TREE="qcom/sm8250-xiaomi-pipa"'; do
	grep -qx "$want" "$OUT/.config" || die ".config lacks $want"
done
for off in CONFIG_FASTBOOT_FLASH CONFIG_CMD_USB_MASS_STORAGE; do
	grep -qx "# $off is not set" "$OUT/.config" || die "$off is not off in .config"
done
say "PASS  .config: SM8250, pipa tree, PMIC keys remapped, bootmenu, HakiOS; flash and UMS off"
# 4. the menu compiled into the binary: Android default, 10 s, the three entries
python3 - "$OUT/u-boot.bin" "$ROOT/uefi-profiles/xiaomi/pipa/u-boot/files/board/xiaomi/pipa.env" <<'PY'
import sys
blob = open(sys.argv[1], 'rb').read()
for want in (b'bootmenu_default=0', b'bootmenu_delay=10', b'bootcmd=bootmenu', b'bootmenu_0=Android',
             b'bootmenu_1=HakiOS', b'bootmenu_2=Recovery or Fastboot', b'stdin=serial,button-kbd'):
    if want not in blob:
        sys.exit(f'u-boot.bin: the compiled-in environment lacks {want.decode()}')
print('PASS  compiled-in environment: Android default, 10 s, Android / HakiOS / Recovery, keys on stdin')
PY
# 5. the tree in the image is pipa's
grep -qa 'xiaomi,pipa' "$DTB" && say "PASS  device tree compatible xiaomi,pipa" || die "the packed tree is not pipa's"
cp "$OUT/hakios-pipa-bootmgr.img" "$OUT/u-boot.bin" "$ROOT/build/"
python3 "$ROOT/tools/verify_bootimg.py" "$ROOT/build/hakios-pipa-bootmgr.img"
say "built: build/hakios-pipa-bootmgr.img (for fastboot boot only; not tested on the tablet)"
