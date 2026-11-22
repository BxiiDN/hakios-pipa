#!/usr/bin/env bash
# Everything that can be built and checked without the tablet, with a PASS / FAIL / BLOCKED line for each.
# Writes logs/build-summary.txt. Exit 1 if anything that should pass failed; BLOCKED is not a failure.
source "$(dirname "$0")/lib.sh"
need python3; need git
K=$WORK/hakios-xnu-kernel
[ -d "$K" ] || "$ROOT/scripts/fetch-upstream.sh"
SUMMARY=$ROOT/logs/build-summary.txt; : > "$SUMMARY"
failed=0
step() {  # step NAME COMMAND...: PASS or FAIL, the command's output in the log
	local name=$1; shift
	say "== $name"
	if "$@"; then echo "PASS     $name" | tee -a "$SUMMARY"; else echo "FAIL     $name" | tee -a "$SUMMARY"; failed=1; fi
}
blocked() { echo "BLOCKED  $1: $2" | tee -a "$SUMMARY"; }

export HAKIOS_KERNEL=$K
step "unit tests: partition validator, boot manager env, hardware facts" python3 -m unittest discover -s "$ROOT/tests"
step "firmware manifest verifier: self-test" python3 "$ROOT/tools/firmware_manifest.py" --self-test
step "boot image verifier: unit tests" python3 "$ROOT/tools/verify_bootimg.py" --self-test
step "pipa device tree from Linux merged" "$ROOT/tools/mkdts.sh" "$WORK/linux" "$WORK/pipa-mainline.dts"
(cd "$K" && python3 tools/device.py remove pipa >/dev/null 2>&1 || true)
step "pipa package brought into the kernel checkout" bash -c "cd '$K' && python3 tools/device.py add --from '$ROOT'"
step "boards check (pipa + the kernel's own)" bash -c "cd '$K' && python3 tools/boards.py check"
step "pipa values still match Linux's tree" bash -c "cd '$K' && python3 tools/boards.py compare pipa --dts '$WORK/pipa-mainline.dts'"
step "kconfig check" make -C "$K" -s kconfig-check
step "boot-args docs check" make -C "$K" -s docs-check
if [ "${SKIP_UPSTREAM_TESTS:-0}" = 1 ]; then
	echo "NOT RUN  HakiOS host tests (workbench/run.sh): SKIP_UPSTREAM_TESTS=1 (CI runs them as their own job)" | tee -a "$SUMMARY"
else
	step "HakiOS host tests (workbench/run.sh)" bash -c "cd '$K' && workbench/run.sh"
fi
if command -v clang >/dev/null && command -v lld-link >/dev/null; then
	step "UEFI loader (arch/arm64/boot/build.sh)" bash -c "cd '$K' && arch/arm64/boot/build.sh"
	a=$(sha256sum "$K/arch/arm64/boot/loader.efi" | cut -d' ' -f1)
	step "UEFI loader rebuilt bit for bit" bash -c "cd '$K' && arch/arm64/boot/build.sh >/dev/null && [ \"\$(sha256sum arch/arm64/boot/loader.efi | cut -d' ' -f1)\" = $a ]"
else
	blocked "UEFI loader" "clang and lld-link needed"
fi
# U-Boot's own Kconfig decides the boot manager's configuration: no compiler needed for this part
UB=$WORK/u-boot-src
if [ ! -d "$UB/.git" ] || ! grep -q 'config CMD_HAKIOS' "$UB/cmd/Kconfig" 2>/dev/null; then
	(cd "$WORK/hakios-uefi" && HAKIOS_PROFILE_ROOT="$ROOT/uefi-profiles" U_BOOT="$UB" U_BOOT_URL=https://github.com/u-boot/u-boot \
		u-boot/apply.sh xiaomi/pipa) >/dev/null 2>&1 || true
fi
if [ -f "$UB/tools/buildman/kconfiglib.py" ]; then
	step "U-Boot defconfig resolved by U-Boot's Kconfig (menu, keys, safety switches)" python3 "$ROOT/tools/check_uboot_config.py" "$UB"
else
	blocked "U-Boot Kconfig check" "could not prepare U-Boot at hakios-uefi's BASE_COMMIT in $UB"
fi
# the iPadOS 17 base: UniXNU-pipa's own checks and driver host tests
step "UniXNU base pinned, iPadOS 17.7.11 profile on xnu-10063.141.1" "$ROOT/scripts/fetch-unixnu.sh"
step "UniXNU-pipa board check and pipa driver host tests" "$ROOT/scripts/unixnu-checks.sh"
if [ -f "$WORK/uefi-pipa/Resources/DTBs/pipa.dts" ]; then
	step "hardware facts of the published pipa tree (uefi-pipa) hold" python3 "$ROOT/tools/pipa_hw_facts.py" "$WORK/uefi-pipa/Resources/DTBs/pipa.dts" --check
fi
if [ -f "$WORK/linux/drivers/gpu/drm/msm/adreno/a6xx_catalog.c" ]; then
	if python3 "$ROOT/tools/a650_check.py" --linux "$WORK/linux" --port "$WORK/UniXNU-pipa" --hakios "$K"; then
		echo "PASS     Adreno 650 constants agree, and HakiOS's driver asks for A650 firmware" | tee -a "$SUMMARY"
	else
		echo "GAP      HakiOS's GPU driver is A660-family only (a650_check.py; docs/ADRENO650.md): known, not a build failure" | tee -a "$SUMMARY"
	fi
fi
if command -v aarch64-linux-gnu-gcc >/dev/null && command -v flex >/dev/null; then
	step "U-Boot boot manager (scripts/build-uboot.sh)" "$ROOT/scripts/build-uboot.sh"
else
	blocked "U-Boot boot manager" "aarch64-linux-gnu-gcc and flex needed (scripts/wsl-setup.sh --install)"
fi
if [ -n "${IPHONEOS_SDK:-}" ] && [ -d "${IPHONEOS_SDK}" ]; then
	step "XNU kernel (kernel/build.sh)" bash -c "cd '$K' && kernel/build.sh"
else
	blocked "HakiOS XNU kernel (xnu-12377)" "needs Apple's iPhoneOS SDK; not the iPadOS 17 base anyway (docs/BASE-DECISION.md)"
fi
if [ -x /opt/unixnu-linux/bin/clang ] || [ -n "${UNIXNU_TOOLCHAIN:-}" ]; then
	blocked "UniXNU XNU 10063 kernel" "toolchain present: ./unixnu fetch, ipsw fetch, build kernel -D $WORK/UniXNU-pipa (docs/CLAUDE-CODE.md)"
else
	blocked "UniXNU XNU 10063 kernel" "needs UniXNU's Linux toolchain (scripts/wsl-setup.sh --unixnu-toolchain) and the iPadOS 17.7.11 IPSW inputs"
fi
blocked "iPadOS 17 user space / payload" "needs the iPad7,1 17.7.11 IPSW members (./unixnu ipsw fetch) on your machine"
blocked "QEMU boot" "needs a kernel; no qemu-system-aarch64 here"
blocked "anything on the tablet" "this script never connects to it (docs/DUAL-BOOT.md)"
say "summary: $SUMMARY"
cat "$SUMMARY"
exit $failed
