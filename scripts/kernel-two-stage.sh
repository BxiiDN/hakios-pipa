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
OUTDIR=$U/out/pipa/ipados-17.7.11-21H461/pipa
TREE=$OUTDIR/tree KERNEL=$OUTDIR/kernel/kernel.macho
EV=${HAKIOS_EVIDENCE:-$ROOT/logs/two-stage}
STAGE_PATCH=$ROOT/patches/stage-a/0001-reference-kernel-without-hid-and-legacy-display.patch
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
	grep -h '^SKIP ' "$EV/$1-logs/"*.log 2>/dev/null | sort -u > "$EV/$1-skipped.txt" || true
	[ -s "$EV/$1-skipped.txt" ] || return 1
	say "$1: builders that SKIPPED (their archive is not built):"; cat "$EV/$1-skipped.txt"
}

case $stage in
a)
	git -C "$P" apply --check "$STAGE_PATCH" || die "stage-A patch does not apply to the patched port"
	git -C "$P" apply "$STAGE_PATCH"
	trap 'git -C "$P" apply -R "$STAGE_PATCH" && say "stage-A patch removed from the port"' EXIT
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
	if [ -f "$EV/gpu-userland.env" ]; then export "$(cat "$EV/gpu-userland.env")"; say "GPU userland from $UNIXNU_GPU_WORK"; fi
	# build-platform-power.py (with a reference kernel) reads the original kernelcache at the port's path
	# .cache/firmware/kernelcache.macho/kernelcache.release.ipad7.decompressed; UniXNU 62f203c keeps it in out/ipsw/<build>.
	cache=$U/out/ipsw/21H461/kernelcache.decompressed
	[ -f "$cache" ] || die "no decompressed 21H461 kernelcache at $cache"
	[ "$(sha "$cache")" = f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7 ] || die "$cache is not the pinned 21H461 kernelcache"
	mkdir -p "$P/.cache/firmware/kernelcache.macho"
	ln -sfn "$cache" "$P/.cache/firmware/kernelcache.macho/kernelcache.release.ipad7.decompressed"
	python3 "$ROOT/tools/candidate_provenance.py" install --candidate "$OUTDIR/stage-a/kernel.macho" \
		--plan "$OUTDIR/stage-a/kernel.json" --provenance "$EV/stage-a-provenance.json" --tree "$TREE"
	build stage-b
	cp "$TREE/build/sheng-hid-input/abi-audit.json" "$EV/stage-b-hid-abi-audit.json"
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
	say "bison: $(bison --version | head -1); flex: $(flex --version | head -1)"
	(cd "$U" && python3 - <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location('boot_runtime', 'scripts/build-boot-runtime.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print('AdrenoMetal plugin:', module.build_plugin('ios'))
PY
	) > "$EV/gpu-userland.log" 2>&1 || { tail -40 "$EV/gpu-userland.log"; tail -60 "$U/.cache/mesa-tu-ios-build.log" 2>/dev/null; die "gpu-userland: Turnip/AdrenoMetal build failed"; }
	tail -20 "$EV/gpu-userland.log"
	for f in build/mesa-tu-ios/src/freedreno/vulkan/libvulkan_freedreno.dylib build/adreno-metal-bridge/ios/libadreno_metal_bridge.a; do
		[ -f "$U/$f" ] || die "gpu-userland: $f was not produced"
		say "gpu-userland: $(sha "$U/$f")  $(wc -c < "$U/$f" | tr -d ' ')  $f"
		file "$U/$f" | sed 's/^/  /'
	done
	echo "UNIXNU_GPU_WORK=$U" > "$EV/gpu-userland.env"
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
