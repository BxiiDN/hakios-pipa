#!/usr/bin/env bash
# UniXNU-pipa's A650GmuTests (package/A650Gmu.c: RSC/PDC setup, GMU firmware load, HFI start) for AArch64 little-endian,
# the only host the AdrenoFirmware HFI kit supports, run under QEMU user mode on x86. With the device's a650_gmu.bin
# when one is given (the firmware stays local), and with the test's built-in image.
#   a650-gmu-tests.sh [a650_gmu.bin]       QEMU_AARCH64=path/to/qemu-aarch64 (default: on PATH)
# Needs aarch64-linux-gnu-gcc and/or clang+lld. Evidence: $HAKIOS_EVIDENCE (default logs/a650-gmu).
source "$(dirname "$0")/lib.sh"
P=$WORK/UniXNU-pipa K=$WORK/UniXNU/kits/AdrenoFirmware
Q=${QEMU_AARCH64:-$(command -v qemu-aarch64 || true)}
[ -x "$Q" ] || die "no qemu-aarch64 (apt install qemu-user, or QEMU_AARCH64=...)"
[ -f "$P/package/A650GmuTests.c" ] && [ -f "$K/AdrenoHfiStartup.c" ] || die "pinned trees missing: scripts/fetch-unixnu.sh, then unixnu fetch"
EV=${HAKIOS_EVIDENCE:-$ROOT/logs/a650-gmu}; mkdir -p "$EV"
fw=${1:-}
[ -z "$fw" ] || [ -f "$fw" ] || die "no firmware at $fw"
src=("$P/package/A650GmuTests.c" "$P/package/A650Gmu.c" "$K/AdrenoFirmware.c" "$K/AdrenoHfi.c" "$K/AdrenoHfiStartup.c" "$K/AdrenoHfiVotes.c")
failed=0 ran=0
for cc in gcc clang; do
	case $cc in
	gcc) command -v aarch64-linux-gnu-gcc >/dev/null || continue; C=(aarch64-linux-gnu-gcc) ;;
	clang) command -v clang >/dev/null && command -v ld.lld >/dev/null || continue; C=(clang --target=aarch64-linux-gnu -fuse-ld=lld) ;;
	esac
	bin=$EV/a650-$cc
	"${C[@]}" -std=gnu11 -O1 -Wall -Werror -static -I "$P/package" -I "$K" -o "$bin" "${src[@]}" > "$EV/build-$cc.txt" 2>&1 \
		|| { cat "$EV/build-$cc.txt"; say "FAIL build ($cc)"; failed=1; continue; }
	for f in "" "$fw"; do
		label=${f:+device-firmware}; label=${label:-built-in}
		[ "$label" = device-firmware ] && [ -z "$fw" ] && continue
		ran=1
		if "$Q" "$bin" ${f:+"$f"} > "$EV/run-$cc-$label.txt" 2>&1; then say "PASS ($cc, $label): $(tail -1 "$EV/run-$cc-$label.txt")"
		else say "FAIL ($cc, $label)"; cat "$EV/run-$cc-$label.txt"; failed=1; fi
	done
done
[ $ran = 1 ] || die "no aarch64 compiler ran"
{ sha256sum "$EV"/a650-*; [ -n "$fw" ] && sha256sum "$fw" | sed 's|  .*/|  |'; "$Q" --version | head -1; } > "$EV/SHA256SUMS"
exit $failed
