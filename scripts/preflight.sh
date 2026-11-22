#!/usr/bin/env bash
# HARDWARE PREFLIGHT: everything that must be verified about the tablet and the image before a temporary boot.
# Each requirement is PASS or FAIL; a requirement that could not be checked is FAIL (never skipped into a pass).
#   preflight.sh --image IMAGE --gpt DIR [--device]
#     --device asks the tablet read-only questions (fastboot getvar); without it identity is read from private/device.txt
# Exit 0 only when every requirement passes: "HARDWARE PREFLIGHT PASS".
source "$(dirname "$0")/lib.sh"
img=; gpt=; device=0
while [ $# -gt 0 ]; do case $1 in --image) img=$2; shift;; --gpt) gpt=$2; shift;; --device) device=1;;
	*) die "unknown argument $1";; esac; shift; done
PRIVATE=${HAKIOS_PRIVATE:-$ROOT/private}
fails=0
ok()  { say "PASS  $*"; }
bad() { say "FAIL  $*"; fails=$((fails + 1)); }

# 1. no script in this repository can write the tablet (comments and this check aside)
writers=$(grep -rnE --exclude-dir=__pycache__ --exclude=preflight.sh \
	'fastboot +(flash|erase|format|flashing|set_active|oem +(unlock|lock))|dd +[^|]*of=/dev/block|sgdisk|parted|mkfs' \
	"$ROOT/scripts" "$ROOT/tools" | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true)
if [ -n "$writers" ]; then printf '%s\n' "$writers"; bad "a script here could write the tablet"; else ok "no script here writes the tablet"; fi
# 2. the image: structure, payload volume, menu, storage arguments
if [ -z "$img" ] || [ ! -f "$img" ]; then bad "image: none given or not found (--image)"
elif python3 "$ROOT/tools/verify_bootimg.py" --unixnu "$img"; then ok "image verified (UniXNU layout, menu, storage arguments)"
else bad "image does not verify"; fi
# 3. GPT: dumps present, intact, and the plan writes nothing
if [ -z "$gpt" ] || ! ls "$gpt"/sd?.bin >/dev/null 2>&1; then bad "GPT: no dumps (--gpt DIR from scripts/dump-gpt.sh)"
else
	(cd "$gpt" && sha256sum -c --quiet SHA256SUMS) && ok "GPT dumps match their SHA256SUMS" || bad "GPT dumps do not match SHA256SUMS"
	python3 "$ROOT/tools/pipa_gpt.py" check "$ROOT/plans/ram-boot.json" "$gpt"/sd?.bin && ok "ram-boot plan against the tablet's GPT" || bad "plan check"
fi
# 4. root target: the partition the image names exists on this tablet and is clear of Android's userdata
if [ -n "$gpt" ] && [ -n "$img" ] && [ -f "$img" ] && ls "$gpt"/sd?.bin >/dev/null 2>&1; then
	python3 "$ROOT/tools/image_root_check.py" "$img" "$gpt"/sd?.bin && ok "root target on this tablet" || bad "root target (see above)"
else bad "root target: needs both --image and --gpt"; fi
# 5. identity and temporary-boot support
if [ $device = 1 ]; then
	need fastboot
	product=$(fastboot getvar product 2>&1 | awk '/^product:/ {print $2}' || true)
	unlocked=$(fastboot getvar unlocked 2>&1 | awk '/^unlocked:/ {print $2}' || true)
else
	product=$({ awk -F= '/^ro.product.device=|^product=/ {print $2}' "$PRIVATE/device.txt" 2>/dev/null || true; } | head -1)
	unlocked=$({ awk -F= '/^unlocked=/ {print $2}' "$PRIVATE/device.txt" 2>/dev/null || true; } | head -1)
fi
[ "$product" = pipa ] && ok "identity: pipa" || bad "identity: '${product:-unknown}' (scripts/detect-device.sh)"
[ "$unlocked" = yes ] && ok "bootloader unlocked (fastboot boot is accepted)" || bad "bootloader unlocked: '${unlocked:-unknown}' (detect-device.sh in fastboot mode)"
# 6. firmware the image needs, from this tablet, with digests checked
touch=$(python3 "$ROOT/tools/panel_firmware.py" "$(cat "$PRIVATE/panel.txt" 2>/dev/null || true)" 2>/dev/null || true)
if [ -d "$PRIVATE/firmware" ] && [ -n "$touch" ] && python3 "$ROOT/tools/firmware_manifest.py" "$ROOT/manifests/unixnu-pipa-proprietary-files.txt" "$PRIVATE/firmware" --touch "$touch" >/dev/null; then
	ok "firmware digests"; else bad "firmware: not extracted or digests differ (scripts/extract-firmware.sh)"; fi
[ -n "$touch" ] \
	&& ok "panel identified ($(cat "$PRIVATE/panel.txt"))" || bad "panel not identified (scripts/extract-live-dt.sh)"
# 7. backup that matches the risk: the image writes nothing, so the boot chain images plus the owner's own data backup
latest=$({ ls -d "$PRIVATE"/backup/*/ 2>/dev/null || true; } | tail -1)
if [ -n "$latest" ] && (cd "$latest" && sha256sum -c --quiet SHA256SUMS 2>/dev/null); then ok "boot-chain images backed up and verified ($latest)"
else bad "boot-chain backup missing or does not verify (scripts/backup-readiness.sh)"; fi
[ -f "$PRIVATE/USER-DATA-BACKUP-CONFIRMED" ] && ok "owner confirmed a backup of Android's data ($(head -1 "$PRIVATE/USER-DATA-BACKUP-CONFIRMED"))" \
	|| bad "owner has not confirmed a backup of Android's data (write the date into private/USER-DATA-BACKUP-CONFIRMED)"
# 8. recovery: the tools to get back
for t in adb fastboot; do command -v $t >/dev/null && ok "recovery tool $t" || bad "recovery tool $t missing"; done
[ $fails = 0 ] && say "HARDWARE PREFLIGHT PASS" || say "HARDWARE PREFLIGHT FAIL ($fails)"
exit $([ $fails = 0 ] && echo 0 || echo 1)
