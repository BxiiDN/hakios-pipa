# Shared by the scripts here: logging to logs/, clear failures, the pinned upstreams.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
WORK=${HAKIOS_WORK:-$ROOT/../hakios-work}
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/$(basename "$0" .sh)-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
# shellcheck source=../UPSTREAM
source <(grep -E '^[A-Z_]+=' "$ROOT/UPSTREAM")
say()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die()  { printf '[%s] ERROR: %s\n' "$(date +%H:%M:%S)" "$*" >&2; printf 'log: %s\n' "$LOG" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed (scripts/wsl-setup.sh --install)"; }
trap 'die "line $LINENO: \"$BASH_COMMAND\" failed"' ERR
say "log: $LOG"
apply_patches() {  # apply_patches TREE PATCHDIR: the series applied in order on the pinned commit
	# Every run puts the tracked files back to the pin (git checkout -f), removes the files the series adds and applies
	# the whole series again in order. No shortcut: a stamp once said "applied" over a tree whose payload.py had been
	# reset, and the dual-boot menu silently went missing. The stamp only records what was applied.
	local tree=$1 dir=$2 patch stamp want
	stamp=$(git -C "$tree" rev-parse --absolute-git-dir)/hakios-patches
	want=$({ git -C "$tree" rev-parse HEAD; cat "$dir"/*.patch 2>/dev/null || true; } | sha256sum | cut -d' ' -f1)   # the pin and the series
	git -C "$tree" checkout -q -f HEAD
	for patch in "$dir"/*.patch; do
		[ -e "$patch" ] || continue
		grep -oE '^\+\+\+ b/[^[:space:]]+' "$patch" | cut -c7- | while read -r f; do
			git -C "$tree" ls-files --error-unmatch "$f" >/dev/null 2>&1 || rm -f "$tree/$f"
		done
	done
	for patch in "$dir"/*.patch; do
		[ -e "$patch" ] || continue
		git -C "$tree" apply "$patch" || die "$(basename "$patch") does not apply to $tree at its pin: refresh the patch"
		say "applied $(basename "$patch")"
	done
	echo "$want" > "$stamp"
}
