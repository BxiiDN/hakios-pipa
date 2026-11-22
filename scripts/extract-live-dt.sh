#!/usr/bin/env bash
# The tablet's live device tree and the panel it booted with, read-only (root needed for /sys/firmware/fdt), then the
# hardware facts held to what this repository assumes. Nothing of it is committed (private/).
source "$(dirname "$0")/adb-lib.sh"
need_android; need_root
su_cmd 'cat /sys/firmware/fdt > /sdcard/pipa-fdt.dtb'
adb pull -q /sdcard/pipa-fdt.dtb "$PRIVATE/fdt.dtb"; adb shell rm /sdcard/pipa-fdt.dtb
su_cmd 'cat /proc/cmdline' | tr ' ' '\n' > "$PRIVATE/cmdline.txt"
grep -E 'msm_drm.dsi_display0=|androidboot.(hwc|hwversion|panel)' "$PRIVATE/cmdline.txt" || say "no panel name on the command line"
sha256sum "$PRIVATE/fdt.dtb" | tee "$PRIVATE/fdt.dtb.sha256"
if command -v dtc >/dev/null; then
	dtc -q -I dtb -O dts "$PRIVATE/fdt.dtb" -o "$PRIVATE/phone.dts"
	python3 "$ROOT/tools/pipa_hw_facts.py" "$PRIVATE/phone.dts" > "$PRIVATE/hw-facts.json"
	python3 "$ROOT/tools/pipa_hw_facts.py" "$PRIVATE/phone.dts" --check || say "a fact differs from what the repository assumes: read private/hw-facts.json"
	say "compare with the HakiOS package: (cd \$HAKIOS_WORK/hakios-xnu-kernel && tools/boards.py compare pipa --dts $PRIVATE/phone.dts)"
else
	say "dtc missing: install it (scripts/wsl-setup.sh --install) and run: dtc -I dtb -O dts $PRIVATE/fdt.dtb"
fi
