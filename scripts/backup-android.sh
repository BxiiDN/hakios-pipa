#!/usr/bin/env bash
# Android backup to this PC without root, before any change to userdata is even proposed (docs/IPADOS-PARTITION.md, 10).
# Read-only on the tablet: adb pull, pm, settings and dumpsys only; nothing is installed, deleted or changed there.
#   backup-android.sh backup DIR     copy into DIR (must not exist): /sdcard, the APKs of user apps, the package list,
#                                    settings (system/secure/global), device facts; then SHA256SUMS over every file
#   backup-android.sh verify DIR     re-hash DIR against its SHA256SUMS (exit 1 on any difference)
# Not covered (Android gives a non-root shell no access): app private data, accounts, SMS/call log, Wi-Fi keys. Those come
# from HyperOS "Back up & restore" (its archive lands in /sdcard/MIUI/backup and is copied with /sdcard), Google / Mi Cloud,
# and each app's own export (chat backups, authenticator recovery codes) -- docs/IPADOS-PARTITION.md, table of section 10.
# DIR holds personal data: keep it on this PC, never in a Git tree or an upload.
source "$(dirname "$0")/adb-lib.sh"
adb_sh() { adb shell "$1" | tr -d '\r'; }
mode=${1:?usage: backup-android.sh backup|verify DIR}
dir=${2:?usage: backup-android.sh backup|verify DIR}
case $dir in "$ROOT"*) die "$dir is inside the repository: personal data never goes there" ;; esac

hash_tree() { (cd "$1" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum); }

case $mode in
backup)
	need_android
	[ -e "$dir" ] && die "$dir exists; choose a new directory"
	mkdir -p "$dir/sdcard" "$dir/apks" "$dir/meta"
	adb_sh 'getprop ro.build.version.incremental; uname -r; getprop ro.boot.slot_suffix' > "$dir/meta/device.txt"
	adb_sh 'pm list packages -f -3' | tr -d '\r' > "$dir/meta/packages-user.txt"
	adb_sh 'pm list packages -f' | tr -d '\r' > "$dir/meta/packages-all.txt"
	for ns in system secure global; do adb_sh "settings list $ns" | tr -d '\r' > "$dir/meta/settings-$ns.txt"; done
	# user apps: every APK split of each package (base and splits), as pm reports them
	sed -n 's/^package://p' "$dir/meta/packages-user.txt" | sed 's/=\([^=]*\)$/ \1/' | while read -r apk pkg; do
		mkdir -p "$dir/apks/$pkg"
		adb_sh "pm path $pkg" | tr -d '\r' | sed -n 's/^package://p' | while read -r path; do
			adb pull "$path" "$dir/apks/$pkg/" >/dev/null || say "WARN: could not pull $path"
		done
	done
	say "pulling /sdcard (this takes a while)"
	adb pull /sdcard/. "$dir/sdcard/" >"$dir/meta/sdcard-pull.log" 2>&1 || say "WARN: adb pull /sdcard reported errors (meta/sdcard-pull.log)"
	adb_sh 'find /sdcard/ -type f 2>/dev/null | wc -l' | tr -d '\r' > "$dir/meta/sdcard-file-count-on-tablet.txt"
	find "$dir/sdcard" -type f | wc -l > "$dir/meta/sdcard-file-count-on-pc.txt"
	hash_tree "$dir" > "$dir/SHA256SUMS"
	say "backup in $dir: $(wc -l < "$dir/SHA256SUMS") files; tablet listed $(cat "$dir/meta/sdcard-file-count-on-tablet.txt") files in /sdcard, PC has $(cat "$dir/meta/sdcard-file-count-on-pc.txt")"
	;;
verify)
	[ -f "$dir/SHA256SUMS" ] || die "no SHA256SUMS in $dir"
	if diff <(hash_tree "$dir") "$dir/SHA256SUMS" >/dev/null; then say "BACKUP VERIFIED: $(wc -l < "$dir/SHA256SUMS") files"; else die "backup differs from its SHA256SUMS"; fi
	;;
*) die "unknown mode $mode" ;;
esac
