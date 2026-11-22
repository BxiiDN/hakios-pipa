#!/usr/bin/env bash
# BOOT-CHAIN IMAGES ONLY -- not a full backup. Copies boot, init_boot, vendor_boot, dtbo, vbmeta of both slots, streamed
# read-only to this PC (root), each checked for size, with SHA256SUMS, after checking this PC has room for them.
# Android's apps and files (userdata) are NOT copied by this script: a full backup is the owner's (docs/DUAL-BOOT.md).
# Writes private/backup/<build>/ and BACKUP-SCOPE.txt saying exactly what is there.
source "$(dirname "$0")/adb-lib.sh"
need_android; need_root
build=$(adb shell getprop ro.build.version.incremental | tr -d '\r')
B=$PRIVATE/backup/$build; mkdir -p "$B"
list=(); total=0
for part in boot init_boot vendor_boot dtbo vbmeta vbmeta_system; do
	for slot in _a _b; do
		size=$(su_cmd "blockdev --getsize64 /dev/block/by-name/$part$slot 2>/dev/null" || true)
		[ -n "$size" ] && [ "$size" -gt 0 ] 2>/dev/null || continue
		list+=("$part$slot"); total=$((total + size))
	done
done
[ ${#list[@]} -gt 0 ] || die "no boot-chain partitions found by name"
free=$(df -B1 --output=avail "$B" | tail -1)
say "boot-chain images: ${#list[@]}, $((total / 1048576)) MiB; free here: $((free / 1048576)) MiB"
[ "$free" -gt $((total * 2)) ] || die "not enough room on this PC (need twice $((total / 1048576)) MiB)"
for p in "${list[@]}"; do stream_part "$p" "$B/$p.img" || die "$p: incomplete copy"; say "$p: ok"; done
(cd "$B" && sha256sum *.img > SHA256SUMS && sha256sum -c --quiet SHA256SUMS) || die "backup does not verify"
slot=$(adb shell getprop ro.boot.slot_suffix | tr -d '\r')
{ echo "scope: boot-chain partition images only (${list[*]})"
  echo "NOT included: userdata (apps, files), super (system/vendor), firmware, persist, modem calibration"
  echo "build: $build  active slot: $slot  date: $(date -u +%FT%TZ)"; } > "$B/BACKUP-SCOPE.txt"
used=$(adb shell df -k /data | tail -1 | awk '{print $3}')
say "verified: $B (SHA256SUMS). Android data in use: $((used / 1048576)) GB, not backed up by this script"
say "for a plan that writes boot_X: backup_sha256 = $(grep " boot$slot.img" "$B/SHA256SUMS" | cut -d' ' -f1)"
