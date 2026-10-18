#!/bin/sh
# Baut .ipk-Pakete aus openwrt/<paketname>/{control,files}/ - ohne OpenWrt-SDK,
# nur mit tar/gzip (reicht fuer reine Skript-Pakete, Architecture: all).
#
# WICHTIG zum Format: Ein opkg-.ipk ist KEIN ar-Archiv (anders als ein
# Debian-.deb, dem es oberflaechlich aehnelt) - es ist ein einzelner,
# gzip-komprimierter tar-Stream mit drei Dateien darin:
#   ./debian-binary   - enthaelt nur "2.0"
#   ./data.tar.gz     - der zu installierende Dateibaum (files/ als Wurzel "/")
#   ./control.tar.gz  - control, ggf. conffiles/postinst/prerm (Paket-Metadaten)
# Reihenfolge und Pfadschreibweise ("./xyz", nicht "xyz") entsprechen dem
# offiziellen OpenWrt-Skript "ipkg-build". Eine fruehere Version dieses
# Skripts hat das faelschlich als ar-Archiv gebaut (wie ein .deb) - das ist
# fuer ein echtes opkg auf dem Router NICHT installierbar.
#
# WICHTIG zum Zielgeraet: Dieses Skript auf einem gewoehnlichen Linux-
# Rechner ausfuehren (z. B. dem eigenen PC/Laptop, einer VM, WSL), nicht
# zwingend auf dem Router selbst - schadet aber auch nicht, da hier nur
# noch simples tar/gzip benutzt wird (kein ar mehr nötig).
#
# WICHTIG zum Paketmanager: Ab OpenWrt 25.12 ist "apk" (Alpine-Stil) der
# Standard-Paketmanager statt "opkg" - ein .ipk lässt sich dort grundsätzlich
# NICHT mit "apk add"/"apk install" installieren (anderes Paketformat, nicht
# nur ein anderer Befehl). Pruefen, welcher Paketmanager auf dem Zielrouter
# läuft ("opkg --version" bzw. "apk --version"). Für apk-basierte Router
# siehe docs/deployment-openwrt.md, Abschnitt "OpenWrt 25.12+ (apk)" und
# openwrt/tools/ (Konvertierung .ipk -> .apk).
#
# Aufruf:
#   ./build-ipk.sh                 baut alle Pakete in diesem Verzeichnis
#   ./build-ipk.sh mesh-roaming     baut nur das angegebene Paket
#
# Ergebnis landet in openwrt/dist/<paket>_<version>_all.ipk
#
# Hinweis: Das erzeugte Archiv wurde nicht gegen ein echtes opkg auf einem
# Router getestet (in dieser Umgebung steht kein OpenWrt zur Verfuegung) -
# vor dem produktiven Einsatz einmal mit "opkg install ./paket.ipk" auf
# einem Testgeraet pruefen.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIST_DIR="$SCRIPT_DIR/dist"
mkdir -p "$DIST_DIR"

# GNU tar unterstuetzt --owner/--group/--numeric-owner/--format/--sort (fuer
# reproduzierbare root:root-Archive, unabhaengig vom Build-Nutzer). BusyBox
# tar kennt diese Optionen nicht - dort einfach weglassen; der Rest des
# Skripts kommt mit reinem POSIX-tar aus.
TAR_EXTRA_FLAGS=""
if tar --version 2>/dev/null | grep -qi "GNU tar"; then
	TAR_EXTRA_FLAGS="--owner=0 --group=0 --numeric-owner"
fi
OUTER_TAR_FLAGS="$TAR_EXTRA_FLAGS"
if tar --version 2>/dev/null | grep -qi "GNU tar"; then
	OUTER_TAR_FLAGS="$TAR_EXTRA_FLAGS --format=gnu --sort=name"
fi

build_one() {
	pkgdir="$1"
	src="$SCRIPT_DIR/$pkgdir"

	if [ ! -f "$src/control/control" ]; then
		echo "uebersprungen: $pkgdir (keine control/control-Datei)" >&2
		return 0
	fi

	name=$(sed -n 's/^Package: *//p' "$src/control/control" | head -n1)
	version=$(sed -n 's/^Version: *//p' "$src/control/control" | head -n1)
	[ -n "$name" ] || { echo "Fehler: kein 'Package:' in $src/control/control" >&2; exit 1; }
	[ -n "$version" ] || { echo "Fehler: kein 'Version:' in $src/control/control" >&2; exit 1; }

	work=$(mktemp -d)
	trap 'rm -rf "$work"' EXIT

	# control.tar.gz: nur die Dateien, die tatsaechlich existieren
	ctrl_files=""
	for f in control conffiles postinst preinst prerm postrm; do
		[ -f "$src/control/$f" ] && ctrl_files="$ctrl_files $f"
	done
	# shellcheck disable=SC2086
	tar -C "$src/control" $TAR_EXTRA_FLAGS \
		-czf "$work/control.tar.gz" $ctrl_files

	# data.tar.gz: der komplette Zielbaum, falls vorhanden (ein reines
	# Metapaket ohne eigene Dateien ist zulaessig und hat kein files/)
	if [ -d "$src/files" ]; then
		# shellcheck disable=SC2086
		tar -C "$src/files" $TAR_EXTRA_FLAGS \
			-czf "$work/data.tar.gz" .
	else
		# shellcheck disable=SC2086
		tar $TAR_EXTRA_FLAGS -czf "$work/data.tar.gz" -T /dev/null
	fi

	echo "2.0" > "$work/debian-binary"

	out="$DIST_DIR/${name}_${version}_all.ipk"
	rm -f "$out"
	# Aeusserer Container: EIN gzip-komprimierter tar-Stream mit den drei
	# Dateien (./debian-binary zuerst, dann data.tar.gz, dann control.tar.gz -
	# exakt die Reihenfolge und "./"-Pfadschreibweise aus OpenWrts eigenem
	# "ipkg-build"-Skript) - KEIN ar-Archiv.
	# shellcheck disable=SC2086
	( cd "$work" && tar $OUTER_TAR_FLAGS -cf - ./debian-binary ./data.tar.gz ./control.tar.gz ) | gzip -n > "$out"

	rm -rf "$work"
	trap - EXIT

	echo "gebaut: $out"
}

if [ "$#" -gt 0 ]; then
	for p in "$@"; do
		build_one "$p"
	done
else
	for d in "$SCRIPT_DIR"/*/; do
		d=${d%/}
		base=$(basename "$d")
		case "$base" in
			dist|feed-makefiles|tools) continue ;;
		esac
		[ -f "$d/control/control" ] && build_one "$base"
	done
fi
