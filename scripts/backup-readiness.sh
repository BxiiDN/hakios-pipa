#!/usr/bin/env bash
# Is there a way back before anything is tried? Read-only: copies boot, vendor_boot, dtbo, vbmeta of both slots to
# the PC (dd if=, root), records their SHA-256, and checks the PC has room for a full copy of the user's files.
# It does not back up Android's user data for you: that is the owner's job (docs/DUAL-BOOT.md, Recovery plan).
source "$(dirname "$0")/adb-lib.sh"
need_android; need_root
B=$PRIVATE/backup/$(adb shell getprop ro.build.version.incremental | tr -d '\r'); mkdir -p "$B"
for part in boot vendor_boot dtbo vbmeta init_boot; do
	for slot in _a _b; do
		dev=/dev/block/by-name/$part$slot
		adb shell "su -c 'test -e $dev'" 2>/dev/null || continue
		su_cmd "dd if=$dev of=/sdcard/bk-$part$slot.img bs=4096" >/dev/null 2>&1
		adb pull -q "/sdcard/bk-$part$slot.img" "$B/$part$slot.img"; adb shell rm "/sdcard/bk-$part$slot.img"
	done
done
(cd "$B" && sha256sum *.img > SHA256SUMS) && say "boot images: $B (SHA256SUMS: put the active slot's boot hash in a plan's backup_sha256)"
used_kb=$(adb shell df -k /data | tail -1 | awk '{print $3}'); free_kb=$(df -k --output=avail "$PRIVATE" | tail -1)
say "Android data in use: $((used_kb / 1024 / 1024)) GB; free on this PC: $((free_kb / 1024 / 1024)) GB"
[ "$free_kb" -gt "$used_kb" ] && say "room for a full copy: yes" || say "WARNING: not enough room on this PC for a full copy of /data"
say "fastboot ROM to keep at hand: the same build as ro.build.version.incremental=$(basename "$B") (anti-rollback: scripts/detect-device.sh in fastboot)"
