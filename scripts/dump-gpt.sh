#!/usr/bin/env bash
# Read-only copy of each UFS LUN's primary GPT (the first 6 sectors of 4096 bytes) from a rooted Android, for
# tools/pipa_gpt.py. It reads /dev/block/sd[a-h] with dd if=... and writes only to /sdcard and to this PC.
#   dump-gpt.sh OUTDIR
source "$(dirname "$0")/lib.sh"
need adb
OUT=${1:?usage: dump-gpt.sh OUTDIR}; mkdir -p "$OUT"
[ "$(adb get-state 2>/dev/null)" = device ] || die "no Android device on adb"
[ "$(adb shell getprop ro.product.device | tr -d '\r')" = pipa ] || die "the connected device is not pipa"
for lun in a b c d e f g h; do
	adb shell "su -c 'test -b /dev/block/sd$lun'" 2>/dev/null || continue
	adb shell "su -c 'dd if=/dev/block/sd$lun of=/sdcard/gpt-sd$lun.bin bs=4096 count=6'" >/dev/null
	adb pull -q "/sdcard/gpt-sd$lun.bin" "$OUT/sd$lun.bin"
	adb shell "rm /sdcard/gpt-sd$lun.bin"
	say "sd$lun: $(python3 "$ROOT/tools/pipa_gpt.py" read "$OUT/sd$lun.bin" | grep -c '"name"') partitions"
done
python3 "$ROOT/tools/pipa_gpt.py" read "$OUT"/*.bin > "$OUT/layout.json"
say "layout: $OUT/layout.json; keep these files private (they identify the tablet)"
