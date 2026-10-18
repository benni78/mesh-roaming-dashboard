#!/bin/sh
# Baut .ipk-Pakete aus openwrt/<paketname>/{control,files}/ - ohne OpenWrt-SDK,
# nur mit ar/tar/gzip (reicht fuer reine Skript-Pakete, Architecture: all).
#
# WICHTIG: Dieses Skript auf einem gewoehnlichen Linux-Rechner ausfuehren
# (z. B. dem eigenen PC/Laptop, einer VM, WSL) - NICHT auf dem OpenWrt-
# Router selbst! Der auf OpenWrt/BusyBox mitgelieferte "ar"-Befehl kann
# ueblicherweise nur Archive LESEN/entpacken, nicht neu ERSTELLEN - das
# Erstellen eines .ipk schlaegt dort fehl (bzw. dieses Skript bricht weiter
# unten mit einer klaren Fehlermeldung ab, statt mitten im Bauen zu
# scheitern). Die fertigen .ipk-Dateien danach einfach per scp auf den
# Router kopieren (siehe docs/deployment-openwrt.md, Schritt 2).
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

# GNU tar unterstuetzt --owner/--group/--numeric-owner (fuer root:root-
# Eigentuemer in den Archiven, unabhaengig vom Build-Nutzer). BusyBox tar
# (auf OpenWrt) kennt diese Optionen nicht - dort einfach weglassen, die
# Dateien gehoeren beim Bauen als root sowieso schon root:root.
TAR_OWNER_FLAGS=""
if tar --version 2>/dev/null | grep -qi "GNU tar"; then
	TAR_OWNER_FLAGS="--owner=0 --group=0 --numeric-owner"
fi

# ar-Verfuegbarkeit pruefen: BusyBox liefert auf vielen OpenWrt-Systemen nur
# eine LESE-faehige ar-Variante (kann Archive entpacken/auflisten, aber
# keine neuen erstellen) - genau das brauchen wir hier aber zwingend.
# Lieber jetzt mit einer klaren Meldung abbrechen als mitten im Bauen mit
# einem kryptischen Fehler.
if ! command -v ar >/dev/null 2>&1; then
	echo "Fehler: 'ar' ist auf diesem System nicht vorhanden." >&2
	echo "Dieses Skript bitte auf einem gewoehnlichen Linux-Rechner (nicht" >&2
	echo "auf dem OpenWrt-Router) ausfuehren und die fertigen .ipk-Dateien" >&2
	echo "danach per scp auf den Router kopieren." >&2
	exit 1
fi
AR_TEST_DIR=$(mktemp -d)
echo test > "$AR_TEST_DIR/t"
if ! ( cd "$AR_TEST_DIR" && ar rc test.ar t >/dev/null 2>&1 && ar t test.ar 2>/dev/null | grep -q '^t$' ); then
	rm -rf "$AR_TEST_DIR"
	echo "Fehler: Das vorhandene 'ar' auf diesem System kann offenbar keine" >&2
	echo "Archive ERSTELLEN (nur lesen/entpacken) - typisch fuer BusyBox auf" >&2
	echo "OpenWrt-Routern. .ipk-Dateien lassen sich damit nicht bauen." >&2
	echo >&2
	echo "Bitte dieses Skript auf einem gewoehnlichen Linux-Rechner (eigener" >&2
	echo "PC/Laptop, VM, WSL) mit vollwertigem binutils-ar ausfuehren - NICHT" >&2
	echo "auf dem Router selbst - und danach nur die beiden fertigen" >&2
	echo "openwrt/dist/*.ipk-Dateien per scp auf den Router kopieren:" >&2
	echo "  scp openwrt/dist/*.ipk root@<router-ip>:/tmp/" >&2
	echo "  ssh root@<router-ip> opkg install /tmp/<paket>.ipk" >&2
	exit 1
fi
rm -rf "$AR_TEST_DIR"

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
	tar -C "$src/control" $TAR_OWNER_FLAGS \
		-czf "$work/control.tar.gz" $ctrl_files

	# data.tar.gz: der komplette Zielbaum, falls vorhanden (ein reines
	# Metapaket ohne eigene Dateien ist zulaessig und hat kein files/)
	if [ -d "$src/files" ]; then
		# shellcheck disable=SC2086
		tar -C "$src/files" $TAR_OWNER_FLAGS \
			-czf "$work/data.tar.gz" .
	else
		# shellcheck disable=SC2086
		tar $TAR_OWNER_FLAGS -czf "$work/data.tar.gz" -T /dev/null
	fi

	echo "2.0" > "$work/debian-binary"

	out="$DIST_DIR/${name}_${version}_all.ipk"
	rm -f "$out"
	( cd "$work" && ar rc "$out" debian-binary control.tar.gz data.tar.gz >/dev/null )

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
