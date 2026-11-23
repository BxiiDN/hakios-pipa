#!/usr/bin/env bash
# Two-stage kernel build for the pipa port (docs/BOOTSTRAP.md). Needs macOS with the Xcode iphoneos SDK, the IPSW
# input UniXNU fetches, and UNIXNU_OWNER_* set (docs/OWNER-KEY.md).
#   kernel-two-stage.sh a        stage A: reference kernel without ShengHidInput and the legacy display archive,
#                                built and prelinked by UniXNU; records its provenance (never a boot candidate)
#   kernel-two-stage.sh b        stage B: the full board, every archive, qualified against the stage-A kernel
#   kernel-two-stage.sh recheck  qualify ShengHidInput again against the final kernel; the bindings must not move
#   kernel-two-stage.sh gpu-userland    Turnip (Mesa freedreno Vulkan, ARM64/iOS 17) and the AdrenoMetal bridge, with
#                                UniXNU's own build-boot-runtime.py build_plugin('ios'); stage B then finds them
#   kernel-two-stage.sh storage-static  UniXNU's audit-storage-interface.py against the stage-A kernel: its static
#                                checks only. It cannot write interface-audit.json without the live QEMU/gdb record,
#                                and this never claims one (docs/BOOTSTRAP.md "storage")
# Evidence goes to $HAKIOS_EVIDENCE (default logs/two-stage): logs, plans, provenance, symbol list, hashes. The
# kernels themselves contain Apple's kexts and stay local.
source "$(dirname "$0")/lib.sh"
stage=${1:?usage: kernel-two-stage.sh a|b|recheck}
U=$WORK/UniXNU P=$WORK/UniXNU-pipa
OUTROOT=${UNIXNU_OUT:-$U/out}   # UniXNU honours UNIXNU_OUT too: a fresh one is a clean build
OUTDIR=$OUTROOT/pipa/ipados-17.7.11-21H461/pipa
TREE=$OUTDIR/tree KERNEL=$OUTDIR/kernel/kernel.macho
EV=${HAKIOS_EVIDENCE:-$ROOT/logs/two-stage}
STAGE_PATCH=$ROOT/patches/stage-a/0001-reference-kernel-without-hid-and-legacy-display.patch
STAGE_PATCHES=("$ROOT"/patches/stage-a/*.patch)   # 0001, then 0002 (no storage bindings: no audit in stage A)
# The live storage ABI record of the QEMU board (scripts/qemu-storage-abi.sh); stage B binds VirtioMmioBlock/RamBlock to it
STORAGE_AUDIT=${HAKIOS_STORAGE_AUDIT:-$ROOT/logs/qemu-storage/interface-audit.json}
IOSERVICE_OBJ=$TREE/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOService.cpo   # its DWARF: IOService size
mkdir -p "$EV"
# Reproducible version string: XNU's config/newvers.pl stamps `date` into "Darwin Kernel Version ...: <date>" unless
# KERNEL_BUILD_DATE is set ("allowing for reproducible builds"). Runs 45100879621 and 45104257856 built identical
# archives but kernels that differ, and their version strings carry the build time. Use the commit date of the
# UniXNU pin, in `date`'s own format.
if [ -z "${KERNEL_BUILD_DATE:-}" ]; then
	KERNEL_BUILD_DATE=$(TZ=UTC git -C "$WORK/UniXNU" log -1 --format=%cd --date=format-local:'%a %b %e %H:%M:%S UTC %Y')
	export KERNEL_BUILD_DATE
fi
say "KERNEL_BUILD_DATE=$KERNEL_BUILD_DATE"
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }   # shasum is on macOS and Ubuntu alike
NM=$(command -v llvm-nm || true); [ -n "$NM" ] || NM="xcrun nm"
command -v brew >/dev/null && export PATH="$(brew --prefix llvm)/bin:$PATH"   # llvm-objcopy for the HID builder
[ -n "${UNIXNU_OWNER_PUBLIC_KEY:-}" ] || die "UNIXNU_OWNER_PUBLIC_KEY is not set (docs/OWNER-KEY.md)"

save_logs() {  # save_logs NAME
	mkdir -p "$EV/$1-logs"
	cp "$OUTDIR"/logs/*.log "$EV/$1-logs/" 2>/dev/null || true
}
evidence() {  # evidence NAME: archive hashes always; plan, hashes and exported symbols of the kernel when one was built
	find "$TREE/build" -name '*.a' -type f 2>/dev/null | sort | while read -r a; do echo "$(sha "$a")  $(wc -c < "$a" | tr -d ' ')  ${a#"$TREE"/}"; done > "$EV/$1-archives-sha256.txt"
	say "$1: $(wc -l < "$EV/$1-archives-sha256.txt" | tr -d ' ') archives"; cat "$EV/$1-archives-sha256.txt"
	[ -f "$KERNEL" ] || { say "$1: no kernel.macho"; return 0; }
	cp "$OUTDIR/kernel/kernel.json" "$EV/$1-kernel.json"
	[ -f "$OUTDIR/kernel/kernel.map.json" ] && cp "$OUTDIR/kernel/kernel.map.json" "$EV/$1-kernel.map.json"
	echo "$(sha "$KERNEL")  $(wc -c < "$KERNEL" | tr -d ' ')  kernel.macho" > "$EV/$1-kernel-sha256.txt"
	$NM -g --defined-only "$KERNEL" 2>/dev/null | sort -k3 > "$EV/$1-kernel-exports.txt" || true
	python3 "$ROOT/tools/macho_fingerprint.py" "$KERNEL" --out "$EV/$1-kernel-fingerprint.json"
	python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); [print("FP", k, v["sha256"]) for k, v in sorted(d["segments"].items())]; print("FP uuid", d["uuid"])' "$EV/$1-kernel-fingerprint.json"
	say "$1: kernel.macho $(cat "$EV/$1-kernel-sha256.txt"), $(wc -l < "$EV/$1-kernel-exports.txt" | tr -d ' ') exported symbols"
}
build() {  # build NAME
	(cd "$U" && ./unixnu defconfig pipa_defconfig -D ../UniXNU-pipa && ./unixnu build kernel) || { save_logs "$1"; evidence "$1"; skipped "$1" || true; die "$1: unixnu build kernel failed"; }
	save_logs "$1"; evidence "$1"
	# A builder that prints SKIP and exits 0 has not built its archive: never a PASS for the full board.
	if skipped "$1" && [ "$1" = stage-b ]; then die "stage-b: a required archive input was skipped (above)"; fi
}
skipped() {  # skipped NAME: list builder SKIP lines; true when there is one
	grep -hE '^SKIP [A-Za-z0-9._-]+: ' "$EV/$1-logs/"*.log 2>/dev/null | sort -u > "$EV/$1-skipped.txt" || true
	[ -s "$EV/$1-skipped.txt" ] || return 1
	say "$1: builders that SKIPPED (their archive is not built):"; cat "$EV/$1-skipped.txt"
}

turnip_diagnostics() {  # evidence for a failed Turnip iOS compile: first errors, feature macros, SDK headers
	local b=$TREE/build/mesa-tu-ios sdk d=$EV/turnip-diagnostics.txt
	sdk=$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null || true)
	{ echo "== SDK $(xcrun --sdk iphoneos --show-sdk-version 2>/dev/null) $sdk"
	  for h in endian.h machine/endian.h dlfcn.h; do echo "-- $h: $([ -f "$sdk/usr/include/$h" ] && shasum -a 256 "$sdk/usr/include/$h" | cut -c1-16 || echo absent)"; done
	  [ -f "$sdk/usr/include/endian.h" ] && grep -nE 'define|#if|#include' "$sdk/usr/include/endian.h" | head -40
	  grep -nE 'Dl_info|dladdr|_POSIX_C_SOURCE|_DARWIN_C_SOURCE|__DARWIN_C_LEVEL' "$sdk/usr/include/dlfcn.h" 2>/dev/null | head -20
	  echo "== HAVE_* in build.ninja"; grep -oE -- '-DHAVE_[A-Z0-9_]+' "$b/build.ninja" 2>/dev/null | sort | uniq -c
	  echo "== meson header/function checks"; grep -E 'Has header "(endian|dlfcn)\.h"|Checking for function "dladdr"|Checking if .*endian' "$b/meson-logs/meson-log.txt" 2>/dev/null | head
	  echo "== first compile errors"; grep -hE 'error:|FAILED:' "$TREE/.cache/mesa-tu-ios-build.log" "$EV/gpu-userland.log" 2>/dev/null | head -30
	  echo "== first failing command"; grep -h -A1 '^FAILED:' "$TREE/.cache/mesa-tu-ios-build.log" 2>/dev/null | head -4 | cut -c1-1500
	} > "$d" 2>&1 || true
	cat "$d"
	# Annotations are readable on the public run page and API without a login: one per section, newlines as %0A.
	if [ -n "${GITHUB_ACTIONS:-}" ]; then
		awk '/^== /{if(m)print m; m=$0; next}{m=m "%0A" $0} END{if(m)print m}' "$d" | head -10 | cut -c1-4000 | while IFS= read -r line; do echo "::error title=turnip-diagnostics::$line"; done
	fi
}

case $stage in
a)
	git -C "$P" apply --check "${STAGE_PATCHES[@]}" || die "stage-A patches do not apply to the patched port"
	git -C "$P" apply "${STAGE_PATCHES[@]}"
	trap 'git -C "$P" apply -R "${STAGE_PATCHES[@]}" && say "stage-A patches removed from the port"' EXIT
	rm -f "$KERNEL" "$OUTDIR/kernel/kernel.json"
	build stage-a
	python3 "$ROOT/tools/candidate_provenance.py" record --kernel "$KERNEL" --plan "$OUTDIR/kernel/kernel.json" \
		--stage-patch "$STAGE_PATCH" --out "$EV/stage-a-provenance.json" \
		--commit "hakios-pipa=$(git -C "$ROOT" rev-parse HEAD)" --commit "UniXNU=$(git -C "$U" rev-parse HEAD)" \
		--commit "UniXNU-pipa=$(git -C "$P" rev-parse HEAD)"
	mkdir -p "$OUTDIR/stage-a"
	cp "$KERNEL" "$OUTDIR/stage-a/kernel.macho"; cp "$OUTDIR/kernel/kernel.json" "$OUTDIR/stage-a/kernel.json"
	;;
b)
	git -C "$P" apply --check -R "$STAGE_PATCH" 2>/dev/null && die "the stage-A patch is still applied to the port"
	# Storage ABI: the QEMU record may bind pipa's drivers only if the stage-A pipa kernel carries the same original
	# IOStorageFamily class at the same addresses (tools/storage_abi_transfer.py). Nothing in the record is edited.
	[ -f "$STORAGE_AUDIT" ] || die "no interface-audit.json at $STORAGE_AUDIT (scripts/qemu-storage-abi.sh; HAKIOS_STORAGE_AUDIT)"
	python3 "$ROOT/tools/storage_abi_transfer.py" --audit "$STORAGE_AUDIT" --kernel "$OUTDIR/stage-a/kernel.macho" \
		--plan "$OUTDIR/stage-a/kernel.json" --unixnu "$U" --dwarf "$IOSERVICE_OBJ" --json "$EV/storage-transfer-stage-a.json" \
		|| die "the QEMU storage record does not transfer to the stage-A pipa kernel"
	mkdir -p "$TREE/build/storage-abi"; cp "$STORAGE_AUDIT" "$TREE/build/storage-abi/interface-audit.json"
	say "storage ABI record installed: $(sha "$STORAGE_AUDIT")"
	if [ -f "$EV/gpu-userland.env" ]; then export "$(cat "$EV/gpu-userland.env")"; say "GPU userland from $UNIXNU_GPU_WORK"; fi
	# build-platform-power.py (with a reference kernel) reads the original kernelcache at the port's path
	# .cache/firmware/kernelcache.macho/kernelcache.release.ipad7.decompressed; UniXNU 62f203c keeps it in out/ipsw/<build>.
	cache=$OUTROOT/ipsw/21H461/kernelcache.decompressed
	[ -f "$cache" ] || die "no decompressed 21H461 kernelcache at $cache"
	[ "$(sha "$cache")" = f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7 ] || die "$cache is not the pinned 21H461 kernelcache"
	mkdir -p "$P/.cache/firmware/kernelcache.macho"
	ln -sfn "$cache" "$P/.cache/firmware/kernelcache.macho/kernelcache.release.ipad7.decompressed"
	python3 "$ROOT/tools/candidate_provenance.py" install --candidate "$OUTDIR/stage-a/kernel.macho" \
		--plan "$OUTDIR/stage-a/kernel.json" --provenance "$EV/stage-a-provenance.json" --tree "$TREE"
	build stage-b
	cp "$TREE/build/sheng-hid-input/abi-audit.json" "$EV/stage-b-hid-abi-audit.json"
	for c in virtio-mmio-block-verified ram-block; do
		[ -f "$TREE/build/$c/bindings.json" ] || die "stage-b: no $c bindings.json"; cp "$TREE/build/$c/bindings.json" "$EV/stage-b-$c-bindings.json"
	done
	python3 "$ROOT/tools/storage_abi_transfer.py" --audit "$STORAGE_AUDIT" --kernel "$KERNEL" --plan "$OUTDIR/kernel/kernel.json" \
		--unixnu "$U" --dwarf "$IOSERVICE_OBJ" --json "$EV/storage-transfer-final.json" || die "final kernel: storage bindings do not hold"
	;;
recheck)
	[ -f "$EV/stage-b-hid-abi-audit.json" ] || die "no stage-B HID audit; run stage b first"
	final=$TREE/build/xnu-prelink/native-owner-ufs-cpu-desktop-zfinal-candidate.macho
	cp "$KERNEL" "$final"; cp "$OUTDIR/kernel/kernel.json" "${final%.macho}.json"; touch "$final"
	(cd "$TREE" && python3 scripts/build-sheng-hid-input.py) > "$EV/recheck-hid.log" 2>&1 || { cat "$EV/recheck-hid.log"; die "ShengHidInput does not qualify against the final kernel"; }
	cp "$TREE/build/sheng-hid-input/abi-audit.json" "$EV/final-hid-abi-audit.json"
	rm -f "$final" "${final%.macho}.json"
	python3 "$ROOT/tools/candidate_provenance.py" compare-bindings "$EV/stage-b-hid-abi-audit.json" "$EV/final-hid-abi-audit.json"
	;;
gpu-userland)
	command -v glslangValidator >/dev/null || die "glslangValidator missing (brew install glslang)"
	# Mesa's ir3 parser needs bison >= 3 and flex; macOS ships bison 2.3 (run 45106011890: ir3_parser.c FAILED)
	command -v brew >/dev/null && export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$PATH"
	say "bison: $(bison --version | head -1); flex: $(flex --version | head -1); SDK $(xcrun --sdk iphoneos --show-sdk-version 2>/dev/null)"
	# In the pipa tree, as the GPU addon builder expects (its inputs are $TREE/build/...), not in UniXNU's own checkout:
	# there drivers/Adreno740 is UniXNU's KMD and drivers/AdrenoMetal UniXNU's frontend, not the ones the pipa kernel has.
	# `unixnu tree` fetches every git module; run 45260103800 lost one to "Connection reset by peer": three attempts.
	for attempt in 1 2 3; do
		(cd "$U" && ./unixnu defconfig pipa_defconfig -D ../UniXNU-pipa && ./unixnu tree -D ../UniXNU-pipa) > "$EV/gpu-tree.log" 2>&1 && break
		[ $attempt = 3 ] && { tail -20 "$EV/gpu-tree.log"; die "gpu-userland: unixnu tree failed"; }
		say "gpu-userland: unixnu tree attempt $attempt failed: $(grep -m1 -E 'fatal|error' "$EV/gpu-tree.log")"; sleep 30
	done
	[ -d "$TREE/scripts" ] || die "gpu-userland: no pipa tree at $TREE"
	# `unixnu tree` links only the board's components: drivers/Adreno650 and drivers/AdrenoMetal are not among them (a
	# fresh tree has neither). pipa's own builders link them from the device repository (build-adreno650.py,
	# build-pipa-gpu-addon.py stage_inputs); do the same here, and refuse a tree whose links point elsewhere.
	for d in Adreno650 AdrenoMetal; do
		[ -d "$P/drivers/$d" ] || die "gpu-userland: the pipa port has no drivers/$d"
		[ -e "$TREE/drivers/$d" ] || [ -L "$TREE/drivers/$d" ] || ln -s "$(cd "$P/drivers/$d" && pwd -P)" "$TREE/drivers/$d"
	done
	# Turnip reads the KMD user-client ABI from -Dtu-darwin-abi-dir=drivers/Adreno740. pipa's KMD is drivers/Adreno650,
	# whose NativeAdrenoABI.h has every constant of the 740 header with the same values (plus MaxQueues, MaxBoBytesShift):
	# build against the ABI of the KMD that runs.
	if [ -e "$TREE/drivers/Adreno740" ] && [ "$(readlink -f "$TREE/drivers/Adreno740")" != "$(readlink -f "$P/drivers/Adreno650")" ]; then
		die "gpu-userland: $TREE/drivers/Adreno740 exists and is not pipa's Adreno650"
	fi
	ln -sfn "$P/drivers/Adreno650" "$TREE/drivers/Adreno740"
	[ -f "$TREE/drivers/Adreno740/NativeAdrenoABI.h" ] || die "gpu-userland: no NativeAdrenoABI.h"
	[ "$(readlink -f "$TREE/drivers/AdrenoMetal")" = "$(readlink -f "$P/drivers/AdrenoMetal")" ] || die "gpu-userland: the tree's AdrenoMetal is not pipa's"
	mkdir -p "$TREE/.cache/mesa-tools/bin"; ln -sfn "$(command -v bison)" "$TREE/.cache/mesa-tools/bin/bison"
	(cd "$TREE" && python3 - <<'PY'
import importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
spec = importlib.util.spec_from_file_location('boot_runtime', Path('scripts/build-boot-runtime.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
pins = json.loads(Path('scripts/data/adreno-compiler-inputs.json').read_text())
mesa = m.ROOT / '.cache/mesa-work'
if m.checkout(mesa, pins['mesa']):
    for patch in pins['patches']:
        m.run('git', '-C', mesa, 'apply', m.ROOT / patch)
m.validate_recorded_patches(m.ROOT, mesa, pins)
venv = m.ROOT / '.cache/mesa-venv'
if not (venv / 'bin/python').is_file():
    m.run(sys.executable, '-m', 'venv', venv)
m.run(venv / 'bin/python', '-m', 'pip', 'install', '-r', m.ROOT / 'scripts/requirements-adreno-compiler.txt')
m.script('build-turnip-darwin.py', '--target', 'ios')
PY
	) > "$EV/gpu-userland.log" 2>&1 || { tail -40 "$EV/gpu-userland.log"; tail -60 "$TREE/.cache/mesa-tu-ios-build.log" 2>/dev/null; turnip_diagnostics; die "gpu-userland: Turnip build failed"; }
	# The bridge: pipa's drivers/AdrenoMetal/bridge on its own translator pin (scripts/build-adreno-metal-bridge.py, port
	# patch 0009: its 21 patches apply to metal2vulkan 720ef1ce and to no later pin).
	m2v=$TREE/.cache/gpu-reference/metal2vulkan
	[ -d "$m2v/.git" ] || git clone -q --filter=blob:none https://github.com/steelbrain/metal2vulkan.git "$m2v"
	git -C "$m2v" checkout -q --detach 720ef1ce9ae2a2068999a8675717418b9416283e
	command -v brew >/dev/null && export LLVM_AS="$(brew --prefix llvm)/bin/llvm-as"
	# build-adreno-metal-bridge.py runs `cargo +1.98.0 build --target aarch64-apple-ios`; rustup fetches 1.98.0 on
	# demand but not its iOS std (run 45262156041: E0463 "can't find crate for `core`" in typenum).
	command -v rustup >/dev/null || die "gpu-userland: rustup missing"
	rustup toolchain install 1.98.0 --profile minimal --target aarch64-apple-ios >> "$EV/gpu-userland.log" 2>&1 \
		|| { tail -20 "$EV/gpu-userland.log"; die "gpu-userland: rust 1.98.0 with aarch64-apple-ios"; }
	(cd "$TREE" && python3 scripts/build-adreno-metal-bridge.py --target ios) >> "$EV/gpu-userland.log" 2>&1 || { tail -40 "$EV/gpu-userland.log"; die "gpu-userland: Metal bridge build failed"; }
	tail -20 "$EV/gpu-userland.log"
	for f in build/mesa-tu-ios/src/freedreno/vulkan/libvulkan_freedreno.dylib build/adreno-metal-bridge/ios/libadreno_metal_bridge.a; do
		[ -f "$TREE/$f" ] || die "gpu-userland: $f was not produced"
		say "gpu-userland: $(sha "$TREE/$f")  $(wc -c < "$TREE/$f" | tr -d ' ')  $f"
		file "$TREE/$f" | sed 's/^/  /'
	done
	echo "UNIXNU_GPU_WORK=$TREE" > "$EV/gpu-userland.env"
	;;
storage-static)
	[ -f "$OUTDIR/stage-a/kernel.macho" ] || die "no stage-A kernel; run stage a first"
	ref=$TREE/build/xnu-prelink/native-apfs-load-positive.macho; mkdir -p "$(dirname "$ref")"
	[ -e "$ref" ] && die "$ref exists already; refusing to replace it"
	cp "$OUTDIR/stage-a/kernel.macho" "$ref"; cp "$OUTDIR/stage-a/kernel.json" "${ref%.macho}.json"
	code=0; (cd "$TREE" && python3 scripts/audit-storage-interface.py) > "$EV/storage-static.log" 2>&1 || code=$?   # lib.sh traps ERR
	rm -f "$ref" "${ref%.macho}.json"
	cat "$EV/storage-static.log" | tail -15
	[ ! -f "$TREE/build/storage-abi/interface-audit.json" ] || die "interface-audit.json appeared; it must come from the live record only"
	if [ $code -ne 0 ] && grep -q "darwinboot-storage-native-metadata/gdb-stop.json" "$EV/storage-static.log"; then
		say "STORAGE ABI STATIC VERIFIED: every static check of audit-storage-interface.py passed on the stage-A kernel"
		say "STORAGE ABI LIVE VERIFIED: NO (no gdb-stop.json; UniXNU 62f203c has no producer for it)"
	else
		die "storage-static: audit-storage-interface.py stopped before its live step (exit $code): static ABI check FAILED"
	fi
	;;
*) die "unknown stage $stage" ;;
esac
