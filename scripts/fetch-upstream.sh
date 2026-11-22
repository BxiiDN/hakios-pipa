#!/usr/bin/env bash
# The pinned HakiOS kernel and UEFI, and the parts of Linux the pipa tree needs, beside this repository ($WORK).
source "$(dirname "$0")/lib.sh"
need git
mkdir -p "$WORK"
fetch() {  # fetch DIR URL REF
	local dir=$WORK/$1
	if [ ! -d "$dir/.git" ]; then git init -q "$dir"; git -C "$dir" remote add origin "$2"; fi
	git -C "$dir" fetch -q --depth 1 origin "$3" || die "could not fetch $2 at $3"
	git -C "$dir" checkout -q --detach FETCH_HEAD
	say "$1: $(git -C "$dir" rev-parse HEAD)"
	[ "$(git -C "$dir" rev-parse HEAD)" = "$3" ] || [[ ! "$3" =~ ^[0-9a-f]{40}$ ]] || die "$1 is not at $3"
}
fetch hakios-xnu-kernel "$KERNEL_REPOSITORY" "$KERNEL_REF"
fetch hakios-uefi "$UEFI_REPOSITORY" "$UEFI_REF"
# patches/upstream/: fixes to the pinned kernel kept apart from the pipa package (docs/UPSTREAM-TESTS.md).
# HAKIOS_UPSTREAM_PATCHES=0 leaves the kernel exactly as upstream has it, for the baseline.
if [ "${HAKIOS_UPSTREAM_PATCHES:-1}" = 1 ]; then
	apply_patches "$WORK/hakios-xnu-kernel" "$ROOT/patches/upstream"
else
	say "upstream patches not applied (HAKIOS_UPSTREAM_PATCHES=0)"
fi
if [ ! -d "$WORK/linux/.git" ]; then
	git clone -q --depth 1 --filter=blob:none --no-checkout "$LINUX_REPOSITORY" "$WORK/linux"
fi
git -C "$WORK/linux" sparse-checkout set --no-cone '/arch/arm64/boot/dts/qcom/sm8250*' '/arch/arm64/boot/dts/qcom/pm8*' \
	'/arch/arm64/boot/dts/qcom/pmk8*' '/arch/arm64/boot/dts/qcom/pmr7*' '/include/dt-bindings/' \
	'/include/uapi/linux/input-event-codes.h' '/drivers/clk/qcom/gcc-sm8250.c' '/drivers/clk/qcom/dispcc-sm8250.c' \
	'/drivers/gpu/drm/msm/adreno/a6xx_catalog.c' '/drivers/gpu/drm/msm/adreno/a6xx_gmu.c' '/drivers/gpu/drm/msm/adreno/a6xx_gpu.c'
git -C "$WORK/linux" fetch -q --depth 1 origin "$LINUX_REF" && git -C "$WORK/linux" checkout -q --detach FETCH_HEAD
say "linux: $(git -C "$WORK/linux" rev-parse HEAD)"
