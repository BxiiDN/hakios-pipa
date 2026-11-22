# Owner key (VerifiedRoot)

The pipa port's kernel links an owner trust anchor, `_verified_root_key`, from
`build/verified-root-key/libVerifiedRootKey.a` (`CONFIG_XNU_VERIFIED_ROOT_ARCHIVE`). The kernel uses it to check
the signed root policy of the iPadOS root image before it mounts that root. The port calls
`build-verified-root-key.py --pin 70a5ea34…` (the digest of EsaiJJ's own key), but that builder is in no public
repository; we searched the full histories of UniXNU, EsaiJJ/UniXNU-pipa and xVanTuring/UniXNU-pipa, plus GitHub
code search. Patch `patches/unixnu-pipa/0003` adds a builder that follows the tree's contract:

- **Anchor format:** `b'VROOTKEY'` + the 384-byte RSA-3072 modulus + `01 00 01`, which is 395 bytes
  (`kits/VerifiedRoot/tools/manifest.py public_anchor`, `VR_KEY_BYTES`).
- **Output:** an ordinary arm64/iOS 17 Mach-O object that exports `_verified_root_key` in `__DATA_CONST,__const`,
  archived as `libVerifiedRootKey.a`, with `key.json` next to it (anchor digest, kind, archive sha256).
- **Inputs:**
  - `UNIXNU_OWNER_PUBLIC_KEY`: the public key.
  - `UNIXNU_OWNER_KEY_SHA256`: the anchor digest the build must carry. A mismatch stops the build; so does using
    EsaiJJ's pin with any other key.
  - `UNIXNU_OWNER_KEY_KIND`: `owner` or `ephemeral`.

## Your own key

The private half signs the root policies and must stay on your PC. Never commit it, never paste it in a chat, and
never store it as a CI secret. Only the public half goes into the repository.

```bash
mkdir -p ~/.hakios-owner && chmod 700 ~/.hakios-owner
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out ~/.hakios-owner/owner.pem
chmod 600 ~/.hakios-owner/owner.pem
openssl pkey -in ~/.hakios-owner/owner.pem -pubout -out owner/owner-public.pem   # in the hakios-pipa checkout
git add owner/owner-public.pem && git commit -m "owner: public half of the VerifiedRoot owner key" && git push
```

Back up `owner.pem` offline. Without it, no new root policy can be signed for a kernel that carries this anchor.

## CI

`unixnu-build.yml` uses `owner/owner-public.pem` when it exists (kind `owner`). Until then it generates an RSA-3072
key in the run and deletes the private half right away (kind `ephemeral`), so compile, link and prelink can still be
tested. Such a kernel authorizes no root, so `scripts/readiness.sh` reports `MISSING owner key anchor` and never
answers READY for it.
