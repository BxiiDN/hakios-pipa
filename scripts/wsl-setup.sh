#!/usr/bin/env bash
# Windows 11 + WSL2 Ubuntu (or Ubuntu/Debian): check (default) or install what the builds here need. Safe to run
# again: it installs only what is missing, keeps existing configuration, and never removes anything.
#   wsl-setup.sh [--install] [--mu-silicium] [--unixnu-toolchain] [--report]
#     --report             only print and record the versions (exit 0): for CI logs; the builds fail on what they lack
#     --install            apt packages that are missing
#     --mu-silicium        also a Python venv in $WORK/venv-mu with uefi-pipa's pip requirements (Mu-Silicium/edk2)
#     --unixnu-toolchain   also UniXNU's Linux XNU toolchain (patched clang, cctools-port): scripts/linux/setup-toolchain.py
# Writes logs/toolchain.txt: each tool, its version, and whether it meets the minimum.
source "$(dirname "$0")/lib.sh"
install=0; mu=0; uxt=0; report=0
for a in "$@"; do case $a in --install) install=1;; --mu-silicium) mu=1;; --unixnu-toolchain) uxt=1;; --report) report=1;;
	*) die "unknown $a";; esac; done

PKGS=(git make cmake ninja-build python3 python3-venv python3-pip clang lld llvm gcc g++ gcc-aarch64-linux-gnu
      binutils-aarch64-linux-gnu flex bison bc libssl-dev zlib1g-dev uuid-dev libbsd-dev device-tree-compiler mtools
      unifdef nasm cpio xz-utils lzma-dev qemu-system-arm qemu-efi-aarch64 qemu-user shellcheck android-sdk-platform-tools)
if grep -qi microsoft /proc/version 2>/dev/null; then say "WSL: $(uname -r)"; else say "not WSL (fine on Ubuntu too)"; fi
[ -r /etc/os-release ] && say "$(. /etc/os-release; echo "$PRETTY_NAME")"
command -v dpkg >/dev/null || die "this script is for apt-based systems; UniXNU's setup-toolchain.py covers dnf/pacman/zypper"
case "$ROOT" in /mnt/[a-z]/*) say "WARNING: the repository is on a Windows drive ($ROOT): clone it under ~ in WSL";; esac

missing=()
for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if [ ${#missing[@]} -gt 0 ]; then
	say "missing packages: ${missing[*]}"
	if [ $install = 1 ]; then sudo apt-get update && sudo apt-get install -y --no-remove "${missing[@]}"; fi
fi

# minimum versions: tool, command printing a version, minimum, who needs it
T=$ROOT/logs/toolchain.txt; : > "$T"; low=0
ver() { "$@" 2>&1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1; }
check() {  # check NAME MIN WHO CMD...
	local name=$1 min=$2 who=$3; shift 3
	local v; v=$(command -v "$1" >/dev/null && ver "$@" || true)
	if [ -z "$v" ]; then echo "MISSING  $name (>= $min) for $who" | tee -a "$T"; low=1
	elif [ "$(printf '%s\n%s\n' "$min" "$v" | sort -V | head -1)" != "$min" ]; then echo "TOO OLD  $name $v (>= $min) for $who" | tee -a "$T"; low=1
	else echo "OK       $name $v for $who" | tee -a "$T"; fi
}
check python3 3.12 "HakiOS checks (3.11 for UniXNU)" python3 --version
check clang 17.0 "HakiOS loader, UniXNU firmware" clang --version
check ld.lld 17.0 "HakiOS loader" ld.lld --version
check lld-link 17.0 "HakiOS loader (PE)" lld-link --version
check aarch64-linux-gnu-gcc 12.0 "U-Boot" aarch64-linux-gnu-gcc --version
check flex 2.6 "U-Boot kconfig, dtc" flex --version
check bison 3.0 "U-Boot kconfig, dtc" bison --version
check cmake 3.20 "UniXNU kernel references" cmake --version
check ninja 1.10 "UniXNU" ninja --version
check dtc 1.6 "device trees" dtc --version
check make 4.0 "everything" make --version
check git 2.30 "everything" git --version
check qemu-system-aarch64 7.0 "QEMU tests" qemu-system-aarch64 --version
check fastboot 33.0 "temporary boot" fastboot --version
check adb 1.0 "read-only device steps" adb --version
[ -f /usr/include/openssl/ssl.h ] && echo "OK       OpenSSL headers" | tee -a "$T" || { echo "MISSING  OpenSSL headers (libssl-dev) for U-Boot" | tee -a "$T"; low=1; }

if [ $mu = 1 ]; then
	U=$WORK/uefi-pipa; [ -f "$U/pip-requirements.txt" ] || SKIP_UEFI_PIPA=0 "$ROOT/scripts/fetch-unixnu.sh"
	V=$WORK/venv-mu
	[ -x "$V/bin/python" ] || python3 -m venv "$V"
	"$V/bin/python" -m pip install -q -r "$U/pip-requirements.txt"
	say "Mu-Silicium Python: $V ($("$V/bin/python" -m pip list 2>/dev/null | grep -c . ) packages)"
	dpkg -s mono-devel >/dev/null 2>&1 || say "Mu-Silicium also wants mono-devel (NuGet): sudo apt-get install mono-devel"
fi
if [ $uxt = 1 ]; then
	X=$WORK/UniXNU; [ -d "$X" ] || "$ROOT/scripts/fetch-unixnu.sh"
	if python3 "$X/scripts/linux/setup-toolchain.py" --check; then say "UniXNU Linux toolchain: present"
	else say "building UniXNU's toolchain (patched LLVM: hours)"; sudo python3 "$X/scripts/linux/setup-toolchain.py"; fi
fi
say "USB from WSL: usbipd-win on Windows (winget install usbipd; usbipd bind / attach --wsl), docs/WSL.md"
say "summary: $T"
[ $report = 1 ] && exit 0
exit $low
