'use strict';
'require fs';

// Copyright Benjamin Johann (mesh-roaming-dashboard)
// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
//
// Gemeinsame Helfer der LuCI-Seiten von luci-app-mesh-roaming (#9):
// Titel mit der tatsaechlich installierten Paketversion und Hinweise, wenn
// die Seite aus dem Browser-Cache stammt oder der Dienst nach einem Upgrade
// noch mit der alten Version laeuft.

var FILE_VERSION = '2.0'; // MESH_ROAMING_VERSION
// Vollstaendige Paketversion (z. B. "1.4-r1"), beim Bauen des Pakets von
// build-ipk.sh eingesetzt. Weicht sie von der installierten ab, stammt
// diese Datei (und damit die ganze Seite) aus dem Browser-Cache.
var BUILD_VERSION = '@PKG_VERSION@';

function upstream(v) {
	return v ? String(v).replace(/-r[0-9]+$/, '') : v;
}

return L.Class.extend({
	// -> {packages: {...}, service: "1.4" | null} oder null
	loadVersions: function () {
		return fs.exec_direct('/usr/libexec/mesh-roaming-version', [], 'json')
			.catch(function () { return null; });
	},

	title: function (info, suffix) {
		var pkgs = (info && info.packages) || {};
		var v = pkgs['luci-app-mesh-roaming'] || pkgs['mesh-roaming'] || FILE_VERSION;
		return 'Mesh Roaming Dashboard ' + v + ' – ' + suffix;
	},

	// Hinweiskaesten (leeres Array, wenn alles passt)
	hints: function (info) {
		var out = [];
		if (!info || !info.packages)
			return out;
		var luciPkg = info.packages['luci-app-mesh-roaming'];
		var svcPkg = info.packages['mesh-roaming'];

		if (luciPkg && BUILD_VERSION.charAt(0) !== '@' && BUILD_VERSION !== luciPkg) {
			out.push(E('div', { 'class': 'alert-message warning' }, [
				E('strong', {}, 'Veraltete Seite: '),
				'Diese Seite stammt noch aus Version ' + BUILD_VERSION +
				' (Browser-Cache), installiert ist ' + luciPkg + '. ' +
				'Bitte die Seite neu laden (Strg+F5) bzw. den Browser-Cache leeren.'
			]));
		}

		// Laufender Dienst mit anderer Version - oder ohne Versionsangabe
		// (vor 1.4 gab /api/status noch keine Version zurueck).
		var running = info.service || (info.service_running ? 'vor 1.4' : null);
		if (svcPkg && running && running !== upstream(svcPkg)) {
			out.push(E('div', { 'class': 'alert-message warning' }, [
				E('strong', {}, 'Dienst nicht neu gestartet: '),
				'Installiert ist mesh-roaming ' + svcPkg + ', der Dienst laeuft aber noch mit Version ' +
				running + '. Neu starten mit „/etc/init.d/mesh-roaming restart“ ' +
				'oder unter System → Systemstart.'
			]));
		}
		return out;
	},

	// Hinweise oben in die gerenderte Seite einfuegen
	withHints: function (info, node) {
		var h = this.hints(info);
		for (var i = h.length - 1; i >= 0; i--)
			node.insertBefore(h[i], node.firstChild);
		return node;
	}
});
