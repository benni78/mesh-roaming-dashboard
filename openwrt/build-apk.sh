#!/bin/sh
# Baut .apk-Pakete (Alpine-Format, Standard-Paketmanager seit OpenWrt 25.12)
# aus den bereits gebauten .ipk-Dateien (siehe build-ipk.sh).
#
# Hintergrund: Seit OpenWrt 25.12 ist "apk" (Alpine-Stil) der Standard-
# Paketmanager auf vielen Targets, nicht mehr "opkg" - ein .ipk ist dafuer
# das falsche Dateiformat, egal wie korrekt es als opkg-Paket gebaut ist
# ("apk add paket.ipk" schlaegt mit "file format is invalid or inconsistent"
# fehl). Die Umwandlung geht in zwei Schritten (siehe
# openwrt/tools/openwrt-ipk2apk/README-vendored.md fuer Details/Herkunft):
#
#   1. .ipk -> APK v2   (dieses Skript macht das automatisch, reines Python,
#                        keine Zusatz-Tools nötig)
#   2. APK v2 -> APK v3 (braucht "apk-tools >= 3.0" / "apk mkpkg" - dieses
#                        Skript macht das automatisch MIT, falls vorhanden,
#                        sonst gibt es unten die genauen Befehle aus, um es
#                        selbst nachzuholen - braucht dafuer KEIN Docker:
#                        apk-tools baut als normales Meson/C-Projekt direkt
#                        auf jeder Linux-Distribution, s. u.)
#
# WICHTIG: Ob der eigene Router ueberhaupt APK v2 ODER v3 braucht, ist nicht
# in jedem Fall sicher vorhersagbar (manche apk-Versionen akzeptieren v2,
# neuere verlangen v3) - am einfachsten selbst ausprobieren:
#   apk add --allow-untrusted ./paket.apk
# Kommt dieselbe "file format is invalid or inconsistent"-Meldung wie beim
# .ipk, fehlt der v3-Schritt (s. u.).
#
# Aufruf:
#   ./build-ipk.sh && ./build-apk.sh    (erst .ipk, dann daraus .apk bauen)
#   ./build-apk.sh mesh-roaming          nur ein bestimmtes Paket

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIST_DIR="$SCRIPT_DIR/dist"
TOOLS_DIR="$SCRIPT_DIR/tools/openwrt-ipk2apk"
IPK2APK="$TOOLS_DIR/openwrt-ipk2apk.py"
V2_TO_V3="$TOOLS_DIR/convert-apk-v2-to-v3.sh"

if [ ! -f "$IPK2APK" ]; then
	echo "Fehler: $IPK2APK nicht gefunden." >&2
	exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
	echo "Fehler: python3 wird fuer die .ipk->APK-v2-Umwandlung benoetigt." >&2
	exit 1
fi

# apk-tools >= 3.0 ("apk mkpkg") vorhanden? Dann gleich bis APK v3 bauen,
# sonst nur v2 erzeugen und unten erklaeren, wie v3 nachgeholt wird.
#
# WICHTIG: NICHT ueber "apk mkpkg --help" pruefen - das schlaegt fehl, wenn
# apk-tools ohne scdoc (also ohne eingebaute Hilfetexte) gebaut wurde
# ("ERROR: This apk-tools has been built without help"), obwohl "mkpkg"
# selbst dabei ganz normal funktioniert. Stattdessen die Versionsnummer aus
# "apk --version" auswerten (z. B. "apk-tools 3.0.8, compiled for x86_64.").
HAVE_APK_MKPKG=0
if command -v apk >/dev/null 2>&1; then
	apk_major=$(apk --version 2>/dev/null | sed -n 's/^apk-tools \([0-9][0-9]*\)\..*/\1/p')
	if [ -n "$apk_major" ] && [ "$apk_major" -ge 3 ] 2>/dev/null; then
		HAVE_APK_MKPKG=1
	fi
	# OpenWrts eigenes apk (z. B. 3.0.5 auf 25.12) ist ohne "mkpkg" gebaut
	# ("'mkpkg' is not an apk command") - dann bei APK v2 bleiben; das
	# akzeptiert OpenWrt 25.12 per "apk add --allow-untrusted" ebenfalls.
	if apk mkpkg 2>&1 | grep -q "is not an apk command"; then
		HAVE_APK_MKPKG=0
	fi
fi

convert_one() {
	ipk="$1"
	base=$(basename "$ipk" .ipk)
	v2="$DIST_DIR/${base}.apk"

	echo "--- $base ---"
	python3 "$IPK2APK" "$ipk" -o "$v2"

	if [ "$HAVE_APK_MKPKG" -eq 1 ]; then
		echo "apk-tools >= 3.0 gefunden - baue direkt APK v3 ..."
		# "apk mkpkg" uebernimmt Besitzer/Gruppe aus dem Dateisystem - ohne
		# root/fakeroot stuende sonst der Build-Nutzer (statt root:root) als
		# Besitzer im Paket.
		if [ "$(id -u)" -eq 0 ]; then
			"$V2_TO_V3" "$v2"
		elif command -v fakeroot >/dev/null 2>&1; then
			fakeroot "$V2_TO_V3" "$v2"
		else
			echo "WARNUNG: weder root noch fakeroot - Dateien im Paket gehoeren dem Build-Nutzer statt root." >&2
			"$V2_TO_V3" "$v2"
		fi
		echo "fertig (APK v3): $v2"
	else
		echo "APK v2 gebaut: $v2"
		echo "(kein 'apk mkpkg' auf diesem System gefunden - APK v3 noch nicht gebaut, s. u.)"
	fi
}

found=0
if [ "$#" -gt 0 ]; then
	for p in "$@"; do
		ipk="$DIST_DIR/${p}"*.ipk
		# shellcheck disable=SC2086
		for f in $ipk; do
			[ -f "$f" ] && { convert_one "$f"; found=1; }
		done
	done
else
	for f in "$DIST_DIR"/*.ipk; do
		[ -f "$f" ] || continue
		convert_one "$f"
		found=1
	done
fi

if [ "$found" -eq 0 ]; then
	echo "Keine .ipk-Dateien in $DIST_DIR gefunden - zuerst ./build-ipk.sh ausfuehren." >&2
	exit 1
fi

if [ "$HAVE_APK_MKPKG" -eq 0 ]; then
	cat >&2 <<'EOF'

Kein lokales apk-tools >= 3.0 gefunden - die erzeugten *.apk-Dateien in
openwrt/dist/ sind erst APK v2 (Zwischenformat), noch nicht das von
OpenWrt 25.12+ erwartete APK v3.

Zuerst ausprobieren (kostet nichts, manche apk-Versionen akzeptieren v2):
  scp openwrt/dist/*.apk root@<router-ip>:/tmp/
  ssh root@<router-ip> apk add --allow-untrusted /tmp/<paket>.apk

Kommt dieselbe Fehlermeldung wie beim .ipk ("file format is invalid or
inconsistent" bzw. "no such package"), fehlt der v3-Schritt. apk-tools 3.0+
selbst bauen braucht KEIN Docker und KEIN OpenWrt-Buildsystem - es ist ein
ganz normales Meson/C-Projekt, das auf jeder gaengigen Linux-Distribution
(Ubuntu, Debian, Fedora, ...) direkt baut:

  sudo apt install -y git meson ninja-build pkg-config liblua5.3-dev \
                       libssl-dev libzstd-dev
  git clone https://gitlab.alpinelinux.org/alpine/apk-tools.git
  cd apk-tools
  meson setup build
  meson compile -C build

Danach den frisch gebauten Binary (liegt unter build/src/apk) einmalig vor
den eigentlichen Aufruf stellen und dieses Skript erneut laufen lassen -
es findet "apk mkpkg" dann automatisch:

  PATH="$PWD/build/src:$PATH" ./build-apk.sh

(Wer schon ein volles OpenWrt-Buildsystem/SDK ausgecheckt hat, braucht
dafuer trotzdem KEINEN Checkout-spezifischen Weg zu suchen - das Bauen von
apk-tools *innerhalb* des OpenWrt-Buildroots als Host-Tool ist laut
OpenWrt-Forum fehleranfaelliger (u. a. Lua-Versionskonflikte zwischen
lua5.1/lua5.3 je nach Branch) als der obige direkte Weg gegen den
Upstream-Quellcode.)

Alternative, falls auf dem eigenen Rechner aus anderen Gruenden kein
Compiler/Meson installiert werden soll: ein kurzlebiger Alpine-Edge-
Container (enthaelt apk-tools 3.0+ bereits fertig gebaut):

  docker run --rm -v "$PWD":/w -w /w alpine:edge sh -c '
    apk add --no-cache apk-tools bash util-linux gzip tar coreutils findutils fakeroot &&
    fakeroot openwrt/tools/openwrt-ipk2apk/convert-apk-v2-to-v3.sh openwrt/dist/*.apk
  '

Beide Wege wandeln die *.apk-Dateien in openwrt/dist/ in-place zu APK v3
um. Danach wie gewohnt per scp auf den Router kopieren und
"apk add --allow-untrusted ./paket.apk" installieren.
EOF
fi
