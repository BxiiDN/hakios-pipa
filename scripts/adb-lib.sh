# Shared by the tablet scripts. Reads from the tablet are streamed straight to this PC with `adb exec-out`: nothing is
# written to the tablet's storage, not even a temporary file. Output goes to private/ (gitignored, mode 700).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
PRIVATE=${HAKIOS_PRIVATE:-$ROOT/private}
mkdir -p "$PRIVATE"; chmod 700 "$PRIVATE"
need_android() {
	need adb
	[ "$(adb get-state 2>/dev/null | tr -d '\r')" = device ] || die "no Android device on adb (USB debugging on, authorised)"
	local dev; dev=$(adb shell getprop ro.product.device | tr -d '\r')
	[ "$dev" = pipa ] || die "the device is '$dev', not pipa"
}
# Root is used only where Android gives no other read access (/sys/firmware/fdt, block devices). Nothing here roots
# the tablet or changes its security; without root the step says so and stops.
has_root() { adb shell 'su -c id' 2>/dev/null | grep -q 'uid=0'; }
need_root() { has_root || die "this step needs root (su) on the tablet; it is skipped, not worked around"; }
su_cmd() { adb shell "su -c '$*'" | tr -d '\r'; }
# stream FILE-ON-TABLET OUT: root read of a file or block device, straight to OUT on this PC
stream() { adb exec-out "su -c 'cat $1'" > "$2"; }
# stream_part NAME OUT: a partition by name, read-only; its size checked against what arrived
stream_part() {
	local dev=/dev/block/by-name/$1 want got
	want=$(su_cmd "blockdev --getsize64 $dev") || return 1
	stream "$dev" "$2"
	got=$(stat -c %s "$2")
	[ "$got" = "$want" ] || { say "$1: $got of $want bytes arrived"; return 1; }
}
