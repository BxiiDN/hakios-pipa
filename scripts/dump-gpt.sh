#!/usr/bin/env bash
# Read-only copy of each UFS LUN's primary GPT (the first 6 sectors of 4096 bytes), streamed to this PC (root).
#   dump-gpt.sh OUTDIR
source "$(dirname "$0")/adb-lib.sh"
need_android; need_root
OUT=${1:?usage: dump-gpt.sh OUTDIR}; mkdir -p "$OUT"
for lun in a b c d e f g h; do
	su_cmd "test -b /dev/block/sd$lun && echo y" | grep -q y || continue
	adb exec-out "su -c 'dd if=/dev/block/sd$lun bs=4096 count=6 2>/dev/null'" > "$OUT/sd$lun.bin"
	[ "$(stat -c %s "$OUT/sd$lun.bin")" = 24576 ] || die "sd$lun: short read"
	say "sd$lun: $(python3 "$ROOT/tools/pipa_gpt.py" read "$OUT/sd$lun.bin" | grep -c '"name"') partitions"
done
python3 "$ROOT/tools/pipa_gpt.py" read "$OUT"/*.bin > "$OUT/layout.json"
(cd "$OUT" && sha256sum sd?.bin > SHA256SUMS)
say "layout: $OUT/layout.json; keep these files private (they identify the tablet)"
