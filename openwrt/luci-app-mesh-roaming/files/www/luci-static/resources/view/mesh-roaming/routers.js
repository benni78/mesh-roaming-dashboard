'use strict';
'require form';
'require view';

// Router-Liste des Mesh-Roaming-Dashboards (UCI-Typ "router" in
// /etc/config/mesh-roaming). Jeder Eintrag entspricht einem Router auf der
// Karte. "id" ist die interne, stabile Kennung (frei waehlbar, z. B.
// "router-wohnzimmer") - "name" ist die Ueberschrift auf der Karte, "room"
// nur ein kleiner Untertitel darunter.

return view.extend({
	render: function () {
		var m, s, o;

		m = new form.Map('mesh-roaming', 'Mesh Roaming Dashboard – Router',
			'Ein Eintrag je Router. Nach dem Speichern & Anwenden wird der Dienst ' +
			'neu geladen.');

		s = m.section(form.TypedSection, 'router', '');
		s.addremove = true;
		s.anonymous = true;
		s.sortable = true;

		o = s.option(form.Value, 'id', 'ID',
			'Frei waehlbar, muss eindeutig sein (z. B. "router-wohnzimmer"). ' +
			'Nach dem Anlegen nicht mehr aendern.');
		o.rmempty = false;
		o.optional = false;

		o = s.option(form.Value, 'name', 'Name',
			'Ueberschrift auf der Karte/in allen Listen.');
		o.rmempty = false;
		o.optional = false;

		o = s.option(form.Value, 'room', 'Raum',
			'Nur als kleiner Untertitel unter dem Namen angezeigt.');

		o = s.option(form.Value, 'ip', 'IP-Adresse',
			'Client-LAN-IP, ueber die dieser Router per SSH erreicht wird.');
		o.datatype = 'ipaddr';
		o.rmempty = false;
		o.optional = false;

		o = s.option(form.Value, 'map_x', 'Karte – X-Position');
		o.datatype = 'uinteger';
		o.default = '0';
		o.placeholder = '0–900';

		o = s.option(form.Value, 'map_y', 'Karte – Y-Position');
		o.datatype = 'uinteger';
		o.default = '0';
		o.placeholder = '0–600';

		o = s.option(form.DynamicList, 'mgmt_ip', 'Mesh-Management-IPs',
			'Nur nötig, wenn sich die Router per usteer/batman gegenseitig sehen ' +
			'und das auf der Karte sichtbar sein soll – sonst leer lassen.');

		o = s.option(form.Flag, 'local', 'Dieser Router',
			'Markiert den Router, auf dem dieser Dienst selbst laeuft ' +
			'(nur bei der router-gehosteten Installation relevant).');
		o.default = '0';

		o = s.option(form.Flag, 'disabled', 'Deaktiviert',
			'Router vorübergehend aus der Karte ausblenden, ohne den Eintrag zu löschen.');
		o.default = '0';

		return m.render();
	}
});
