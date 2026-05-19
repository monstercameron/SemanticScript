# crypt_blowfish (vendored bcrypt)

This is the public-domain crypt_blowfish 1.3 implementation by Solar Designer
(Openwall), dropped in directly rather than carried as a git submodule. The
source is small, dependency-free, and well-tested — same vendoring rationale
as `third_party/sqlite/`.

## Pinned version

- Release: **crypt_blowfish 1.3**
- Upstream: <https://www.openwall.com/crypt/>
- License: **public domain** (with fallback "permissive" terms — see the
  prologue comment in `crypt_blowfish.c`). No SemanticScript-side license
  obligation introduced.
- Algorithm compatibility: fully compatible with OpenBSD's bcrypt for the
  `$2b$` prefix (the format we use). See vendored `crypt.3` for compat
  notes on the other historical `$2`/`$2a`/`$2x`/`$2y` prefixes.

## Files vendored

| File | Purpose |
| --- | --- |
| `crypt_blowfish.c` | The eksblowfish key schedule + hash main loop (~1100 lines). The only thing we link. |
| `crypt_blowfish.h` | Public functions: `_crypt_blowfish_rn` (hash), `_crypt_gensalt_blowfish_rn` (salt), `_crypt_output_magic` (error). |
| `crypt_gensalt.c` | Generic salt-string generator shared with other crypt schemes. |
| `crypt_gensalt.h` | Defines `_crypt_itoa64` base-64 alphabet table used by both files. |
| `ow-crypt.h` | Outermost public header — declares `crypt_rn` and friends; we only use it to know the canonical prototypes. |
| `README` | Upstream README (public domain, license terms confirmed). |
| `crypt.3` | Upstream man page; vendored for reference but not installed. |

## Files NOT vendored

- `wrapper.c` — provides `crypt`, `crypt_r`, `crypt_rn` compatibility shims around `getpwnam`-style users. We don't need any of that; our `sem_bcrypt_runtime.c` adapter calls `_crypt_blowfish_rn` and `_crypt_gensalt_blowfish_rn` directly.
- `x86.S` — optional hand-rolled x86 assembly variant of the inner loop (faster on i386). We use the portable C implementation; the assembly is gated by `BF_ASM=1` in upstream's Makefile and ignored without it.
- `glibc-*.diff` — patches for grafting the implementation into glibc's `crypt` subsystem. Not relevant.
- `Makefile`, `PERFORMANCE`, `LINKS` — build artifacts and pointers.

## Why crypt_blowfish?

Three other bcrypt implementations were considered and rejected:

- **OpenBSD `lib/libc/crypt/bcrypt.c`** — also clean and public domain, but requires the OpenBSD-style Blowfish primitive split across `blf.h`/`blowfish.c`. Same algorithm, more files.
- **node-bcrypt** — C++ wrapper around the OpenBSD code. We don't want C++.
- **libsodium `crypto_pwhash`** — only ships Argon2, not bcrypt. Different algorithm.

crypt_blowfish was Solar Designer's deliberate "reusable bcrypt as a C library" project; it has the cleanest standalone shape of the bunch.

## How we use it

The SemanticScript runtime adapter at
`SemanticScript/runtime/native_bcrypt/sem_bcrypt_runtime.c` calls
`_crypt_blowfish_rn` directly with a 60-byte output buffer to compute a
hash, and re-uses the same call to verify (bcrypt re-derives the salt
from the stored hash string, so verify is `hash(plaintext, stored) ==
stored` with a constant-time comparison).

The adapter also owns the CSPRNG for salt bytes (`BCryptGenRandom` on
Windows, `getrandom`/`/dev/urandom` on POSIX) and a base64url encoder
for opaque session tokens.

## Upgrading

1. Download a newer crypt_blowfish-*.tar.gz from
   <https://www.openwall.com/crypt/>.
2. Replace the vendored files with the matching files from the new
   release.
3. Re-run the native_bcrypt build + smoke
   (`SemanticScript/runtime/native_bcrypt/health_demo`) and the
   `test_compiler.py` bcrypt round-trip test.
4. Update the pinned version above.

## Do not edit

These files are upstream-owned. SemanticScript-side adapter code lives in
`SemanticScript/runtime/native_bcrypt/`. Patching the vendored source
would silently diverge from upstream and be lost on the next upgrade.
