#!/usr/bin/env bash
# Windows 11 + WSL2 Ubuntu: check (default) or install (--install) what the builds and checks here need.
source "$(dirname "$0")/lib.sh"
PKGS=(git make python3 clang lld llvm gcc gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu flex bison bc
      libssl-dev zlib1g-dev device-tree-compiler qemu-system-arm qemu-user shellcheck android-sdk-platform-tools
      cpio xz-utils)
if grep -qi microsoft /proc/version 2>/dev/null; then say "WSL: $(uname -r)"; else say "not WSL: fine on Ubuntu too"; fi
[ -r /etc/os-release ] && say "$(. /etc/os-release; echo "$PRETTY_NAME")"
case "$ROOT" in /mnt/[a-z]/*) say "WARNING: the repository is on a Windows drive ($ROOT): builds are slow and file modes break; clone it under ~ in WSL";; esac
missing=()
for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
py=$(python3 -c 'import sys; print(sys.version_info >= (3, 12))' 2>/dev/null || echo False)
[ "$py" = True ] || say "WARNING: HakiOS's checks want Python 3.12+ ($(python3 --version 2>&1))"
if [ ${#missing[@]} -eq 0 ]; then say "all packages present"; exit 0; fi
say "missing: ${missing[*]}"
if [ "${1:-}" = --install ]; then
	sudo apt-get update
	sudo apt-get install -y "${missing[@]}"
	say "installed"
else
	say "run: scripts/wsl-setup.sh --install"
	exit 1
fi
say "USB to the tablet from WSL: usbipd-win on Windows (winget install usbipd), then usbipd bind/attach --wsl; or run adb/fastboot from Windows (docs/WSL.md)"
