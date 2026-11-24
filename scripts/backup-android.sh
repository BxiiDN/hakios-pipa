#!/usr/bin/env bash
# Android backup to this PC without root, before any change to userdata is even proposed (docs/IPADOS-PARTITION.md, 10-11).
# Read-only on the tablet: adb pull, pm, settings, dumpsys, df, find and sha256sum only; nothing is installed, deleted,
# pushed or changed there.
#   backup-android.sh plan DIR          preflight, copies nothing: tablet, battery, size of /sdcard, free space where DIR would
#                                       be, DIR's file system (ext4 in WSL, not /mnt/<drive>), unreadable folders
#   backup-android.sh backup DIR        copy into DIR (must not exist): /sdcard, the APK splits of every user app, package
#                                       list, settings (system/secure/global); hash every file ON THE TABLET and on this PC and
#                                       compare them (meta/compare.txt); SHA256SUMS over DIR
#   backup-android.sh verify DIR        DIR against its SHA256SUMS, and the tablet-vs-PC comparison made at backup time
#   backup-android.sh restore-plan DIR  print (only print) the commands that would put it back after a wipe
# adb is Windows' adb.exe here: every PC-side path given to it is converted with `wslpath -w`.
# Not covered (a non-root shell has no access): app private data, accounts, SMS/call log, Wi-Fi keys. Those come from
# HyperOS "Back up & restore" (its archive in /sdcard/MIUI/backup is copied with /sdcard), Google / Mi Cloud and each
# app's own export (chat backups, authenticator recovery codes).
# DIR holds personal data: keep it on this PC, never in a Git tree or an upload.
source "$(dirname "$0")/adb-lib.sh"
adb_sh() { { adb shell "$1" || true; } | tr -d '\r'; }   # partial reads (du, find over unreadable folders) are expected
# adb.exe of Windows (driven from WSL) needs Windows paths; a Linux adb takes the path as it is.
winpath() { if command -v wslpath >/dev/null 2>&1 && [[ "$(command -v adb)" == /mnt/* || "$(head -c 300 "$(command -v adb)" 2>/dev/null)" == *adb.exe* ]]; then wslpath -w "$1"; else printf '%s' "$1"; fi; }
# PC-side subdirectory joined the way the adb in use expects it
pcjoin() { case "$1" in *\\*) printf '%s\\%s' "$1" "$2" ;; *) printf '%s/%s' "$1" "$2" ;; esac; }
mode=${1:?usage: backup-android.sh plan|backup|verify|restore-plan DIR}
dir=${2:?usage: backup-android.sh plan|backup|verify|restore-plan DIR}
dir=$(realpath -m "$dir")
case $dir in "$ROOT"|"$ROOT"/*) die "$dir is inside the repository: personal data never goes there" ;; esac
case $dir in /mnt/*) die "$dir is on a Windows drive: NTFS refuses some Android file names; use a WSL path such as ~/android-backup" ;; esac

# After a restart Android keeps the user's storage (FBE credential-encrypted) locked until the screen is unlocked once;
# /sdcard is then absent for adb and a backup would be empty.
need_unlocked() {
	adb_sh 'dumpsys user' | grep -q 'State: RUNNING_UNLOCKED' && [ "$(adb_sh 'ls -A /sdcard/ 2>/dev/null | wc -l')" -gt 0 ] \
		|| die "user storage is locked (RUNNING_LOCKED): unlock the tablet's screen once, then run again"
}

hash_tree() { (cd "$1" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 -r sha256sum); }

# "hash  ./path" lines of the tablet's /sdcard, sorted by path
device_hashes() { adb_sh 'cd /sdcard/ && find . -type f -exec sha256sum {} + 2>/dev/null' | LC_ALL=C sort; }

case $mode in
plan)
	need_android
	need_unlocked
	[ -e "$dir" ] && die "$dir exists; choose a new directory"
	parent=$(dirname "$dir"); while [ ! -d "$parent" ]; do parent=$(dirname "$parent"); done
	kb=$(adb_sh 'du -sk /sdcard/ 2>/dev/null' | awk '{print $1}')
	files=$(adb_sh 'find /sdcard/ -type f 2>/dev/null | wc -l')
	unreadable=$(adb_sh 'find /sdcard/ -type d ! -readable 2>/dev/null | head -20')
	free=$(df -Pk "$parent" | awk 'NR==2 {print $4}')
	fs=$(df -PT "$parent" | awk 'NR==2 {print $2}')
	battery=$(adb_sh 'dumpsys battery' | awk '$1 == "level:" {print $2; exit}')
	say "tablet: $(adb_sh 'getprop ro.build.version.incremental') slot $(adb_sh 'getprop ro.boot.slot_suffix'), battery ${battery}%"
	say "/sdcard: $files files, $((kb / 1024)) MiB; APKs of $(adb_sh 'pm list packages -3' | wc -l) user apps on top"
	say "target: $dir on $fs, $((free / 1024)) MiB free"
	[ -n "$unreadable" ] && say "not readable by adb (not copied; covered by HyperOS backup or the app itself):" && printf '  %s\n' $unreadable
	ok=1
	[ "$free" -gt $((kb * 12 / 10 + 4 * 1024 * 1024)) ] || { say "FAIL: not enough free space (need /sdcard + 20 % + 4 GiB for APKs)"; ok=0; }
	[ "${battery:-0}" -ge 50 ] || { say "FAIL: battery under 50 %; charge first"; ok=0; }
	[ "$ok" = 1 ] && say "PLAN PASS: backup can start (it copies personal data: the owner's approval comes first)" || exit 1
	;;
backup)
	need_android
	need_unlocked
	[ -e "$dir" ] && die "$dir exists; choose a new directory"
	mkdir -p "$dir/sdcard" "$dir/apks" "$dir/meta"
	chmod 700 "$dir"
	adb_sh 'getprop ro.build.version.incremental; uname -r; getprop ro.boot.slot_suffix' > "$dir/meta/device.txt"
	adb_sh 'pm list packages -f -3' > "$dir/meta/packages-user.txt"
	adb_sh 'pm list packages -f' > "$dir/meta/packages-all.txt"
	for ns in system secure global; do adb_sh "settings list $ns" > "$dir/meta/settings-$ns.txt"; done
	: > "$dir/meta/apk-compare.txt"
	sed -n 's/^package:.*=\([^=]*\)$/\1/p' "$dir/meta/packages-user.txt" | while read -r pkg; do
		mkdir -p "$dir/apks/$pkg"
		adb_sh "pm path $pkg" | sed -n 's/^package://p' | while read -r path; do
			name=$(basename "$path")
			(cd / && adb pull "$path" "$(pcjoin "$(winpath "$dir/apks/$pkg")" "$name")" >/dev/null 2>&1) || say "WARN: could not pull $path"
			want=$(adb_sh "sha256sum '$path'" | cut -c1-64)
			got=$({ sha256sum "$dir/apks/$pkg/$name" 2>/dev/null || true; } | cut -c1-64)
			echo "$([ -n "$want" ] && [ "$want" = "$got" ] && echo SAME || echo DIFF) $pkg/$name" >> "$dir/meta/apk-compare.txt"
		done
	done
	say "pulling /sdcard (about 30 MB/s)"
	(cd / && adb pull /sdcard/. "$(winpath "$dir/sdcard")" >"$dir/meta/sdcard-pull.log" 2>&1) \
		|| say "WARN: adb pull /sdcard reported errors (meta/sdcard-pull.log)"
	say "hashing /sdcard on the tablet (read only) and here"
	device_hashes > "$dir/meta/device-sha256.txt"
	(cd "$dir/sdcard" && find . -type f -print0 | xargs -0 -r sha256sum | LC_ALL=C sort) > "$dir/meta/pc-sha256.txt"
	# lines only on the tablet = missing or different here; lines only here = extra (e.g. a 0-byte file from a failed pull)
	LC_ALL=C comm -23 "$dir/meta/device-sha256.txt" "$dir/meta/pc-sha256.txt" > "$dir/meta/missing-or-different.txt"
	LC_ALL=C comm -13 "$dir/meta/device-sha256.txt" "$dir/meta/pc-sha256.txt" > "$dir/meta/extra-on-pc.txt"
	{ echo "tablet files: $(wc -l < "$dir/meta/device-sha256.txt")"
	  echo "identical on the PC: $(LC_ALL=C comm -12 "$dir/meta/device-sha256.txt" "$dir/meta/pc-sha256.txt" | wc -l)"
	  echo "missing or different: $(wc -l < "$dir/meta/missing-or-different.txt")"
	  echo "extra on the PC: $(wc -l < "$dir/meta/extra-on-pc.txt")"
	  echo "APK splits identical: $(grep -c '^SAME' "$dir/meta/apk-compare.txt") of $(wc -l < "$dir/meta/apk-compare.txt")"
	} > "$dir/meta/compare.txt"
	hash_tree "$dir" > "$dir/SHA256SUMS"
	cat "$dir/meta/compare.txt"
	if [ -s "$dir/meta/missing-or-different.txt" ] || [ -s "$dir/meta/extra-on-pc.txt" ] || grep -q '^DIFF' "$dir/meta/apk-compare.txt"; then
		say "BACKUP INCOMPLETE: see meta/missing-or-different.txt, meta/extra-on-pc.txt, meta/apk-compare.txt"; exit 1
	fi
	say "BACKUP COMPLETE: every /sdcard file and APK split readable by adb is byte-identical on this PC"
	;;
verify)
	[ -f "$dir/SHA256SUMS" ] || die "no SHA256SUMS in $dir"
	diff <(hash_tree "$dir") "$dir/SHA256SUMS" >/dev/null || die "backup differs from its SHA256SUMS: changed or damaged since"
	[ -f "$dir/meta/compare.txt" ] && cat "$dir/meta/compare.txt"
	if [ -f "$dir/meta/missing-or-different.txt" ] && { [ -s "$dir/meta/missing-or-different.txt" ] || [ -s "$dir/meta/extra-on-pc.txt" ]; }; then
		die "intact, but incomplete against the tablet at backup time"
	fi
	say "BACKUP VERIFIED: $(wc -l < "$dir/SHA256SUMS") files intact"
	;;
restore-plan)
	[ -f "$dir/SHA256SUMS" ] || die "no SHA256SUMS in $dir"
	echo "# Restore after a wipe -- printed only, nothing is run. Verify first: backup-android.sh verify $dir"
	echo "# 1. Android first boot, same account; HyperOS Back up & restore restores its own archive after step 2."
	echo "# 2. Files (from the WSL root, so adb.exe sees the path):"
	echo "cd / && adb push \"$(winpath "$dir/sdcard")\\.\" /sdcard/"
	echo "# 3. User apps, one install per package with all its splits:"
	for d in "$dir"/apks/*/; do
		[ -d "$d" ] || continue
		set -- "$d"*.apk; [ -e "$1" ] || continue
		printf 'adb install-multiple'; for a in "$@"; do printf ' "%s"' "$(winpath "$a")"; done; echo
	done
	echo "# 4. Settings are a record (meta/settings-*.txt) to compare by hand; they are not written back blindly."
	;;
*) die "unknown mode $mode" ;;
esac
