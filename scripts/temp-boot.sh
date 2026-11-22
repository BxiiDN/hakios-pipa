#!/usr/bin/env bash
# The one script that starts something on the tablet: `fastboot boot IMAGE`, which runs IMAGE from RAM and writes
# nothing. It refuses to run unless the preflight passes, the image verifies, and --yes is given.
#   temp-boot.sh IMAGE --yes [--gpt DIR]
source "$(dirname "$0")/lib.sh"
img=${1:?usage: temp-boot.sh IMAGE --yes [--gpt DIR]}; shift
yes=0; gpt=()
while [ $# -gt 0 ]; do case $1 in --yes) yes=1;; --gpt) gpt=(--gpt "$2"); shift;; *) die "unknown $1";; esac; shift; done
[ $yes = 1 ] || die "add --yes: this starts the image on the tablet (RAM only)"
python3 "$ROOT/tools/verify_bootimg.py" "$img" || die "the image does not verify"
"$ROOT/scripts/preflight.sh" --device "${gpt[@]}" || die "preflight failed: nothing was started"
sha=$(sha256sum "$img" | cut -d' ' -f1); say "fastboot boot $img ($sha)"
fastboot boot "$img"
say "started. To return: hold Power 10-15 s. Afterwards in Android: scripts/capture-boot-log.sh"
