#!/usr/bin/env bash
# Which mode the tablet is in and what it is, read-only. Writes private/device.txt.
source "$(dirname "$0")/adb-lib.sh"
out=$PRIVATE/device.txt; : > "$out"
if command -v adb >/dev/null && [ "$(adb get-state 2>/dev/null)" = device ]; then
	say "mode: Android (adb)"
	{ for p in ro.product.device ro.product.model ro.build.fingerprint ro.build.version.incremental ro.boot.slot_suffix \
	           ro.boot.verifiedbootstate ro.boot.flash.locked ro.boot.hwc ro.boot.hwversion; do
		echo "$p=$(adb shell getprop $p | tr -d '\r')"; done
	  echo "memtotal_kb=$(adb shell cat /proc/meminfo | awk '/MemTotal/ {print $2}')"
	  echo "data_df=$(adb shell df -k /data | tail -1 | tr -s ' ')"; } | tee -a "$out"
elif command -v fastboot >/dev/null && fastboot devices | grep -q .; then
	say "mode: fastboot"
	for v in product current-slot unlocked anti slot-count; do
		echo "$v=$(fastboot getvar $v 2>&1 | awk -F': ' "/^$v:/ {print \$2}")"; done | tee -a "$out"
else
	die "no tablet on adb or fastboot (WSL: usbipd attach; docs/WSL.md)"
fi
say "written: $out"
