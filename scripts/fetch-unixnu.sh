#!/usr/bin/env bash
# UniXNU, the pipa port, its reference port and uefi-pipa at the commits pinned in UPSTREAM, beside this repository.
# Submodules are left to `./unixnu fetch` (UniXNU's own), which needs the network and the port's -D directory.
source "$(dirname "$0")/lib.sh"
need git
mkdir -p "$WORK"
pin() {  # pin DIR URL REF
	local dir=$WORK/$1
	[ -d "$dir/.git" ] || { git init -q "$dir"; git -C "$dir" remote add origin "$2"; }
	git -C "$dir" fetch -q --depth 1 origin "$3" || die "could not fetch $2 at $3"
	git -C "$dir" checkout -q -f --detach FETCH_HEAD   # tracked files back to the pin; patches are re-applied below
	[ "$(git -C "$dir" rev-parse HEAD)" = "$3" ] || die "$1 is not at $3"
	say "$1: $3"
}
pin UniXNU "$UNIXNU_REPOSITORY" "$UNIXNU_REF"
pin UniXNU-pipa "$PIPA_PORT_REPOSITORY" "$PIPA_PORT_REF"
pin UniXNU-pipa-reference "$PIPA_REFERENCE_REPOSITORY" "$PIPA_REFERENCE_REF"
[ "${SKIP_UEFI_PIPA:-0}" = 1 ] || pin uefi-pipa "$UEFI_PIPA_REPOSITORY" "$UEFI_PIPA_REF"
# patches/unixnu, patches/unixnu-pipa: the Android-first boot menu (docs/DUAL-BOOT.md); HAKIOS_UNIXNU_PATCHES=0: none
if [ "${HAKIOS_UNIXNU_PATCHES:-1}" = 1 ]; then
	apply_patches "$WORK/UniXNU" "$ROOT/patches/unixnu"
	apply_patches "$WORK/UniXNU-pipa" "$ROOT/patches/unixnu-pipa"
fi
# the iPadOS 17 profile must still name the XNU this repository records
profile=$WORK/UniXNU/profiles/os/ipados-17.7.11-21H461/profile.toml
grep -q "\"xnu_revision\" = \"$XNU_REF\"" "$profile" || die "UniXNU's iPadOS 17.7.11 profile no longer pins $XNU_TAG ($XNU_REF)"
say "iPadOS 17.7.11 profile: $XNU_TAG ($XNU_REF)"
git ls-remote https://github.com/apple-oss-distributions/xnu "refs/tags/$XNU_TAG^{}" | grep -q "^$XNU_REF" \
	|| die "$XNU_TAG is not $XNU_REF at apple-oss-distributions/xnu"
say "apple-oss-distributions/xnu $XNU_TAG = $XNU_REF: confirmed"
