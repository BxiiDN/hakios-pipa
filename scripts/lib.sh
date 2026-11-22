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
