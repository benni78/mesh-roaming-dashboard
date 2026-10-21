# Vendored: openwrt-ipk2apk

These two files are vendored from
[rychly/openwrt-ipk2apk](https://github.com/rychly/openwrt-ipk2apk),
commit `60caa88a2c5907dc76884b58742304161d6448` (2026-07-10), under the
MIT License (see [`LICENSE`](LICENSE) in this folder — the original
project's license, kept alongside the files as required). Two small,
documented local patches were applied — see "Local patches" below.

They are **not part of this project's own PolyForm Noncommercial license**
— only these two files (`openwrt-ipk2apk.py`, `convert-apk-v2-to-v3.sh`)
are MIT-licensed, same as upstream. Everything else in this repository
keeps the license stated in the top-level [`LICENSE`](../../../LICENSE).

## Why this is here

Since OpenWrt 25.12, the default package manager on many targets is `apk`
(Alpine-style), not `opkg`. An `.ipk` built by [`../../build-ipk.sh`](../../build-ipk.sh)
is the correct, real opkg format — but it is a **different package format**
than `apk` expects, and `apk add`/`apk install` will refuse it outright
(`file format is invalid or inconsistent`) regardless of how correctly the
`.ipk` itself is built. There is no single-step fix: OpenWrt's `apk` only
accepts the newer "APK v3" (ADB container) format, and converting there
takes two stages:

1. `openwrt-ipk2apk.py` (pure Python 3 standard library, no dependencies):
   `.ipk` → APK v2 (an intermediate, Alpine-compatible format).
2. `convert-apk-v2-to-v3.sh`: APK v2 → APK v3. This step needs a real
   `apk` binary with `apk mkpkg` support, i.e. **apk-tools ≥ 3.0** — not
   available in this project's own build/sandbox environment, see
   [`docs/deployment-openwrt.md`](../../../docs/deployment-openwrt.md)
   for how to get it (e.g. a throwaway Alpine Edge container) and run
   this step yourself.

See [`openwrt/build-apk.sh`](../../build-apk.sh) for the orchestration
script that runs step 1 automatically and tells you exactly what to run
for step 2.

## Local patches

### 1. `arch: all` → `arch: noarch` (openwrt-ipk2apk.py)

`openwrt-ipk2apk.py` originally copied the IPK control file's
`Architecture` value straight into the generated `.PKGINFO`'s `arch`
field. opkg's convention for an architecture-independent package is
`Architecture: all`; APK's (Alpine's) convention for the same concept is
`arch = noarch` — `apk`'s solver does not treat `all` as a wildcard or
alias for "any architecture," so a package left with `arch = all`
installs cleanly as far as the package *format* goes but is then
rejected by the real `apk add` on an actual OpenWrt 25.12 router:

```
ERROR: unable to select packages:
  mesh-roaming-1.0-r1:
    error: uninstallable
    arch: all
    satisfies: world[mesh-roaming><...>]
```

(confirmed in practice on a HiLink-RM65-B running OpenWrt 25.12.5 — the
package converted and signed without any error, `apk mkpkg` accepted it,
and it still refused to install, with the error explicitly naming
`arch: all` as the offending field.)

A small `_apk_arch()` helper was added that maps `all` → `noarch` when
writing `.PKGINFO`; every other architecture value (e.g. an
OpenWrt-target-specific IPK arch like `aarch64_cortex-a53`) is passed
through unchanged, since this tool has so far only ever been used on
`Architecture: all` packages and no translation table exists yet for
target-specific arches.

### 2. `--help`-based `apk mkpkg` detection (convert-apk-v2-to-v3.sh, build-apk.sh)

`convert-apk-v2-to-v3.sh`'s `check_deps()` originally detected a usable
`apk mkpkg` by running `apk mkpkg --help` and grepping the output for the
word `mkpkg`. That check fails — with `apk mkpkg not available (apk-tools
>= 3.0 required)` — on any `apk-tools` build that was compiled without
`scdoc` (the tool that generates its bundled help text): the binary then
prints `ERROR: This apk-tools has been built without help` instead, which
doesn't contain the word `mkpkg` anywhere, even though `mkpkg` itself works
fine. Since `scdoc` is an optional, rarely-preinstalled build dependency
(not pulled in by the plain `meson setup build && meson compile -C build`
sequence in `docs/deployment-openwrt.md`), this false negative is the
common case, not an edge case, when building `apk-tools` from source on a
regular Linux machine — confirmed in practice building apk-tools 3.0.8
this way on Ubuntu.

The check was changed to read the version number from `apk --version`
(e.g. `apk-tools 3.0.8, compiled for x86_64.`) instead of relying on
`--help` output. `build-apk.sh`'s own, separate detection logic had the
same bug and was fixed the same way. Nothing else in either file was
touched.
