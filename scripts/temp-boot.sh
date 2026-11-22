#!/usr/bin/env bash
# The one script that starts something on the tablet: `fastboot boot IMAGE` (RAM only, nothing flashed). An image run
# from RAM can still reach the UFS storage, so it refuses unless scripts/readiness.sh says READY FOR HARDWARE BOOT for
# this exact image, and --yes is given.
#   temp-boot.sh IMAGE --gpt DIR --yes
source "$(dirname "$0")/lib.sh"
img=${1:?usage: temp-boot.sh IMAGE --gpt DIR --yes}; shift
yes=0; gpt=
while [ $# -gt 0 ]; do case $1 in --yes) yes=1;; --gpt) gpt=$2; shift;; *) die "unknown $1";; esac; shift; done
[ -n "$gpt" ] || die "--gpt DIR is required (scripts/dump-gpt.sh)"
[ $yes = 1 ] || die "add --yes: this starts the image on the tablet"
"$ROOT/scripts/readiness.sh" --image "$img" --gpt "$gpt" --device || die "not ready: nothing was started"
sha=$(sha256sum "$img" | cut -d' ' -f1); say "fastboot boot $img ($sha)"
fastboot boot "$img"
say "started. To return: hold Power 10-15 s. Afterwards in Android: scripts/capture-boot-log.sh"
