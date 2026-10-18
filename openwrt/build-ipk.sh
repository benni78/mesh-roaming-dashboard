#!/bin/sh
# Baut .ipk-Pakete aus openwrt/<paketname>/{control,files}/ - ohne OpenWrt-SDK,
# nur mit ar/tar/gzip (reicht fuer reine Skript-Pakete, Architecture: all).
#
# Ein .ipk ist ein ar-Archiv aus drei Dateien:
#   debian-binary   - enthaelt nur "2.0"
#   control.tar.gz  - control, ggf. conffiles/postinst/prerm (Paket-Metadaten)
#   data.tar.gz     - der zu installierende Dateibaum (files/ als Wurzel "/")
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
	tar -C "$src/control" --owner=0 --group=0 --numeric-owner \
		-czf "$work/control.tar.gz" $ctrl_files

	# data.tar.gz: der komplette Zielbaum, falls vorhanden (ein reines
	# Metapaket ohne eigene Dateien ist zulaessig und hat kein files/)
	if [ -d "$src/files" ]; then
		tar -C "$src/files" --owner=0 --group=0 --numeric-owner \
			-czf "$work/data.tar.gz" .
	else
		tar --owner=0 --group=0 --numeric-owner -czf "$work/data.tar.gz" -T /dev/null
	fi

	echo "2.0" > "$work/debian-binary"

	out="$DIST_DIR/${name}_${version}_all.ipk"
	rm -f "$out"
	( cd "$work" && ar -r "$out" debian-binary control.tar.gz data.tar.gz >/dev/null )

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
			dist|feed-makefiles) continue ;;
		esac
		[ -f "$d/control/control" ] && build_one "$base"
	done
fi
