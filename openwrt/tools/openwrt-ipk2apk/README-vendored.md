# Vendored: openwrt-ipk2apk

These two files are vendored unmodified from
[rychly/openwrt-ipk2apk](https://github.com/rychly/openwrt-ipk2apk),
commit `60caa88a2c5907dc76884b58742304161d6448` (2026-07-10), under the
MIT License (see [`LICENSE`](LICENSE) in this folder — the original
project's license, kept alongside the files as required).

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
