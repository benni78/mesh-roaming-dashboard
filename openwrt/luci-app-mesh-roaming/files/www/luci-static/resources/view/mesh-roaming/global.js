'use strict';
'require form';
'require view';

// Grundeinstellungen des Mesh-Roaming-Dashboards (UCI-Sektion
// "config global 'main'" in /etc/config/mesh-roaming). Nach dem Speichern
// erzeugt der Init-Dienst beim naechsten (Re-)Start/Reload daraus die
// config.json fuer mesh_roaming_pi.py - siehe
// /usr/libexec/mesh-roaming-uci2json.

return view.extend({
	render: function () {
		var m, s;

		m = new form.Map('mesh-roaming', 'Mesh Roaming Dashboard – Grundeinstellungen',
			'Diese Werte gelten fuer das gesamte Dashboard. Router und SSID-Farben ' +
			'werden auf den jeweils eigenen Seiten gepflegt. Nach dem Speichern & ' +
			'Anwenden wird der Dienst neu geladen.');

		s = m.section(form.NamedSection, 'main', 'global', 'Allgemein');
		s.addremove = false;
		s.anonymous = true;

		s.tab('general', 'Allgemein');
		s.tab('ssh', 'SSH');
		s.tab('advanced', 'Erweitert');

		var o = s.taboption('general', form.Value, 'label', 'Anzeigename',
			'Erscheint im Seitenkopf des Dashboards.');
		o.default = 'Mesh-Netzwerk';

		o = s.taboption('general', form.Value, 'bind', 'Bind-Adresse');
		o.default = '0.0.0.0';
		o.datatype = 'ipaddr';

		o = s.taboption('general', form.Value, 'port', 'Port');
		o.default = '8765';
		o.datatype = 'port';

		o = s.taboption('general', form.Value, 'interval_sec', 'Abfrage-Intervall (Sekunden)');
		o.default = '1';
		o.datatype = 'min(1)';

		o = s.taboption('general', form.DynamicList, 'ap_ifname', 'AP-Interfaces',
			'z. B. phy0-ap0, phy1-ap0 – per "ubus list | grep hostapd" auf einem ' +
			'Router gegenpruefen, falls ein anderes Namensschema verwendet wird.');

		o = s.taboption('ssh', form.Value, 'ssh_user', 'SSH-Benutzer');
		o.default = 'root';

		o = s.taboption('ssh', form.Value, 'ssh_key_path', 'SSH-Key-Pfad');
		o.default = '/etc/mesh-roaming/id_ed25519';

		o = s.taboption('ssh', form.Value, 'ssh_connect_timeout_sec', 'Connect-Timeout (s)');
		o.default = '5';
		o.datatype = 'min(1)';

		o = s.taboption('ssh', form.Value, 'ssh_command_timeout_sec', 'Kommando-Timeout (s)');
		o.default = '8';
		o.datatype = 'min(1)';

		o = s.taboption('ssh', form.Flag, 'ssh_control_master', 'SSH ControlMaster verwenden');
		o.default = '1';

		o = s.taboption('ssh', form.Value, 'ssh_control_persist', 'ControlPersist');
		o.default = '60s';

		o = s.taboption('advanced', form.Value, 'db_path', 'Pfad der SQLite-Datenbank');
		o.default = '/etc/mesh-roaming/state.db';

		o = s.taboption('advanced', form.Value, 'runtime_dir', 'Laufzeitverzeichnis');
		o.default = '/etc/mesh-roaming/run';

		o = s.taboption('advanced', form.Value, 'reachable_signal_threshold_dbm',
			'Schwelle „auch empfangbar" (dBm)');
		o.default = '-75';
		o.datatype = 'range(-100,0)';

		o = s.taboption('advanced', form.Value, 'shift_amount_min', 'Roaming-Pfeil – min. Versatz');
		o.default = '0.15';

		o = s.taboption('advanced', form.Value, 'shift_amount_max', 'Roaming-Pfeil – max. Versatz');
		o.default = '0.70';

		o = s.taboption('advanced', form.Value, 'log_max_entries', 'Max. Eintraege im Ereignis-Log');
		o.default = '200';
		o.datatype = 'min(1)';

		o = s.taboption('advanced', form.Value, 'signal_min_dbm', 'Signal-Radar – Minimum (dBm)');
		o.default = '-90';

		o = s.taboption('advanced', form.Value, 'signal_max_dbm', 'Signal-Radar – Maximum (dBm)');
		o.default = '-30';

		o = s.taboption('advanced', form.DynamicList, 'reference_ring_dbm',
			'Signal-Radar – Referenzringe (dBm)');

		o = s.taboption('advanced', form.Value, 'map_viewbox_width', 'Karte – Breite (px)');
		o.default = '900';

		o = s.taboption('advanced', form.Value, 'map_viewbox_height', 'Karte – Hoehe (px)');
		o.default = '600';

		o = s.taboption('advanced', form.Value, 'map_radius_inner', 'Karte – Radius Router (px)');
		o.default = '16';

		o = s.taboption('advanced', form.Value, 'map_radius_outer', 'Karte – Radius Aussenring (px)');
		o.default = '100';

		o = s.taboption('advanced', form.DynamicList, 'ssid_color',
			'Standard-Farbreihenfolge fuer neu entdeckte SSIDs (Hex-Farben)');

		o = s.taboption('advanced', form.Value, 'util_interval_sec',
			'Kanalauslastung – Intervall (s)');
		o.default = '10';

		o = s.taboption('advanced', form.Value, 'util_color_own', 'Kanalauslastung – Farbe eigene Nutzung');
		o.default = '#3987e5';

		o = s.taboption('advanced', form.Value, 'util_color_foreign', 'Kanalauslastung – Farbe fremde Nutzung');
		o.default = '#e66767';

		o = s.taboption('advanced', form.Value, 'util_color_rest', 'Kanalauslastung – Farbe ungenutzt');
		o.default = '#2f3d46';

		o = s.taboption('advanced', form.Value, 'mqtt_broker', 'MQTT-Broker (optional)',
			'Leer lassen, um MQTT zu deaktivieren.');

		o = s.taboption('advanced', form.Value, 'mqtt_base_topic', 'MQTT – Basis-Topic');
		o.default = 'mesh-roaming';

		o = s.taboption('advanced', form.Value, 'mqtt_publish_interval_sec', 'MQTT – Intervall (s)');
		o.default = '10';

		return m.render();
	}
});
