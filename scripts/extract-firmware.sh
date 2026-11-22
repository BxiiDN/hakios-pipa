#!/usr/bin/env bash
# Copies the firmware files named in a manifest from the tablet's own /vendor (read-only, no root for most), then
# checks their digests. The files stay in private/firmware/ and are never committed.
#   extract-firmware.sh [MANIFEST]
source "$(dirname "$0")/adb-lib.sh"
need_android
MANIFEST=${1:-$ROOT/manifests/unixnu-pipa-proprietary-files.txt}
mkdir -p "$PRIVATE/firmware"
grep -v '^#' "$MANIFEST" | awk -F'|' 'NF==4 {gsub(/ /,"",$1); print $1}' | while read -r rel; do
	name=$(basename "$rel")
	for dir in /vendor/firmware /vendor/firmware_mnt/image /vendor/bt_firmware/image /vendor/etc/wifi/qca6390; do
		if adb shell "test -f $dir/$name" 2>/dev/null; then adb pull -q "$dir/$name" "$PRIVATE/firmware/$name" && say "pulled $dir/$name"; break; fi
	done
done
python3 "$ROOT/tools/firmware_manifest.py" "$MANIFEST" "$PRIVATE/firmware" || say "some files missing or different (see above): the touch firmware is inside the stock boot.img kernel"
