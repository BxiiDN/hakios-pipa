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
apply_patches() {  # apply_patches TREE PATCHDIR: each patch applied once; a patch that neither applies nor is applied stops
	local tree=$1 dir=$2 patch
	for patch in "$dir"/*.patch; do
		[ -e "$patch" ] || continue
		if git -C "$tree" apply --check "$patch" 2>/dev/null; then git -C "$tree" apply "$patch"; say "applied $(basename "$patch")"
		elif git -C "$tree" apply --check -R "$patch" 2>/dev/null; then say "already applied: $(basename "$patch")"
		else die "$(basename "$patch") neither applies to $tree nor is applied: the pin moved; refresh the patch"; fi
	done
}
