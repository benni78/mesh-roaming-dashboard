#!/bin/sh
# Version 2.1 (MESH_ROAMING_VERSION) - Teil von mesh-roaming-dashboard
# Copyright Benjamin Johann (mesh-roaming-dashboard)
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#
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
# Jedes Paket bekommt LICENSE und THIRD-PARTY-NOTICES.md des Projekts unter
# /usr/share/licenses/<paket>/ (die Lizenz verlangt, dass jede weitergegebene
# Kopie die Lizenzbedingungen enthaelt). Vor dem Bauen wird geprueft, dass
# alle mit MESH_ROAMING_VERSION markierten Versionsangaben (Paketdateien,
# src/ und systemd/ der Raspberry-Pi-Variante) zur Version in control/control
# passen und die Kopien unter src/ identisch sind.
#
# Getestet mit opkg auf OpenWrt 23.05.6 (x86/64): Erstinstallation,
# Upgrade, Neuinstallation und Deinstallation.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(dirname -- "$SCRIPT_DIR")
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

	# Versionsangaben in den Programmen muessen zur Paketversion passen
	upstream=${version%-r*}
	bad=$(grep -rn "MESH_ROAMING_VERSION" "$src/files" "$REPO_DIR/src" "$REPO_DIR/systemd" 2>/dev/null | grep -v "[^0-9.]$upstream[^0-9.]" || true)
	if [ -n "$bad" ]; then
		echo "Fehler: Versionsangabe passt nicht zu $version:" >&2
		echo "$bad" >&2
		exit 1
	fi
	for f in mesh_roaming_pi.py mesh-lageplan-live.html; do
		copy="$src/files/usr/share/mesh-roaming/$f"
		if [ -f "$copy" ] && [ -f "$REPO_DIR/src/$f" ] && ! cmp -s "$copy" "$REPO_DIR/src/$f"; then
			echo "Fehler: $copy unterscheidet sich von src/$f" >&2
			exit 1
		fi
	done

	work=$(mktemp -d)
	trap 'rm -rf "$work"' EXIT

	# Dateirechte NICHT aus dem Quellbaum uebernehmen, sondern in einer
	# Arbeitskopie explizit setzen: Geht der Quellbaum ueber Windows, ein
	# ZIP oder scp ohne -p, gehen die +x-Bits verloren - dann landen
	# Init-Skript und postinst mit 0644 im Paket und "/etc/init.d/<paket>
	# enable" scheitert auf dem Router mit "Permission denied".
	# (Auf NTFS unter Git Bash/MSYS ist chmod wirkungslos - dort lieber in
	# einer Linux-Umgebung, z. B. der Test-VM, bauen.)
	mkdir -p "$work/control" "$work/files"
	cp -R "$src/control/." "$work/control/"
	[ -d "$src/files" ] && cp -R "$src/files/." "$work/files/"
	mkdir -p "$work/files/usr/share/licenses/$name"
	for f in LICENSE THIRD-PARTY-NOTICES.md; do
		[ -f "$REPO_DIR/$f" ] || { echo "Fehler: $REPO_DIR/$f fehlt" >&2; exit 1; }
		cp "$REPO_DIR/$f" "$work/files/usr/share/licenses/$name/"
	done
	# Vollstaendige Paketversion in die LuCI-Dateien eintragen (Erkennung
	# einer Seite aus dem Browser-Cache, s. luci-app-mesh-roaming common.js)
	grep -rl "@PKG_VERSION@" "$work/files" 2>/dev/null | while read -r f; do
		sed -i "s/@PKG_VERSION@/$version/g" "$f"
	done
	# Python-Bytecode (z. B. von einem lokalen py_compile) nicht mitpacken
	find "$work/files" -type d -name __pycache__ -prune -exec rm -rf {} +
	find "$work/control" "$work/files" -type d -exec chmod 0755 {} +
	find "$work/control" "$work/files" -type f -exec chmod 0644 {} +
	for f in preinst postinst prerm postrm; do
		[ -f "$work/control/$f" ] && chmod 0755 "$work/control/$f"
	done
	for d in etc/init.d etc/uci-defaults usr/bin usr/sbin usr/libexec; do
		[ -d "$work/files/$d" ] && find "$work/files/$d" -type f -exec chmod 0755 {} +
	done

	# control.tar.gz: nur die Dateien, die tatsaechlich existieren
	ctrl_files=""
	for f in control conffiles postinst preinst prerm postrm; do
		[ -f "$work/control/$f" ] && ctrl_files="$ctrl_files $f"
	done
	# shellcheck disable=SC2086
	tar -C "$work/control" $TAR_EXTRA_FLAGS \
		-czf "$work/control.tar.gz" $ctrl_files

	# data.tar.gz: der komplette Zielbaum, falls vorhanden (ein reines
	# Metapaket ohne eigene Dateien ist zulaessig und hat kein files/)
	if [ -d "$src/files" ]; then
		# shellcheck disable=SC2086
		tar -C "$work/files" $TAR_EXTRA_FLAGS \
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
