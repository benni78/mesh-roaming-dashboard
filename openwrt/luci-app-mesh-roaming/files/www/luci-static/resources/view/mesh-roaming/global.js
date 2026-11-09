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
		s.tab('privacy', 'Datenschutz');
		s.tab('ssh', 'SSH');
		s.tab('mqtt', 'MQTT');
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

		o = s.taboption('privacy', form.Value, 'retention_days',
			'Aufbewahrungsfrist (Tage)',
			'Geraetebezogene Daten (MAC-Adresse, Name, IP, Nickname, Roaming-' +
			'Log-Eintraege) werden spaetestens so viele Tage nach der letzten ' +
			'Beobachtung des jeweiligen Geraets automatisch geloescht – nicht ' +
			'nur aus der Anzeige, sondern aus der Datenbank (Speicherbegrenzung, ' +
			'Art. 5 Abs. 1 lit. e DSGVO). Siehe README.md, Abschnitt ' +
			'"Datenschutz-Hinweis (DSGVO)".');
		o.default = '7';
		o.datatype = 'min(0)';

		o = s.taboption('privacy', form.Flag, 'anonymous_stats_enabled',
			'Anonyme Langzeit-Statistik fuehren',
			'Fuehrt zusaetzlich eine stuendliche Zusammenfassung ohne MAC-' +
			'Adresse (Ereignisanzahl + Ø-Signalstaerke je Router/Band) fort – ' +
			'kein personenbezogenes Datum, darf auch nach Ablauf der ' +
			'Aufbewahrungsfrist oben unbegrenzt fuer Trend-Analysen aufbewahrt ' +
			'werden.');
		o.default = '1';

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

		o = s.taboption('mqtt', form.Value, 'mqtt_broker', 'Broker (optional)',
			'Hostname oder IP-Adresse. Leer lassen, um MQTT zu deaktivieren. ' +
			'Benoetigt mosquitto_pub (apk add mosquitto-client-ssl).');

		o = s.taboption('mqtt', form.Value, 'mqtt_port', 'Port',
			'Leer = Standardport (1883, mit TLS 8883).');
		o.datatype = 'port';
		o.placeholder = '1883 / 8883';
		o.depends({ mqtt_broker: /.+/ });

		o = s.taboption('mqtt', form.Value, 'mqtt_base_topic', 'Basis-Topic');
		o.default = 'mesh-roaming';
		o.depends({ mqtt_broker: /.+/ });

		o = s.taboption('mqtt', form.Value, 'mqtt_publish_interval_sec', 'Intervall (s)');
		o.default = '10';
		o.datatype = 'min(1)';
		o.depends({ mqtt_broker: /.+/ });

		o = s.taboption('mqtt', form.Value, 'mqtt_username', 'Benutzername (optional)',
			'Leer lassen fuer eine anonyme Verbindung.');
		o.depends({ mqtt_broker: /.+/ });

		o = s.taboption('mqtt', form.Value, 'mqtt_password', 'Passwort (optional)',
			'Wird im Klartext in /etc/config/mesh-roaming gespeichert und ohne ' +
			'TLS unverschluesselt uebertragen.');
		o.password = true;
		o.depends({ mqtt_broker: /.+/, mqtt_username: /.+/ });

		o = s.taboption('mqtt', form.Flag, 'mqtt_tls', 'TLS verwenden');
		o.default = '0';
		o.depends({ mqtt_broker: /.+/ });

		o = s.taboption('mqtt', form.Value, 'mqtt_tls_cafile', 'CA-Zertifikat (optional)',
			'Pfad zu einer CA-Datei (PEM) fuer selbst signierte Broker-Zertifikate. ' +
			'Leer = System-Zertifikate aus /etc/ssl/certs (Paket ca-certificates).');
		o.placeholder = '/etc/mesh-roaming/mqtt-ca.crt';
		o.depends({ mqtt_broker: /.+/, mqtt_tls: '1' });

		o = s.taboption('mqtt', form.Flag, 'mqtt_tls_insecure', 'Hostnamen nicht pruefen',
			'Nur zum Testen: akzeptiert ein Zertifikat, auch wenn der Hostname ' +
			'nicht passt.');
		o.default = '0';
		o.depends({ mqtt_broker: /.+/, mqtt_tls: '1' });

		return m.render();
	}
});
