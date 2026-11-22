#!/usr/bin/env bash
# After a temporary boot attempt, back in Android: the previous boot's kernel/firmware log kept in ramoops (pstore),
# read-only, into logs/boot-TIME/. UniXNU-pipa and uefi-pipa write their logs there.
source "$(dirname "$0")/adb-lib.sh"
need_android; need_root
D=$ROOT/logs/boot-$(date +%Y%m%d-%H%M%S); mkdir -p "$D"
for f in $(su_cmd 'ls /sys/fs/pstore 2>/dev/null'); do su_cmd "cat /sys/fs/pstore/$f" > "$D/$f"; done
su_cmd 'cat /proc/last_kmsg 2>/dev/null' > "$D/last_kmsg" || true
ls -la "$D"; say "log: $D"
