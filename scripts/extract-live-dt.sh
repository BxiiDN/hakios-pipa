#!/usr/bin/env bash
# The tablet's live device tree and the panel it booted with: read-only, streamed to this PC (root needed for
# /sys/firmware/fdt; no file is written on the tablet). Then the hardware facts held to what this repository assumes.
source "$(dirname "$0")/adb-lib.sh"
need_android; need_root
stream /sys/firmware/fdt "$PRIVATE/fdt.dtb"
head -c 4 "$PRIVATE/fdt.dtb" | od -An -tx1 | grep -q 'd0 0d fe ed' || die "what arrived is not a device tree blob"
su_cmd 'cat /proc/cmdline' | tr ' ' '\n' > "$PRIVATE/cmdline.txt"
panel=$(grep -oE 'msm_drm.dsi_display0=[^ ]+' "$PRIVATE/cmdline.txt" || true)
echo "${panel:-unknown}" > "$PRIVATE/panel.txt"
say "panel: ${panel:-not on the command line (record it by hand before choosing touch firmware)}"
sha256sum "$PRIVATE/fdt.dtb" | tee "$PRIVATE/fdt.dtb.sha256"
if command -v dtc >/dev/null; then
	dtc -q -I dtb -O dts "$PRIVATE/fdt.dtb" -o "$PRIVATE/phone.dts"
	python3 "$ROOT/tools/pipa_hw_facts.py" "$PRIVATE/phone.dts" > "$PRIVATE/hw-facts.json"
	python3 "$ROOT/tools/pipa_hw_facts.py" "$PRIVATE/phone.dts" --check || say "a fact differs from what the repository assumes: read private/hw-facts.json"
else
	die "dtc missing: scripts/wsl-setup.sh --install, then run this again"
fi
