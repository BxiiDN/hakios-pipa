#!/usr/bin/env bash
# Before the tablet is touched: is everything here, is it what it claims, and would the plan write anything?
#   preflight.sh [--device] [--gpt DIR]
# --device asks the tablet, in fastboot mode, read-only questions (getvar). --gpt DIR holds the read-only GPT dumps
# from scripts/dump-gpt.sh; the plan in plans/ram-boot.json is then checked against the real layout.
source "$(dirname "$0")/lib.sh"
device=0; gpt=
while [ $# -gt 0 ]; do case $1 in --device) device=1;; --gpt) gpt=$2; shift;; *) die "unknown argument $1";; esac; shift; done
result=0
ok()   { say "PASS  $*"; }
bad()  { say "FAIL  $*"; result=1; }
skip() { say "SKIP  $*"; }

# 1. nothing in this repository's scripts can write the tablet's storage (comments and this check itself aside)
writers=$(grep -rnE --exclude-dir=__pycache__ --exclude=preflight.sh \
	'fastboot +(flash|erase|format|flashing|set_active|oem +(unlock|lock))|dd +[^|]*of=/dev/block|sgdisk|parted|mkfs' \
	"$ROOT/scripts" "$ROOT/tools" | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' || true)
if [ -n "$writers" ]; then printf '%s\n' "$writers"; bad "a script here could write the tablet"; else ok "no script here writes the tablet"; fi
# 2. the image, if built
img=$ROOT/build/hakios-pipa-bootmgr.img
if [ -f "$img" ]; then python3 "$ROOT/tools/verify_bootimg.py" "$img" && ok "boot image verified" || bad "boot image"; else skip "no build/hakios-pipa-bootmgr.img yet (scripts/build-uboot.sh)"; fi
# 3. the plan, against the real layout when it is given
if [ -n "$gpt" ]; then
	python3 "$ROOT/tools/pipa_gpt.py" check "$ROOT/plans/ram-boot.json" "$gpt"/*.bin && ok "ram-boot plan against the tablet's GPT" || bad "plan check"
else
	skip "no --gpt DIR: the plan was not held against the tablet's real layout"
fi
# 4. tools on this machine
for t in adb fastboot; do command -v $t >/dev/null && ok "$t: $($t --version 2>/dev/null | head -1)" || bad "$t missing"; done
# 5. the tablet, read-only
if [ $device = 1 ]; then
	product=$(fastboot getvar product 2>&1 | awk '/^product:/ {print $2}')
	[ "$product" = pipa ] && ok "fastboot product: pipa" || bad "fastboot product is '$product', not pipa: stop"
	unlocked=$(fastboot getvar unlocked 2>&1 | awk '/^unlocked:/ {print $2}')
	[ "$unlocked" = yes ] && ok "bootloader unlocked" || bad "bootloader unlocked: '$unlocked'"
	say "current slot: $(fastboot getvar current-slot 2>&1 | awk '/^current-slot:/ {print $2}')"
	say "anti-rollback (Xiaomi): $(fastboot getvar anti 2>&1 | awk '/^anti:/ {print $2}')"
else
	skip "--device not given: the tablet was not asked"
fi
[ $result = 0 ] && say "PREFLIGHT PASS" || say "PREFLIGHT FAIL"
exit $result
