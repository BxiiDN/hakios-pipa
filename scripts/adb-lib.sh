# Shared by the tablet scripts: everything here only reads from the tablet. Output goes to private/ (gitignored).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
PRIVATE=${HAKIOS_PRIVATE:-$ROOT/private}
mkdir -p "$PRIVATE"; chmod 700 "$PRIVATE"
need_android() {
	need adb
	[ "$(adb get-state 2>/dev/null)" = device ] || die "no Android device on adb (USB debugging on, authorised)"
	local dev; dev=$(adb shell getprop ro.product.device | tr -d '\r')
	[ "$dev" = pipa ] || die "the device is '$dev', not pipa"
}
need_root() { adb shell 'su -c id' 2>/dev/null | grep -q 'uid=0' || die "root (su) is needed for this step"; }
su_cmd() { adb shell "su -c '$*'" | tr -d '\r'; }
