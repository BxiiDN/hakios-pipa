#!/usr/bin/env bash
# Storage ABI, LIVE: the original IOBlockStorageDevice / IOService metaclasses observed in a real QEMU guest
# (docs/BOOTSTRAP.md "storage"). Builds the QEMU virt board of xVanTuring/UniXNU-qemu (pinned in UPSTREAM) with the
# pinned UniXNU, boots it under QEMU TCG with UniXNU's scripts/qemu-entry/gdb-stop.py through the port's own
# scripts/build-storage-abi.py, and runs UniXNU's audit-storage-interface.py unchanged on the result.
# macOS with Xcode and `brew install qemu`. Evidence: $HAKIOS_EVIDENCE (default logs/qemu-storage).
source "$(dirname "$0")/lib.sh"
U=$WORK/UniXNU Q=$WORK/UniXNU-qemu
EV=${HAKIOS_EVIDENCE:-$ROOT/logs/qemu-storage}
mkdir -p "$EV"
need qemu-system-aarch64
[ -d "$Q/.git" ] || { git init -q "$Q"; git -C "$Q" remote add origin "$QEMU_PORT_REPOSITORY"; }
git -C "$Q" fetch -q --depth 1 origin "$QEMU_PORT_REF" && git -C "$Q" checkout -q -f --detach FETCH_HEAD
[ "$(git -C "$Q" rev-parse HEAD)" = "$QEMU_PORT_REF" ] || die "UniXNU-qemu is not at $QEMU_PORT_REF"
say "UniXNU-qemu: $QEMU_PORT_REF"
if [ -z "${KERNEL_BUILD_DATE:-}" ]; then
	KERNEL_BUILD_DATE=$(TZ=UTC git -C "$U" log -1 --format=%cd --date=format-local:'%a %b %e %H:%M:%S UTC %Y'); export KERNEL_BUILD_DATE
fi
seed=$(od -An -N8 -tx8 /dev/urandom | tr -d ' \n')   # a fresh platform seed per run; never a device's
step() {  # step NAME COMMAND...: run in UniXNU, keep the log
	say "== $1"; local name=$1; shift
	(cd "$U" && "$@") > "$EV/$name.log" 2>&1 || { tail -60 "$EV/$name.log"; die "$name failed (log $EV/$name.log)"; }
	tail -5 "$EV/$name.log"
}
step defconfig ./unixnu defconfig qemu_defconfig -D ../UniXNU-qemu
step fetch ./unixnu fetch -D ../UniXNU-qemu
step package-kernel ./unixnu build package kernel -D ../UniXNU-qemu
step payload ./unixnu build payload -D ../UniXNU-qemu --unique-chip-id "$seed"
tree=$(dirname "$(dirname "$(find "$U/out" -path '*/tree/scripts/build-storage-abi.py' | head -1)")")
[ -d "$tree" ] || die "no QEMU build tree with scripts/build-storage-abi.py"
say "== storage ABI (live QEMU/gdb) in $tree"
(cd "$tree" && python3 scripts/build-storage-abi.py) > "$EV/storage-abi.log" 2>&1 || { tail -80 "$EV/storage-abi.log"; die "build-storage-abi.py failed"; }
tail -8 "$EV/storage-abi.log"
audit=$tree/build/storage-abi/interface-audit.json
[ -f "$audit" ] || die "no interface-audit.json"
cp "$audit" "$EV/interface-audit.json"
python3 - "$audit" "$tree/build/darwinboot-storage-native-metadata/gdb-stop.json" <<'PY'
import hashlib, json, sys
a = json.load(open(sys.argv[1])); g = json.load(open(sys.argv[2]))
print('interface-audit.json', hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())
print('candidate (QEMU board kernel)', a['candidate_sha256'], '== gdb record kernel', g['kernel_sha256'] == a['candidate_sha256'])
print('live_native_4k', a['live_native_4k'], 'live sizes', a['live_instance_sizes'], 'slots', a['method_slots'])
PY
say "STORAGE ABI LIVE VERIFIED (QEMU virt guest, TCG): not a hardware result"
