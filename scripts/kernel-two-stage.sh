#!/usr/bin/env bash
# Two-stage kernel build for the pipa port (docs/BOOTSTRAP.md). Needs macOS with the Xcode iphoneos SDK, the IPSW
# input UniXNU fetches, and UNIXNU_OWNER_* set (docs/OWNER-KEY.md).
#   kernel-two-stage.sh a        stage A: reference kernel without ShengHidInput and the legacy display archive,
#                                built and prelinked by UniXNU; records its provenance (never a boot candidate)
#   kernel-two-stage.sh b        stage B: the full board, every archive, qualified against the stage-A kernel
#   kernel-two-stage.sh recheck  qualify ShengHidInput again against the final kernel; the bindings must not move
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
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }   # shasum is on macOS and Ubuntu alike
NM=$(command -v llvm-nm || true); [ -n "$NM" ] || NM="xcrun nm"
command -v brew >/dev/null && export PATH="$(brew --prefix llvm)/bin:$PATH"   # llvm-objcopy for the HID builder
[ -n "${UNIXNU_OWNER_PUBLIC_KEY:-}" ] || die "UNIXNU_OWNER_PUBLIC_KEY is not set (docs/OWNER-KEY.md)"

save_logs() {  # save_logs NAME
	mkdir -p "$EV/$1-logs"
	cp "$OUTDIR"/logs/*.log "$EV/$1-logs/" 2>/dev/null || true
}
evidence() {  # evidence NAME: plan, hashes and the exported symbols of the kernel just built
	[ -f "$KERNEL" ] || return 0
	cp "$OUTDIR/kernel/kernel.json" "$EV/$1-kernel.json"
	[ -f "$OUTDIR/kernel/kernel.map.json" ] && cp "$OUTDIR/kernel/kernel.map.json" "$EV/$1-kernel.map.json"
	{ echo "$(sha "$KERNEL")  kernel.macho ($(wc -c < "$KERNEL") bytes)"
	  find "$TREE/build" -name '*.a' -type f | sort | while read -r a; do echo "$(sha "$a")  ${a#"$TREE"/}"; done
	} > "$EV/$1-sha256.txt"
	$NM -g --defined-only "$KERNEL" 2>/dev/null | sort -k3 > "$EV/$1-kernel-exports.txt" || true
	say "$1: kernel.macho $(head -1 "$EV/$1-sha256.txt")"
}
build() {  # build NAME
	(cd "$U" && ./unixnu defconfig pipa_defconfig -D ../UniXNU-pipa && ./unixnu build kernel) || { save_logs "$1"; die "$1: unixnu build kernel failed"; }
	save_logs "$1"; evidence "$1"
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
*) die "unknown stage $stage" ;;
esac
