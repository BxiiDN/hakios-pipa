#!/usr/bin/env bash
# What can be checked of the iPadOS 17 base without Apple's files or the tablet: the port's own board check for an
# 8 GB / 256 GB unit and the host tests of its pipa drivers, with gcc and clang. Summary in logs/unixnu-summary.txt.
source "$(dirname "$0")/lib.sh"
P=$WORK/UniXNU-pipa; R=$WORK/UniXNU-pipa-reference
[ -d "$P" ] || SKIP_UEFI_PIPA=1 "$ROOT/scripts/fetch-unixnu.sh"
S=$ROOT/logs/unixnu-summary.txt; : > "$S"; failed=0
row() { echo "$1" | tee -a "$S"; }
if (cd "$P" && python3 scripts/check-pipa-board.py --ddr-gb 8 --storage-gb 256); then row "PASS     UniXNU-pipa check-pipa-board.py (8 GB / 256 GB)"; else row "FAIL     UniXNU-pipa check-pipa-board.py"; failed=1; fi
for repo in "$P" "$R"; do
	label=$(basename "$repo")
	for t in "$repo"/package/*Tests.c; do
		n=$(basename "$t" .c)
		case $n in A650GmuTests) row "NOT RUN  $label $n: needs UniXNU kits/AdrenoFirmware (AdrenoHfiStartup.h) via unixnu fetch"; continue;; esac
		for cc in gcc clang; do
			command -v $cc >/dev/null || continue
			bin=$(mktemp)
			if $cc -std=gnu11 -O1 -w -I"$repo/package" -o "$bin" "$t" && "$bin" >/dev/null 2>&1; then
				row "PASS     $label $n ($cc)"
			else row "FAIL     $label $n ($cc)"; failed=1; fi
			rm -f "$bin"
		done
	done
done
row "BLOCKED  UniXNU kernel: Linux toolchain (patched clang, cctools-port; scripts/linux/setup-toolchain.py) + Apple's IPSW inputs"
row "BLOCKED  uefi-pipa firmware: needs its Mu-Silicium build (setup_env.sh, pip requirements)"
exit $failed
