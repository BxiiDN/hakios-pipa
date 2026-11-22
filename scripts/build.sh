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

step "pipa partition validator: unit tests" python3 -m unittest discover -s "$ROOT/tests"
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
if command -v aarch64-linux-gnu-gcc >/dev/null && command -v flex >/dev/null; then
	step "U-Boot boot manager (scripts/build-uboot.sh)" "$ROOT/scripts/build-uboot.sh"
else
	blocked "U-Boot boot manager" "aarch64-linux-gnu-gcc and flex needed (scripts/wsl-setup.sh --install)"
fi
if [ -n "${IPHONEOS_SDK:-}" ] && [ -d "${IPHONEOS_SDK}" ]; then
	step "XNU kernel (kernel/build.sh)" bash -c "cd '$K' && kernel/build.sh"
else
	blocked "XNU kernel" "needs Apple's iPhoneOS SDK (IPHONEOS_SDK=...): not redistributable, not in this repository"
fi
blocked "Darwin user space image" "needs an IPSW you are entitled to use; HakiOS main targets Darwin 26/27, not iPadOS 17 (docs/IPADOS17.md)"
blocked "QEMU boot" "needs the kernel above; then: cd $K && make qemu"
blocked "anything on the tablet" "this script never connects to it (docs/DUAL-BOOT.md)"
say "summary: $SUMMARY"
cat "$SUMMARY"
exit $failed
