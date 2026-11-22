#!/usr/bin/env bash
# Linux's sm8250-xiaomi-pipa.dts with its includes merged, as tools/boards.py new/compare --dts reads it.
# mkdts.sh LINUX-CHECKOUT OUT.dts   (needs clang or cpp; no dtc)
set -euo pipefail
L=${1:?usage: mkdts.sh LINUX-CHECKOUT OUT.dts}; OUT=${2:?usage: mkdts.sh LINUX-CHECKOUT OUT.dts}
D=$L/arch/arm64/boot/dts/qcom
[ -f "$D/sm8250-xiaomi-pipa.dts" ] || { echo "mkdts.sh: no $D/sm8250-xiaomi-pipa.dts" >&2; exit 1; }
CPP=(clang -E); command -v clang >/dev/null || CPP=(cpp)
"${CPP[@]}" -P -nostdinc -undef -D__DTS__ -x assembler-with-cpp -I "$L/include" -I "$D" -I "$L/include/dt-bindings" \
	"$D/sm8250-xiaomi-pipa.dts" -o "$OUT"
grep -q 'compatible = "xiaomi,pipa"' "$OUT" || { echo "mkdts.sh: $OUT is not pipa's tree" >&2; exit 1; }
echo "mkdts.sh: $OUT ($(wc -l < "$OUT") lines)"
