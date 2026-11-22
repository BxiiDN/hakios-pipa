#!/usr/bin/env bash
# READY FOR HARDWARE BOOT -- a different statement from OFFLINE CHECKS PASS (scripts/build.sh). Every artefact a
# temporary boot needs must exist and verify, and the hardware preflight must pass. Exit 0 only for "YES".
#   readiness.sh [--image IMAGE] [--gpt DIR] [--device]
# Without --image it looks for UniXNU's boot image in $HAKIOS_WORK/UniXNU/out/pipa/.
source "$(dirname "$0")/lib.sh"
img=; pre=()
while [ $# -gt 0 ]; do case $1 in --image) img=$2; shift;; --gpt) pre+=(--gpt "$2"); shift;; --device) pre+=(--device);;
	*) die "unknown argument $1";; esac; shift; done
OUT=$WORK/UniXNU/out/pipa
missing=0
have() {  # have WHAT PATH-OR-EMPTY
	if [ -n "$2" ] && [ -s "$2" ]; then say "PRESENT  $1: $2 ($(sha256sum "$2" | cut -c1-16)...)"; else say "MISSING  $1"; missing=$((missing + 1)); fi
}
first() { { find "$OUT" -name "$1" -type f 2>/dev/null || true; } | sort | tail -1; }
have "XNU 10063 kernel (kernel.macho)" "$(first kernel.macho)"
have "uefi-pipa firmware (.fd)" "$({ find "$WORK/uefi-pipa" -path '*pipa*' -name '*.fd' -type f 2>/dev/null || true; } | sort | tail -1)"
have "payload volume (payload.img)" "$(first payload.img)"
[ -n "$img" ] || img=$(first boot.img)
have "boot image" "$img"
have "iPadOS root image for the ipados partition" "$(first 'userdata-root*.img')"
if [ $missing = 0 ]; then "$ROOT/scripts/preflight.sh" --image "$img" "${pre[@]}" || missing=$((missing + 1))
else say "hardware preflight not run: artefacts are missing"; fi
[ $missing = 0 ] && { say "READY FOR HARDWARE BOOT: YES"; exit 0; }
say "READY FOR HARDWARE BOOT: NO ($missing requirement(s) not met)"; exit 1
