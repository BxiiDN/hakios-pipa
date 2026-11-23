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
kernel=$(find "$OUT" -path '*/kernel/kernel.macho' -type f 2>/dev/null | sort | tail -1 || true)
# docs/BOOTSTRAP.md: the stage-A reference kernel stays at kernel/kernel.macho while stage B runs (the port's builders
# read it there); if stage B failed it is still there, and it is never a boot candidate.
for ref in $(find "$OUT" -path '*/stage-a/kernel.macho' -type f 2>/dev/null || true); do
	if [ -n "$kernel" ] && cmp -s "$ref" "$kernel"; then
		say "FAIL     kernel.macho is the stage-A reference kernel (no HID, display, storage or owner root): not a boot candidate"
		kernel=; break
	fi
done
have "XNU 10063 kernel (kernel.macho)" "$kernel"
have "uefi-pipa firmware (.fd)" "$({ find "$WORK/uefi-pipa" -path '*pipa*' -name '*.fd' -type f 2>/dev/null || true; } | sort | tail -1)"
have "payload volume (payload.img)" "$(first payload.img)"
[ -n "$img" ] || img=$(first boot.img)
have "boot image" "$img"
have "iPadOS root image for the ipados partition" "$(first 'userdata-root*.img')"
# the kernel must carry the owner's anchor: an ephemeral CI key (docs/OWNER-KEY.md) authorizes no root
keyjson=$(first key.json)
if [ -n "$keyjson" ] && python3 -c 'import json,sys; sys.exit(json.load(open(sys.argv[1])).get("kind") != "owner")' "$keyjson"; then
	say "PRESENT  owner key anchor: $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["anchor_sha256"])' "$keyjson")"
else say "MISSING  owner key anchor (none, or the kernel was built with an ephemeral key)"; missing=$((missing + 1)); fi
if [ $missing = 0 ]; then
	# the image must be made of these very pieces, and they must be the ones this build recorded
	manifest=$ROOT/logs/readiness-manifest.json
	python3 "$ROOT/tools/build_manifest.py" "$WORK/UniXNU" --uefi "$WORK/uefi-pipa" --out "$manifest" >/dev/null
	python3 "$ROOT/tools/image_consistency.py" --image "$img" --kernel "$kernel" --payload "$(first payload.img)" \
		--firmware "$({ find "$WORK/uefi-pipa" -path '*pipa*' -name 'SILICIUM_UEFI.fd' -type f 2>/dev/null || true; } | sort | tail -1)" \
		--manifest "$manifest" || missing=$((missing + 1))
	"$ROOT/scripts/preflight.sh" --image "$img" "${pre[@]}" || missing=$((missing + 1))
else say "hardware preflight not run: artefacts are missing"; fi
[ $missing = 0 ] && { say "READY FOR HARDWARE BOOT: YES"; exit 0; }
say "READY FOR HARDWARE BOOT: NO ($missing requirement(s) not met)"; exit 1
