#!/usr/bin/env bash
# Collect the private firmware for a LOCAL stage-B build (docs/BOOTSTRAP.md). Runs on the owner's PC (WSL2 with adb
# from scripts/wsl-setup.sh). Never in public CI; nothing here is committed.
#
#   collect-firmware.sh adb             tablet booted into Android, USB debugging on, exactly one device
#   collect-firmware.sh rom DIR         DIR = images/ of an unpacked official pipa_global_images_*.tgz (touch firmware
#                                       from the stock boot.img kernel; no tablet needed)
#   collect-firmware.sh vendor IMG      IMG = vendor.img (EROFS) of the same official ROM, e.g. from its payload.bin:
#                                       the Adreno 650 GMU/SQE/ZAP images of /vendor/firmware when adb cannot read
#                                       /vendor (SELinux, no root). Needs fsck.erofs (FSCK_EROFS or on PATH).
#   collect-firmware.sh check           firmware_check.py on what is staged
#
# Audited (hakios-pipa session 6): EsaiJJ/UniXNU-pipa scripts/extract-pipa-firmware.py only runs getprop, ls, cat,
# od, tr, find, awk, readlink, "wm size"/"wm density" (queries) and adb pull / exec-out cat; it writes only to its
# --out directory. It refuses a device whose ro.product.device is not pipa. No root, no reboot, no flash.
source "$(dirname "$0")/lib.sh"
P=$WORK/UniXNU-pipa
PRIVATE=${HAKIOS_PRIVATE:-$HOME/.hakios-private}   # outside every Git checkout
STAGE=$P/.cache/firmware                            # ignored by the port's .gitignore (.cache/)
mode=${1:?usage: collect-firmware.sh adb|rom DIR|vendor IMG|check}
case "$PRIVATE" in "$ROOT"/*|"$P"/*) die "HAKIOS_PRIVATE must be outside the Git checkouts";; esac
git -C "$P" check-ignore -q "$STAGE/gpu/x" || die "$STAGE is not ignored by Git in $P; refusing to stage firmware there"
mkdir -p "$PRIVATE" && chmod 700 "$PRIVATE"

stage() {  # stage SRC REL: copy one input into the ignored build path
	[ -f "$1" ] || { say "not found: $1"; return 0; }
	mkdir -p "$(dirname "$STAGE/$2")"; cp "$1" "$STAGE/$2"; say "staged $2 ($(shasum -a 256 "$1" | cut -c1-16)...)"
}
case $mode in
adb)
	need adb
	python3 "$P/scripts/extract-pipa-firmware.py" --out "$PRIVATE/pipa-firmware"
	src=$PRIVATE/pipa-firmware/root/vendor/firmware
	for f in a650_gmu.bin a650_sqe.fw a650_zap.elf; do stage "$src/$f" "gpu/$f"; done
	[ -f "$src/a650_zap.elf" ] || [ ! -f "$src/a650_zap.mdt" ] || say "only the split ZAP image (.mdt/.b0N) is on this ROM; do not rename it"
	;;
rom)
	dir=${2:?collect-firmware.sh rom IMAGES_DIR}
	# needs vmlinux-to-elf (VMLINUX_TO_ELF or on PATH) to read the kernel's built-in firmware table
	python3 "$P/scripts/extract-stock-firmware.py" --images "$dir" --touch --out "$PRIVATE/pipa-stock"
	stage "$(find "$PRIVATE/pipa-stock" -name novatek_nt36532_m82_fw_csot.bin -type f | head -1)" touch/novatek_nt36532_m82_fw_csot.bin
	;;
vendor)
	img=${2:?collect-firmware.sh vendor VENDOR_IMG}
	erofs=${FSCK_EROFS:-$(command -v fsck.erofs || true)}
	[ -x "$erofs" ] || die "fsck.erofs not found (set FSCK_EROFS)"
	[ "$(head -c 1028 "$img" | tail -c 4 | od -An -tx4 | tr -d ' ')" = e0f5e1e2 ] || die "$img is not an EROFS image"
	out=$PRIVATE/vendor-$(sha256sum "$img" | cut -c1-16)
	if [ ! -d "$out/firmware" ]; then rm -rf "$out.tmp"; mkdir -p "$out.tmp"; "$erofs" --extract="$out.tmp" "$img"; mv "$out.tmp" "$out"; fi
	{ echo "vendor.img sha256 $(sha256sum "$img" | cut -d' ' -f1) $(stat -c %s "$img") bytes"
	  (cd "$out/firmware" && sha256sum a650_*); } > "$out.provenance.txt"
	for f in a650_gmu.bin a650_sqe.fw a650_zap.elf; do stage "$out/firmware/$f" "gpu/$f"; done
	;;
check) ;;
*) die "unknown mode $mode" ;;
esac
python3 "$ROOT/tools/firmware_check.py" "$STAGE" --pins "$P/proprietary-files.txt" $(for m in "$ROOT"/manifests/pipa-official-rom-*.txt; do printf -- "--pins %s " "$m"; done) --json "$PRIVATE/firmware-check.json"
