#!/usr/bin/env bash
# The firmware files named in a manifest, copied from the tablet's own /vendor with adb pull (reads only; most need no
# root), then their digests checked. Panel-dependent files (touch firmware) are not chosen automatically: they are
# matched to the panel recorded by extract-live-dt.sh, or left out. The files stay in private/firmware/.
#   extract-firmware.sh [MANIFEST]
source "$(dirname "$0")/adb-lib.sh"
need_android
MANIFEST=${1:-$ROOT/manifests/unixnu-pipa-proprietary-files.txt}
panel=$(cat "$PRIVATE/panel.txt" 2>/dev/null || echo unknown)
mkdir -p "$PRIVATE/firmware"
grep -v '^#' "$MANIFEST" | awk -F'|' 'NF==4 {gsub(/ /,"",$1); print $1}' | while read -r rel; do
	name=$(basename "$rel")
	case $name in novatek_nt36532_*)
		maker=$(python3 "$ROOT/tools/panel_firmware.py" "$panel" 2>/dev/null || true)
		[ -n "$maker" ] && [ "$name" = "$maker" ] || { say "skip $name: panel '$panel' does not select it (tools/panel_firmware.py)"; continue; };;
	esac
	for dir in /vendor/firmware /vendor/firmware_mnt/image /vendor/bt_firmware/image /vendor/etc/wifi/qca6390; do
		if adb shell "test -f $dir/$name" 2>/dev/null; then adb pull -q "$dir/$name" "$PRIVATE/firmware/$name" && say "pulled $dir/$name"; break; fi
	done
done
python3 "$ROOT/tools/firmware_manifest.py" "$MANIFEST" "$PRIVATE/firmware" || say "some files missing or different (above); the touch firmware is inside the stock boot.img kernel"
