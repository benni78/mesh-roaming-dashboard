'use strict';
'require form';
'require view';

// Copyright Benni (mesh-roaming-dashboard)
// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
var VERSION = '1.2'; // MESH_ROAMING_VERSION

// Feste Farben je SSID-Name (UCI-Typ "ssid_color" in
// /etc/config/mesh-roaming). Optional - jede SSID, die hier nicht
// eingetragen ist, bekommt automatisch eine Farbe aus der
// Standard-Farbreihenfolge (siehe Grundeinstellungen) nach
// Entdeckungsreihenfolge zugewiesen.

return view.extend({
	render: function () {
		var m, s, o;

		m = new form.Map('mesh-roaming', 'Mesh Roaming Dashboard ' + VERSION + ' – SSID-Farben',
			'Optional: feste Farbe je SSID-Name, statt automatischer Zuweisung ' +
			'nach Entdeckungsreihenfolge.');

		s = m.section(form.TypedSection, 'ssid_color', '');
		s.addremove = true;
		s.anonymous = true;
		s.sortable = true;

		o = s.option(form.Value, 'ssid', 'SSID-Name');
		o.rmempty = false;
		o.optional = false;

		o = s.option(form.Value, 'color', 'Farbe (Hex)');
		o.rmempty = false;
		o.optional = false;
		o.placeholder = '#5b8dd6';
		o.datatype = 'and(minlength(4),maxlength(7))';

		return m.render();
	}
});
