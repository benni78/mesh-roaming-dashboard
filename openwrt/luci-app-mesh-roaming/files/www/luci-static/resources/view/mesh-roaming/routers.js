'use strict';
'require form';
'require fs';
'require ui';
'require uci';
'require view';

// Router-Liste des Mesh-Roaming-Dashboards (UCI-Typ "router" in
// /etc/config/mesh-roaming). Aufbau wie die Instanz-Liste unter
// LuCI -> VPN -> OpenVPN: eine Tabellenzeile je Router, "Dieser Router" und
// "Deaktiviert" direkt in der Liste umschaltbar, alles Weitere ueber
// "Bearbeiten" im Dialog. "id" ist die interne, stabile Kennung - "name"
// ist die Ueberschrift auf der Karte, "room" nur ein kleiner Untertitel.

var CONFIG = 'mesh-roaming';

// Erreichbarkeit je Router-ID aus dem laufenden Dienst (GET /api/status,
// ueber /usr/libexec/mesh-roaming-status). null = Dienst nicht erreichbar.
function loadStatus() {
	return fs.exec_direct('/usr/libexec/mesh-roaming-status', [], 'json')
		.then(function (res) { return (res && res.routerStatus) || {}; })
		.catch(function () { return null; });
}

// "Gartenhaus Süd" -> "router-gartenhaus-sued", eindeutig gegenueber den
// vorhandenen IDs.
function makeRouterId(name) {
	var base = 'router-' + (name.toLowerCase()
		.replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
		.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'neu');
	var used = {};
	uci.sections(CONFIG, 'router').forEach(function (s) { if (s.id) used[s.id] = true; });
	var id = base;
	for (var i = 2; used[id]; i++)
		id = base + '-' + i;
	return id;
}

return view.extend({
	load: function () {
		return Promise.all([
			uci.load(CONFIG),
			loadStatus()
		]);
	},

	render: function (data) {
		var routerStatus = data[1];
		var m, s, o;

		var mapWidth = +uci.get(CONFIG, 'main', 'map_viewbox_width') || 900;
		var mapHeight = +uci.get(CONFIG, 'main', 'map_viewbox_height') || 600;
		var mapHint = 'Karte: %d × %d px · horizontal 0–%d, vertikal 0–%d (0/0 = oben links). ' +
			'Die Kartengroesse wird unter Grundeinstellungen → Erweitert festgelegt.';
		mapHint = mapHint.format(mapWidth, mapHeight, mapWidth, mapHeight);

		// Bereits gespeicherte Router: deren ID ist im Dialog nur noch lesbar.
		var savedSections = {};
		uci.sections(CONFIG, 'router').forEach(function (s) { savedSections[s['.name']] = true; });

		m = new form.Map(CONFIG, 'Mesh Roaming Dashboard – Router',
			'Ein Eintrag (Instanz) je Router. „Dieser Router“ und „Deaktiviert“ lassen ' +
			'sich direkt in der Liste umschalten, alle weiteren Einstellungen ueber ' +
			'„Bearbeiten“. Nach dem Speichern & Anwenden wird der Dienst neu geladen.');

		s = m.section(form.GridSection, 'router');
		s.addremove = true;
		s.anonymous = true;
		s.sortable = true;
		s.nodescriptions = true;
		s.modaltitle = function (section_id) {
			var name = uci.get(CONFIG, section_id, 'name');
			return name ? 'Router bearbeiten: ' + name : 'Router bearbeiten';
		};

		// Unter der Liste: Namensfeld + "Hinzufuegen" wie bei OpenVPN. Legt
		// einen anonymen Eintrag an, setzt Name und eine daraus abgeleitete ID
		// und oeffnet direkt den Bearbeiten-Dialog.
		s.renderSectionAdd = function (extra_class) {
			var readonly = this.map.readonly || null;
			var nameEl = E('input', {
				'type': 'text',
				'class': 'cbi-section-create-name',
				'placeholder': 'Name des neuen Routers, z. B. Gartenhaus',
				'style': 'min-width:22em',
				'disabled': readonly
			});
			var addBtn = E('button', {
				'class': 'cbi-button cbi-button-add',
				'title': 'Hinzufuegen',
				'disabled': true,
				'click': ui.createHandlerFn(this, function (ev) {
					var name = nameEl.value.trim();
					if (name === '')
						return;
					nameEl.value = '';
					addBtn.disabled = true;
					return this.handleAdd(ev, name);
				})
			}, ['Hinzufuegen']);
			nameEl.addEventListener('input', function () {
				addBtn.disabled = (readonly || nameEl.value.trim() === '') ? true : null;
			});
			nameEl.addEventListener('keydown', function (ev) {
				if (ev.key === 'Enter' && !addBtn.disabled)
					addBtn.click();
			});

			var createEl = E('div', { 'class': 'cbi-section-create' }, [ E('div', {}, nameEl), addBtn ]);
			if (extra_class != null)
				createEl.classList.add(extra_class);
			return createEl;
		};

		// Die eigentliche Logik (Eintrag anlegen, Dialog oeffnen, bei
		// "Abbrechen" wieder entfernen) bleibt die von GridSection - hier wird
		// nur der frisch angelegte Eintrag vorbelegt.
		s.handleAdd = function (ev, name) {
			var data = this.map.data;
			var origAdd = data.add;
			var id = makeRouterId(name || '');
			data.add = function (conf, type) {
				var sid = origAdd.call(data, conf, type);
				data.set(conf, sid, 'name', name);
				data.set(conf, sid, 'id', id);
				return sid;
			};
			try {
				return form.GridSection.prototype.handleAdd.call(this, ev, null);
			}
			finally {
				data.add = origAdd;
			}
		};

		// --- Spalten der Liste (und Felder im Dialog) ---

		o = s.option(form.Value, 'name', 'Name',
			'Ueberschrift auf der Karte/in allen Listen.');
		o.rmempty = false;
		o.textvalue = function (section_id) {
			return E('strong', {}, this.cfgvalue(section_id) || uci.get(CONFIG, section_id, 'id') || '?');
		};

		o = s.option(form.Value, 'room', 'Raum',
			'Nur als kleiner Untertitel unter dem Namen angezeigt.');

		o = s.option(form.Value, 'ip', 'IP-Adresse',
			'Client-LAN-IP, ueber die dieser Router per SSH erreicht wird.');
		o.datatype = 'ipaddr';
		o.rmempty = false;

		o = s.option(form.Flag, 'local', 'Dieser Router',
			'Markiert den Router, auf dem dieser Dienst selbst laeuft ' +
			'(nur bei der router-gehosteten Installation relevant). ' +
			'Kann nur bei einem Router gesetzt sein.');
		o.editable = true;
		o.default = '0';
		// Exklusiv: Ankreuzen entfernt den Haken bei allen anderen Routern -
		// in der Liste sofort sichtbar, beim Speichern zusaetzlich in UCI.
		o.onchange = function (ev, section_id, value) {
			if (value !== '1')
				return;
			this.section.cfgsections().forEach(L.bind(function (sid) {
				var el = (sid !== section_id) ? this.getUIElement(sid) : null;
				if (el)
					el.setValue('0');
			}, this));
		};
		o.write = function (section_id, value) {
			if (value === '1') {
				uci.sections(CONFIG, 'router').forEach(function (r) {
					if (r['.name'] !== section_id)
						uci.unset(CONFIG, r['.name'], 'local');
				});
			}
			return form.Flag.prototype.write.apply(this, arguments);
		};

		o = s.option(form.Flag, 'disabled', 'Deaktiviert',
			'Router voruebergehend aus der Karte ausblenden, ohne den Eintrag zu loeschen.');
		o.editable = true;
		o.default = '0';

		o = s.option(form.DummyValue, '_status', 'Status');
		o.modalonly = false;
		o.textvalue = function (section_id) {
			var rid = uci.get(CONFIG, section_id, 'id');
			var color, text;
			if (uci.get(CONFIG, section_id, 'disabled') === '1') {
				color = '#9aa0a6'; text = 'deaktiviert';
			}
			else if (routerStatus === null) {
				color = '#9aa0a6'; text = 'Dienst laeuft nicht';
			}
			else if (!rid || !(rid in routerStatus)) {
				color = '#9aa0a6'; text = 'noch nicht uebernommen';
			}
			else if (routerStatus[rid] === 'ok') {
				color = '#3aa655'; text = 'erreichbar';
			}
			else {
				color = '#d9534f'; text = 'nicht erreichbar';
			}
			return E('span', { 'title': (routerStatus && rid && routerStatus[rid] !== 'ok') ? routerStatus[rid] || '' : '' }, [
				E('span', { 'style': 'display:inline-block;width:.7em;height:.7em;border-radius:50%;margin-right:.4em;background:' + color }),
				text
			]);
		};

		// --- Nur im Bearbeiten-Dialog ---

		o = s.option(form.Value, 'id', 'ID',
			'Interne, eindeutige Kennung (z. B. "router-wohnzimmer"). Wird beim ' +
			'Anlegen aus dem Namen vorgeschlagen und ist danach nicht mehr aenderbar.');
		o.modalonly = true;
		o.rmempty = false;
		o.datatype = 'maxlength(64)';
		o.renderWidget = function (section_id) {
			this.readonly = savedSections[section_id] ? true : false;
			return form.Value.prototype.renderWidget.apply(this, arguments);
		};
		o.validate = function (section_id, value) {
			if (!/^[A-Za-z0-9_.-]+$/.test(value || ''))
				return 'Nur Buchstaben, Ziffern, "-", "_" und "." erlaubt.';
			var dup = uci.sections(CONFIG, 'router').some(function (r) {
				return r['.name'] !== section_id && r.id === value;
			});
			return dup ? 'Diese ID ist bereits vergeben.' : true;
		};

		o = s.option(form.Value, 'map_x', 'Position horizontal (px)', mapHint);
		o.modalonly = true;
		o.datatype = 'range(0,%d)'.format(mapWidth);
		o.default = '0';
		o.placeholder = '0–%d'.format(mapWidth);

		o = s.option(form.Value, 'map_y', 'Position vertikal (px)', mapHint);
		o.modalonly = true;
		o.datatype = 'range(0,%d)'.format(mapHeight);
		o.default = '0';
		o.placeholder = '0–%d'.format(mapHeight);

		o = s.option(form.DynamicList, 'mgmt_ip', 'Mesh-Management-IPs',
			'Fuer die Anzeige „zwischen Stationen“ (Daten von usteer): IP(s), unter ' +
			'der andere Router diesen Router im usteer-Netz sehen. Leer lassen, wenn ' +
			'das die IP-Adresse oben ist – die wird automatisch verwendet. Ablesen auf ' +
			'einem anderen Router mit „ubus call usteer remote_info“ (Teil vor dem „#“).');
		o.modalonly = true;
		o.datatype = 'ipaddr';

		return m.render();
	}
});
