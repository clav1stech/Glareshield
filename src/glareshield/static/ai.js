// AI Bridge views: live flight context, SimBrief plan, IVAO network, export and variable catalogue.
const AI_PAGES = ['Vol en cours', 'Plan de vol', 'Réseau IVAO', 'Export IA', 'Variables IA'];
const STATUS_LABELS = {
  observed: 'Observée',
  simulated: 'Simulée',
  stale: 'Périmée',
  unavailable: 'Indisponible',
  derived: 'Calculée',
};
const VERIFICATION_LABELS = {
  msfs_sdk: 'SDK MSFS',
  configured_unverified: 'Non vérifiée',
  validated_locally: 'Validée localement',
};
const GROUP_LABELS = {
  aircraft: 'Appareil',
  position: 'Position',
  speed: 'Vitesses',
  attitude: 'Cap et route',
  configuration: 'Configuration',
  engines: 'Moteurs',
  weights: 'Masses et carburant',
  environment: 'Environnement',
  time: 'Heure',
  fenix: 'Variables Fenix configurées',
};
let ai = { status: null, context: null, settings: null, variables: null, level: 'auto', preview: null, network: null, lookup: null, plan: null };
let notesDraft = null;
const LEVELS = {
  auto: ['Automatique', 'Briefing au sol, point en vol une fois en l’air.'],
  briefing: ['Briefing', 'À envoyer une fois, au sol : plan complet (route, SID, STAR, points de route, carburant, masses, METAR, horaires), état de l’avion et, si IVAO est activé, contrôleurs, ATIS, METAR et TAF des aérodromes suivis.'],
  flight: ['Point en vol', 'À envoyer aussi souvent que nécessaire : trajectoire, configuration, autopilote, prochains points, distance restante, carburant comparé au plan et, si IVAO est activé, contrôleurs proches, ATIS et météo de destination. Complète le briefing déjà transmis.'],
  full: ['Complet', 'Diagnostic : toutes les variables avec leur source et leur vérification, le plan intégral et les données IVAO avec leur provenance.'],
};
const ENTRY_LEVELS = { essential: 'briefing et vol', detailed: 'complet seulement' };

function statusBadge(status) {
  return badge(STATUS_LABELS[status] || status, status);
}
function formatValue(field, key = null) {
  if (field.value === null || field.value === undefined) return '—';
  if (key === 'zulu_time' && typeof field.value === 'number')
    return [3600, 60, 1].map(d => String(Math.floor(field.value / d) % (d === 3600 ? 24 : 60)).padStart(2, '0')).join(':') + 'Z';
  if (typeof field.value === 'boolean') return field.value ? 'Oui' : 'Non';
  if (typeof field.value === 'number') return field.value.toLocaleString('fr-FR', { maximumFractionDigits: 4 });
  return String(field.value);
}
function ageText(field) {
  if (field.age_s === undefined) return field.reason || '';
  return field.age_s < 1 ? 'à l’instant' : 'il y a ' + Math.round(field.age_s) + ' s';
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    let area = el('textarea', null, { value: text, style: 'position:fixed;opacity:0' });
    document.body.append(area);
    area.select();
    let ok = document.execCommand('copy');
    area.remove();
    if (!ok) throw Error('Copie refusée par le navigateur : sélectionner le texte de l’aperçu.');
  }
}
async function copyForChat(level = ai.level) {
  let result = await api('ai/chat?level=' + level);
  await copyText(result.text);
  let simulated = result.data_origin !== 'simconnect';
  message(LEVELS[result.level][0] + ' copié (' + result.chars.toLocaleString('fr-FR') + ' caractères)' + (simulated ? ' — données simulées.' : '.'));
}
async function loadAI(full = false) {
  ai.status = await api('ai/status');
  if (['Initialisation', 'Vol'].includes(tab)) {
    let previous = ai.session, next = await api('ai/session');
    // An older poll must not replace the result of a gesture completed meanwhile.
    if (ai.session === previous) ai.session = next;
  }
  if (tab === 'Vol en cours') ai.context = await api('ai/context?level=full');
  if (full || !ai.settings) ai.settings = await api('ai/settings');
  if (tab === 'Initialisation') ai.plan = await api('ai/plan');
  if (tab === 'Variables IA' && (full || !ai.variables || !isEditing())) ai.variables = await api('ai/variables');
  if (tab === 'Export IA' && !isEditing()) ai.preview = await api('ai/context?level=' + ai.level);
  if (tab === 'Réseau IVAO' && (full || !ai.network || !isEditing())) ai.network = await api('ai/ivao');
}
REFRESH_HOOKS.push(async () => {
  await loadAI();
  if (typeof updatePreparationFoot === 'function') updatePreparationFoot();
});
async function reloadAI() {
  await loadAI(true);
  render();
}

function modeBanner(view) {
  let s = ai.status;
  if (!s) return;
  if (s.settings_error)
    view.append(el('div', 'local/ai-bridge.yaml est invalide (' + s.settings_error + ') : module désactivé jusqu’au prochain enregistrement des réglages.', { className: 'banner danger' }));
  if (s.mode === 'scenario') {
    let box = el('div', null, { className: 'banner sim' }),
      text = el('div', null),
      row = el('div', null, { className: 'row' });
    text.append(el('strong', 'Mode démonstration. '), 'Données fictives produites par un scénario de vol (phase : ' + (s.scenario_phase || '—') + '). Elles sont marquées « simulated » dans chaque export.');
    action('Quitter la démonstration', async () => {
      await api('ai/scenario', 'POST', { active: false });
      await reloadAI();
    }, row, 'small');
    box.append(text, row);
    view.append(box);
  } else if (!s.enabled) {
    let box = el('div', null, { className: 'banner warn' }),
      text = el('div', null),
      row = el('div', null, { className: 'row' });
    text.append(el('strong', 'AI Bridge désactivé. '), 'Aucune variable supplémentaire n’est lue dans le simulateur. Les éclairages fonctionnent normalement.');
    action('Activer la lecture', async () => {
      await api('ai/settings', 'PUT', { ...ai.settings, enabled: true });
      message('AI Bridge activé sur la connexion SimConnect existante.');
      await reloadAI();
    }, row, 'small primary');
    action('Démonstration', () => startScenario(), row, 'small', 'play');
    box.append(text, row);
    view.append(box);
  }
}
async function startScenario(phase = null) {
  await api('ai/scenario', 'POST', { active: true, phase });
  message('Démonstration lancée : données fictives.');
  await reloadAI();
}
function aiTiles(view) {
  let s = ai.status;
  if (!s) return;
  let tiles = el('div', null, { className: 'tiles' }),
    counts = s.counts,
    plan = s.plan;
  for (let [label, value, kind, note] of [
    ['Source des données', s.mode === 'scenario' ? 'Scénario' : 'SimConnect', s.mode === 'scenario' ? 'sim' : s.enabled ? 'ok' : '', s.mode === 'scenario' ? 'Valeurs fictives' : s.enabled ? 'Connexion partagée avec l’éclairage' : 'Lecture désactivée'],
    ['Simulateur', s.connected ? (s.paused ? 'En pause' : 'Connecté') : 'Déconnecté', s.connected ? (s.paused ? 'warn' : 'ok') : 'warn', s.mode === 'scenario' ? 'Simulé' : 'État SimConnect'],
    ['Mesures', String(counts.observed + counts.simulated), counts.stale ? 'warn' : counts.observed + counts.simulated ? 'ok' : '', counts.stale + ' périmée(s) · ' + counts.unavailable + ' indisponible(s)'],
    ['Plan de vol', plan.available ? 'Chargé' : 'Aucun', plan.available ? (plan.warnings.length ? 'warn' : 'ok') : '', plan.available ? (plan.source === 'demo' ? 'OFP de démonstration' : 'Importé il y a ' + plan.fetched_age_min + ' min') : s.simbrief_configured ? 'Prêt à importer' : 'Identifiant SimBrief à renseigner'],
  ]) {
    let tile = el('div', null, { className: 'tile' }),
      strong = el('strong', null);
    strong.append(el('span', null, { className: 'dot ' + kind }), value);
    tile.append(el('span', label), strong, el('small', note));
    tiles.append(tile);
  }
  view.append(tiles);
}
function unitText(unit) {
  return { deg: '°', s: '' }[unit] ?? unit;
}
function metric(parent, key, field) {
  let box = el('div', null, { className: 'metric ' + field.status + (typeof field.value === 'string' ? ' text' : ''), title: (field.source || key) + (field.note ? ' — ' + field.note : '') }),
    value = el('strong', formatValue(field, key));
  if (field.unit && field.value !== null && key !== 'zulu_time') value.append(el('small', unitText(field.unit)));
  box.append(el('span', field.label || key, { title: field.label || key }), value);
  let meta = el('div', null, { className: 'row', style: 'gap:6px' });
  // Fresh values are identified by colour; only degraded states carry a badge.
  if (!['observed', 'simulated'].includes(field.status)) meta.append(statusBadge(field.status));
  if (field.meaning) meta.append(badge(field.meaning, 'accent'));
  meta.append(el('small', ageText(field), { className: 'hint' }));
  box.append(meta);
  parent.append(box);
}
function liveView(view) {
  modeBanner(view);
  aiTiles(view);
  let doc = ai.context;
  if (!doc) return;
  for (let check of doc.checks || [])
    if (check.level === 'warning') view.append(el('div', check.message, { className: 'banner warn' }));
  let split = el('div', null, { className: 'split live' }),
    left = el('div', null, { className: 'stack' }),
    right = el('div', null, { className: 'stack' });
  split.append(left, right);
  view.append(split);
  let groups = Object.entries(doc.telemetry);
  if (!groups.length)
    left.append(el('div', 'Aucune mesure disponible. Connecter le simulateur, activer AI Bridge ou lancer la démonstration.', { className: 'empty' }));
  let groupGrid = el('div', null, { className: 'groups' });
  left.append(groupGrid);
  for (let [group, fields] of groups) {
    let c = card(groupGrid, GROUP_LABELS[group] || group),
      grid = el('div', null, { className: 'metrics' });
    for (let [key, field] of Object.entries(fields)) metric(grid, key, field);
    c.append(grid);
  }
  if (doc.derived) progressCard(right, doc.derived, doc.flight_plan);
  planSummary(right, doc.flight_plan);
  networkSummary(right, doc.ivao);
  notesCard(right);
  let info = card(right, 'Lecture des statuts', 'Le liseré de chaque mesure reprend la couleur de son statut');
  for (let [status, text] of [
    ['observed', 'Mesure récente du simulateur, dans le délai propre à la variable.'],
    ['stale', 'Dernière mesure connue, trop ancienne ou simulateur déconnecté.'],
    ['unavailable', 'Jamais reçue ou invalide ; jamais remplacée par zéro.'],
    ['simulated', 'Valeur fictive du scénario de démonstration.'],
    ['derived', 'Calculée à partir des observations et du plan, méthode indiquée.'],
  ]) {
    let row = el('div', null, { className: 'row' });
    row.append(statusBadge(status), el('span', text, { className: 'muted' }));
    info.append(row);
  }
}
function progressCard(parent, derived, plan) {
  let c = card(parent, 'Avancement sur la route', 'Calculé à partir des points de route de l’OFP ; route prévue, pas la route active du MCDU'),
    grid = el('div', null, { className: 'metrics' }),
    progress = derived.route_progress;
  c.append(grid);
  if (derived.direct_distance_to_destination)
    metric(grid, 'direct', { ...derived.direct_distance_to_destination, label: 'Distance directe à destination', note: derived.direct_distance_to_destination.method });
  if (progress) {
    metric(grid, 'remaining', { value: progress.remaining_along_route_nm, unit: 'NM', status: 'derived', label: 'Restant le long de la route', note: progress.method });
    let fuel = progress.fuel_vs_plan;
    if (fuel) metric(grid, 'fuel', { value: (fuel.difference_kg > 0 ? '+' : '') + fuel.difference_kg.toLocaleString('fr-FR'), unit: 'kg', status: 'derived', label: 'Carburant par rapport au plan', note: fuel.method + ' Prévu : ' + fuel.planned_kg + ' kg, observé : ' + fuel.observed_kg + ' kg.' });
    let wrap = el('div', null, { className: 'table-wrap' }),
      table = el('table', null),
      tbody = el('tbody', null);
    table.innerHTML = '<thead><tr><th>Prochains points</th><th>Distance</th><th>Altitude prévue</th></tr></thead>';
    for (let fix of progress.upcoming) {
      let tr = el('tr', null);
      tr.append(el('td', fix.ident, { className: 'mono' }), el('td', fix.distance_nm + ' NM', { className: 'value' }), el('td', fix.altitude_ft !== undefined ? fix.altitude_ft.toLocaleString('fr-FR') + ' ft' : '—', { className: 'value' }));
      tbody.append(tr);
    }
    table.append(tbody);
    wrap.append(table);
    c.append(wrap);
  } else if (plan) c.append(el('p', 'Avancement indisponible : position non observée ou points de route sans coordonnées.'));
}
function notesCard(parent) {
  let notes = ai.status?.notes || { text: '' },
    c = card(parent, 'Notes pilote', 'Ce que le simulateur ne fournit pas : STAR et VIA saisis au MCDU, piste, ATIS, clairance, messages. Incluses dans chaque export comme déclarations du pilote.'),
    area = el('textarea', null, { value: notesDraft ?? notes.text ?? '', maxLength: 2000, rows: 5, placeholder: 'Ex. : STAR DEMO2B, piste à confirmer, ATIS à écouter' }),
    counter = el('small', null, { className: 'hint' });
  area.setAttribute('aria-label', 'Notes pilote');
  let count = () => (counter.textContent = area.value.length + ' / 2000' + (notes.updated_utc ? ' · mises à jour ' + notes.updated_utc.replace('T', ' ').replace('Z', ' UTC') : ''));
  area.oninput = () => { notesDraft = area.value; count(); };
  count();
  c.append(area, counter);
  let bar = cardActions(c);
  action('Enregistrer les notes', async () => {
    let saved = await api('ai/notes', 'PUT', { text: area.value });
    ai.status = { ...ai.status, notes: saved };
    notesDraft = null;
    message(saved.text ? 'Notes enregistrées.' : 'Notes effacées.');
    area.blur();
    await reloadAI();
  }, bar, 'small primary');
}
function planSummary(parent, plan) {
  let c = card(parent, 'Plan de vol prévu', 'SimBrief — ne reflète pas nécessairement la route active du MCDU');
  if (!plan) {
    c.append(el('p', 'Aucun OFP chargé.'));
    let bar = cardActions(c);
    action('Ouvrir Plan de vol', () => navigate('Plan de vol'), bar, 'small');
    return;
  }
  let dl = el('dl', null, { className: 'kv' });
  for (let [k, v] of [
    ['Vol', plan.flight?.callsign || plan.flight?.number],
    ['Trajet', (plan.origin?.icao || '?') + ' → ' + (plan.destination?.icao || '?')],
    ['Dégagement', (plan.alternates || []).map(a => a.icao).join(', ')],
    ['Croisière', plan.cruise?.initial_altitude_ft ? 'FL' + Math.round(plan.cruise.initial_altitude_ft / 100) : null],
    ['AIRAC', plan.airac],
  ])
    if (v) dl.append(el('dt', k), el('dd', v));
  c.append(dl);
  for (let warning of plan.warnings || []) c.append(el('div', warning, { className: 'banner warn' }));
}
function dashboardSummary(parent) {
  let s = ai.status;
  if (!s) return;
  let c = card(parent, 'Assistant IA', s.mode === 'scenario' ? 'Démonstration en cours' : s.enabled ? 'Lecture active sur la connexion SimConnect' : 'Lecture désactivée', badge(s.mode === 'scenario' ? 'Simulé' : s.enabled ? 'Actif' : 'Inactif', s.mode === 'scenario' ? 'sim' : s.enabled ? 'ok' : ''));
  c.append(el('p', (s.counts.observed + s.counts.simulated) + ' mesure(s) exploitable(s), ' + s.counts.stale + ' périmée(s), ' + s.counts.unavailable + ' indisponible(s). Plan : ' + (s.plan.available ? 'chargé' : 'aucun') + '.'));
  let bar = cardActions(c);
  action('Copier pour l’IA', () => copyForChat('auto'), bar, 'small primary', 'copy');
  action('Vol en cours', () => navigate('Vol en cours'), bar, 'small ghost');
}

function planView(view) {
  let settings = ai.settings || {},
    status = ai.status?.plan || { available: false },
    top = el('div', null, { className: 'split' }),
    form = card(top, 'Compte SimBrief', 'Identifiant conservé dans local/ai-bridge.yaml ; aucun mot de passe n’est demandé'),
    grid = el('div', null, { className: 'grid' });
  view.append(top);
  form.append(grid);
  let kind = field(grid, 'Type d’identifiant', settings.simbrief_kind || 'username', 'text', ['username', 'userid']);
  grid.querySelector('select').options[0].textContent = 'Nom d’utilisateur';
  grid.querySelector('select').options[1].textContent = 'Pilot ID numérique';
  let user = field(grid, 'Identifiant SimBrief', settings.simbrief_user || '');
  let bar = cardActions(form);
  action('Enregistrer', async () => {
    await api('ai/settings', 'PUT', { ...ai.settings, simbrief_kind: kind(), simbrief_user: user().trim() || null });
    message('Identifiant SimBrief enregistré.');
    await reloadAI();
  }, bar, 'small');
  action('Actualiser depuis SimBrief', async () => {
    await importPlan();
  }, bar, 'small primary', 'refresh');
  let side = card(top, 'État du plan'),
    dl = el('dl', null, { className: 'kv' });
  side.append(dl);
  if (status.available) {
    for (let [k, v] of [
      ['Source', status.source === 'demo' ? 'Démonstration fictive' : 'SimBrief'],
      ['Importé', status.fetched_utc?.replace('T', ' ').replace('Z', ' UTC')],
      ['Âge de l’OFP', status.generated_age_h !== undefined ? status.generated_age_h + ' h' : 'inconnu'],
    ])
      dl.append(el('dt', k), el('dd', v));
  } else dl.append(el('dt', 'Plan'), el('dd', 'Aucun OFP chargé'));
  if (status.error) side.append(el('div', status.error, { className: 'banner danger' }));
  for (let warning of status.warnings || []) side.append(el('div', warning, { className: 'banner warn' }));
  let sideBar = cardActions(side);
  action('OFP de démonstration', async () => {
    await api('ai/simbrief/demo', 'POST', {});
    message('OFP fictif chargé.');
    await reloadAI();
  }, sideBar, 'small');
  if (status.available)
    action('Effacer', async () => {
      await api('ai/simbrief/clear', 'POST', {});
      await reloadAI();
    }, sideBar, 'small ghost danger');
  api('ai/plan')
    .then(result => planDetails(view, result.plan))
    .catch(e => message(e.message, true));
}
function planDetails(view, plan) {
  if (!plan) return;
  let header = card(view, (plan.origin?.icao || '?') + ' → ' + (plan.destination?.icao || '?') + (plan.flight?.callsign ? ' · ' + plan.flight.callsign : ''), 'Route planifiée : elle n’est jamais présentée comme route active du MCDU', badge('Planifié', 'accent'));
  let cols = el('div', null, { className: 'grid' });
  header.append(cols);
  let kv = (pairs, title) => {
    let box = el('div', null);
    box.append(el('h4', title));
    let dl = el('dl', null, { className: 'kv' });
    for (let [k, v] of pairs) if (v !== undefined && v !== null && v !== '') dl.append(el('dt', k), el('dd', String(v)));
    box.append(dl);
    cols.append(box);
  };
  let w = plan.weight_unit || '';
  kv([
    ['Appareil', [plan.aircraft?.icao, plan.aircraft?.registration].filter(Boolean).join(' · ')],
    ['Départ', [plan.origin?.icao, plan.origin?.runway && 'piste ' + plan.origin.runway].filter(Boolean).join(' · ')],
    ['Destination', [plan.destination?.icao, plan.destination?.runway && 'piste ' + plan.destination.runway].filter(Boolean).join(' · ')],
    ['Dégagements', (plan.alternates || []).map(a => a.icao).join(', ')],
    ['Niveau initial', plan.cruise?.initial_altitude_ft && 'FL' + Math.round(plan.cruise.initial_altitude_ft / 100)],
    ['Cost index', plan.cruise?.cost_index],
    ['Distance', plan.distance_nm && plan.distance_nm + ' NM'],
    ['AIRAC', plan.airac],
    ['Généré', plan.generated_utc?.replace('T', ' ').replace('Z', ' UTC')],
  ], 'Vol');
  let fuel = plan.fuel || {},
    labels = { ramp: 'Bloc', takeoff: 'Décollage', trip: 'Délestage', contingency: 'Réserve de route', alternate: 'Dégagement', final_reserve: 'Réserve finale', extra: 'Supplément', taxi: 'Roulage', minimum_takeoff: 'Minimum au décollage', landing: 'À l’atterrissage' };
  kv([
    ...Object.entries(labels).map(([k, label]) => [label, fuel[k] !== undefined ? fuel[k].toLocaleString('fr-FR') + ' ' + w : null]),
    ['Durée estimée', plan.times?.enroute_min && Math.floor(plan.times.enroute_min / 60) + ' h ' + String(plan.times.enroute_min % 60).padStart(2, '0')],
    ['ZFW / TOW / LDW', plan.weights && [plan.weights.zero_fuel, plan.weights.takeoff, plan.weights.landing].map(v => v?.toLocaleString('fr-FR') ?? '—').join(' / ') + ' ' + w],
  ], 'Carburant et masses');
  if (plan.route) header.append(el('h4', 'Route'), el('div', plan.route, { className: 'route' }));
  for (let [label, airport] of [['METAR départ', plan.origin], ['METAR destination', plan.destination]])
    if (airport?.metar) header.append(el('h4', label), el('div', airport.metar, { className: 'route' }));
  if (plan.waypoints?.length) {
    let c = card(view, 'Points de route', plan.waypoints_total + ' point(s) dans l’OFP'),
      wrap = el('div', null, { className: 'table-wrap' }),
      table = el('table', null),
      tbody = el('tbody', null);
    table.innerHTML = '<thead><tr><th>Point</th><th>Voie</th><th>Phase</th><th>Altitude</th></tr></thead>';
    for (let fix of plan.waypoints) {
      let tr = el('tr', null);
      tr.append(el('td', fix.ident, { className: 'mono' }), el('td', fix.airway || '—'), el('td', fix.stage || '—'), el('td', fix.altitude_ft !== undefined ? fix.altitude_ft.toLocaleString('fr-FR') + ' ft' : '—', { className: 'value' }));
      tbody.append(tr);
    }
    table.append(tbody);
    wrap.append(table);
    c.append(wrap);
  }
}

function exportView(view) {
  modeBanner(view);
  let doc = ai.preview,
    controls = card(view, 'Mode d’export', 'Envoyer le briefing une fois au sol, puis des points en vol au fil du vol dans la même conversation'),
    row = el('div', null, { className: 'row' }),
    seg = el('div', null, { className: 'segmented' });
  for (let [level, [label]] of Object.entries(LEVELS)) {
    let b = el('button', label, { type: 'button', className: ai.level === level ? 'active' : '' });
    b.onclick = async () => {
      ai.level = level;
      ai.preview = await api('ai/context?level=' + level);
      render();
    };
    seg.append(b);
  }
  row.append(seg);
  controls.append(row);
  row = el('div', null, { className: 'row' });
  let resolved = doc?.level || (ai.level === 'auto' ? ai.status?.suggested_level : ai.level);
  if (resolved) controls.append(el('p', (ai.level === 'auto' ? 'Mode retenu : ' + LEVELS[resolved][0] + '. ' : '') + LEVELS[resolved][1]));
  if (doc) {
    let size = JSON.stringify(doc).length;
    row.append(badge(size.toLocaleString('fr-FR') + ' caractères'), badge('≈ ' + Math.ceil(size / 3.5).toLocaleString('fr-FR') + ' tokens (estimation)'), badge(doc.data_origin === 'simconnect' ? 'SimConnect' : 'Données simulées', doc.data_origin === 'simconnect' ? 'ok' : 'sim'));
  }
  controls.append(row);
  let bar = cardActions(controls);
  action('Copier pour un chat IA', () => copyForChat(ai.level), bar, 'primary', 'copy');
  action('Copier le JSON seul', async () => {
    await copyText(JSON.stringify(await api('ai/context?level=' + ai.level), null, 1));
    message('JSON copié.');
  }, bar, '', 'copy');
  action('Télécharger le fichier JSON', async () => {
    let data = await api('ai/context?level=' + ai.level),
      blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      link = el('a', null, { href: URL.createObjectURL(blob), download: 'flight-context-' + data.generated_utc.replace(/[:-]/g, '') + '-' + ai.level + '.json' });
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }, bar, '', 'export');
  action('Enregistrer dans local/exports', async () => {
    let r = await api('ai/export', 'POST', { level: ai.level });
    message('Fichier enregistré : ' + r.path);
  }, bar, 'ghost');
  help(controls, 'La copie ajoute une courte consigne invitant l’assistant à s’en tenir aux valeurs fournies. Aucun modèle d’IA n’est appelé par Glareshield.');
  notesCard(view);
  if (doc) {
    let c = card(view, 'Aperçu', 'Généré le ' + doc.generated_utc.replace('T', ' ').replace('Z', ' UTC'));
    c.append(el('pre', JSON.stringify(doc, null, 2), { className: 'json' }));
  }
}

function variablesView(view) {
  let settings = structuredClone(ai.settings || {}),
    top = el('div', null, { className: 'split' }),
    module = card(top, 'Module AI Bridge', 'Lecture seule ; aucune commande n’est envoyée au cockpit');
  view.append(top);
  let enabled = field(module, 'Lire les variables AI Bridge dans le simulateur', settings.enabled, 'checkbox');
  help(module, 'Utilise la connexion SimConnect de Glareshield : aucune seconde connexion, aucun redémarrage des éclairages.');
  let age = field(module, 'Âge maximal d’un OFP avant avertissement (h)', settings.ofp_max_age_h ?? 12, 'number');
  let bar = cardActions(module);
  action('Enregistrer', async () => {
    await api('ai/settings', 'PUT', { ...ai.settings, enabled: enabled(), ofp_max_age_h: age() });
    message('Réglages AI Bridge enregistrés.');
    await reloadAI();
  }, bar, 'small primary');
  let demo = card(top, 'Scénario de démonstration', 'Vol fictif d’A320 permettant d’éprouver l’affichage et l’export sans simulateur');
  demo.append(el('p', ai.status?.mode === 'scenario' ? 'Démonstration active (phase : ' + ai.status.scenario_phase + ').' : 'Démonstration inactive.'));
  let phases = { parking: 'Parking', taxi_out: 'Roulage', takeoff: 'Décollage', climb: 'Montée', cruise: 'Croisière', descent: 'Descente', approach: 'Approche', landing: 'Atterrissage' },
    phase = field(demo, 'Phase de départ du scénario', 'parking', 'text', Object.keys(phases));
  for (let option of demo.querySelector('select').options) option.textContent = phases[option.value];
  let demoBar = cardActions(demo);
  if (ai.status?.mode === 'scenario')
    action('Arrêter la démonstration', async () => {
      await api('ai/scenario', 'POST', { active: false });
      await reloadAI();
    }, demoBar, 'small', 'stop');
  if (ai.status?.mode !== 'scenario') action('Lancer la démonstration', () => startScenario(phase()), demoBar, 'small', 'play');
  else action('Relancer à cette phase', () => startScenario(phase()), demoBar, 'small ghost', 'play');

  let catalog = card(view, 'Catalogue des variables', 'SimVars standard documentées par le SDK MSFS ; leur correspondance avec le Fenix reste à valider sur votre installation'),
    wrap = el('div', null, { className: 'table-wrap' }),
    table = el('table', null),
    tbody = el('tbody', null);
  table.innerHTML = '<thead><tr><th>Variable</th><th>Valeur</th><th>Statut</th><th>Vérification</th><th>Exporter</th><th>Validée</th></tr></thead>';
  let disabled = new Set(settings.disabled || []),
    validated = new Set(settings.validated || []);
  for (let v of ai.variables || []) {
    let tr = el('tr', null),
      name = el('td', v.label);
    name.append(el('span', (v.origin === 'lvar' ? 'L:' : '') + v.variable + (v.unit ? ' · ' + v.unit : '') + ' · ' + ENTRY_LEVELS[v.level], { className: 'sub mono' }));
    let value = el('td', formatValue(v) + (v.unit && v.value !== null ? ' ' + v.unit : ''), { className: 'value' });
    value.append(el('span', v.meaning || ageText(v), { className: 'sub' }));
    let status = el('td', null),
      verification = el('td', null);
    status.append(statusBadge(v.status));
    verification.append(badge(VERIFICATION_LABELS[v.verification] || v.verification, v.verification === 'validated_locally' ? 'ok' : v.verification === 'configured_unverified' ? 'warn' : ''));
    let toggles = [];
    for (let [set, inverse] of [[disabled, true], [validated, false]]) {
      let td = el('td', null),
        box = el('input', null, { type: 'checkbox', checked: inverse ? !set.has(v.key) : set.has(v.key), disabled: v.origin === 'lvar' });
      box.setAttribute('aria-label', (inverse ? 'Exporter ' : 'Validée : ') + v.label);
      box.onchange = () => ((inverse ? !box.checked : box.checked) ? set.add(v.key) : set.delete(v.key));
      td.append(box);
      toggles.push(td);
    }
    tr.title = v.note || '';
    tr.append(name, value, status, verification, ...toggles);
    tbody.append(tr);
  }
  table.append(tbody);
  wrap.append(table);
  catalog.append(wrap);
  let catalogBar = cardActions(catalog);
  action('Enregistrer la sélection', async () => {
    await api('ai/settings', 'PUT', { ...ai.settings, disabled: [...disabled], validated: [...validated] });
    message('Sélection enregistrée.');
    await reloadAI();
  }, catalogBar, 'small primary');
  help(catalog, 'Cocher « Validée » uniquement après avoir vérifié au parking et en vol que la valeur correspond au cockpit du Fenix.');

  let lvars = card(view, 'LVars Fenix', 'Variables relevées dans une liste vérifiée ou avec scripts/probe_simulator.py ; leur sens doit être confirmé dans votre installation');
  if (!settings.lvars?.length) lvars.append(el('p', 'Aucune LVar configurée. Le préréglage ajoute les variables connues du Fenix A320, à valider ensuite dans votre cockpit.'));
  let presetBar = el('div', null, { className: 'row' });
  lvars.append(presetBar);
  action('Ajouter le préréglage Fenix A320', async () => {
    let result = await api('ai/presets/fenix-a320', 'POST', {});
    message(result.added ? result.added + ' variable(s) ajoutée(s) ; volets et armement des aérofreins standard retirés de l’export.' : 'Préréglage déjà présent.');
    await reloadAI();
  }, presetBar, 'small');
  presetBar.append(el('small', 'Les variables existantes ne sont pas modifiées. Voir docs/fenix-a320.md.', { className: 'hint' }));
  for (let [index, lvar] of (settings.lvars || []).entries()) {
    let row = el('div', null, { className: 'row' });
    row.append(el('strong', lvar.label), el('span', 'L:' + lvar.name.replace(/^L:/, ''), { className: 'mono muted' }), badge(lvar.validated ? 'Validée' : 'Non vérifiée', lvar.validated ? 'ok' : 'warn'));
    if (Object.keys(lvar.values || {}).length) row.append(el('span', Object.entries(lvar.values).map(([k, v]) => k + ' = ' + v).join(' ; '), { className: 'muted' }));
    action('Retirer', async () => {
      settings.lvars.splice(index, 1);
      await api('ai/settings', 'PUT', settings);
      await reloadAI();
    }, row, 'small ghost danger');
    lvars.append(row);
  }
  let details = el('details', null);
  details.append(el('summary', 'Ajouter une LVar'));
  let form = el('div', null, { className: 'grid', style: 'margin-top:12px' });
  details.append(form);
  let key = field(form, 'Identifiant d’export (minuscules, ex. fcu_ap1)', ''),
    name = field(form, 'Nom de la LVar (sans L:)', ''),
    label = field(form, 'Libellé', ''),
    unit = field(form, 'Unité (facultative)', ''),
    level = field(form, 'Exportée dans', 'essential', 'text', ['essential', 'detailed']),
    interval = field(form, 'Intervalle de lecture (ms, 250 minimum)', 1000, 'number'),
    maxAge = field(form, 'Âge maximal avant péremption (s)', 5, 'number'),
    values = field(form, 'Signification des valeurs (ex. 0=OFF;1=ON)', ''),
    checked = field(form, 'Sens vérifié dans le cockpit', false, 'checkbox');
  form.querySelectorAll('select')[0].options[0].textContent = 'Briefing, point en vol et complet';
  form.querySelectorAll('select')[0].options[1].textContent = 'Complet seulement';
  let addBar = el('div', null, { className: 'row', style: 'margin-top:12px' });
  details.append(addBar);
  action('Ajouter', async () => {
    let mapping = {};
    for (let part of values().split(';').map(v => v.trim()).filter(Boolean)) {
      let [k, ...rest] = part.split('=');
      if (!rest.length) throw Error('Format attendu : valeur=signification, séparées par des points-virgules.');
      mapping[k.trim()] = rest.join('=').trim();
    }
    settings.lvars = [...(settings.lvars || []), { key: key().trim(), name: name().trim(), label: label().trim(), unit: unit().trim() || null, level: level(), interval_ms: interval(), max_age_s: maxAge(), values: mapping, validated: checked() }];
    await api('ai/settings', 'PUT', settings);
    message('LVar ajoutée.');
    await reloadAI();
  }, addBar, 'small primary');
  lvars.append(details);
}

// IVAO network: published data shown as received; untrusted texts are only ever inserted as text.
const FEED_STATUS = { current: ['À jour', 'ok'], stale: ['Périmé', 'warn'], unavailable: ['Indisponible', 'danger'] };
const FEED_NAMES = { whazzup: 'Contrôleurs et ATIS', metar: 'METAR', taf: 'TAF' };
const ROLE_LABELS = { origin: 'Départ', destination: 'Destination', alternate: 'Dégagement', manual: 'Ajouté' };
const MATCH_LABELS = {
  callsign_prefix: m => 'indicatif ' + m.airport,
  distance_to_aircraft: m => m.distance_nm + ' NM de l’appareil',
  distance_to_airport: m => m.distance_nm + ' NM de ' + m.airport,
  published_range: m => 'portée publiée ' + m.range_nm + ' NM',
};
const CHANGE_LABELS = {
  new: () => 'Nouvel ATIS',
  revision: c => 'Nouvelle révision' + (c.previous_revision ? ' (était ' + c.previous_revision + ')' : ''),
  text: () => 'Texte modifié',
};
function utcText(value) {
  return value ? value.replace('T', ' ').replace('Z', ' UTC') : '—';
}
function durationText(s) {
  return s < 90 ? s + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : Math.round(s / 3600) + ' h';
}
function matchText(item) {
  return item.matched_by.map(m => MATCH_LABELS[m.basis]?.(m) || m.basis).join(' ; ');
}
function feedNote(feed) {
  let parts = [];
  if (feed.fetched_age_s !== undefined) parts.push('récupéré il y a ' + durationText(feed.fetched_age_s));
  if (feed.source_updated_age_s !== undefined) parts.push('source mise à jour il y a ' + durationText(feed.source_updated_age_s));
  return feed.last_error || parts.join(' · ') || feed.reason || '';
}
function networkSummary(parent, section) {
  let s = ai.status?.ivao;
  if (!s?.enabled) return;
  let c = card(parent, 'Réseau IVAO', 'Données publiées par IVAO, distinctes de la télémétrie'),
    dl = el('dl', null, { className: 'kv' });
  for (let [name, status] of Object.entries(s.feeds)) dl.append(el('dt', FEED_NAMES[name]), el('dd', FEED_STATUS[status][0]));
  if (section?.controllers) dl.append(el('dt', 'Positions retenues'), el('dd', section.controllers.map(item => item.callsign).join(', ') || 'aucune'));
  c.append(dl);
  if (s.atis_changes) c.append(el('div', s.atis_changes + ' ATIS modifié(s) depuis la première récupération.', { className: 'banner' }));
  let bar = cardActions(c);
  action('Ouvrir Réseau IVAO', () => navigate('Réseau IVAO'), bar, 'small');
}
async function saveNetwork(changes, text) {
  await api('ai/settings', 'PUT', { ...ai.settings, ivao: { ...ai.settings.ivao, ...changes } });
  if (text) message(text);
  await reloadAI();
}
async function refreshNetwork() {
  let r = await api('ai/ivao/refresh', 'POST', {}),
    results = Object.entries(r.results),
    errors = results.filter(([, v]) => v.result === 'error'),
    fetched = results.filter(([, v]) => v.result === 'fetched').map(([k]) => FEED_NAMES[k]);
  ai.network = r;
  if (errors.length) message(errors.map(([, v]) => v.message).join(' '), true);
  else message(fetched.length ? 'Actualisé : ' + fetched.join(', ') + '.' : 'Données déjà récentes : intervalle minimal IVAO respecté.');
  render();
}
function bulletinBlock(parent, label, bulletin, kind) {
  parent.append(el('h4', label));
  if (bulletin.status === 'feed_unavailable') return parent.append(el('p', 'Flux ' + kind + ' indisponible.', { className: 'muted' }));
  if (bulletin.status === 'not_published') return parent.append(el('p', 'Aucun ' + kind + ' publié par IVAO pour cet aérodrome.', { className: 'muted' }));
  parent.append(el('div', bulletin.raw, { className: 'route' }));
  let times = [];
  if (bulletin.observed_utc) times.push('observé ' + utcText(bulletin.observed_utc));
  if (bulletin.issued_utc) times.push('émis ' + utcText(bulletin.issued_utc));
  if (bulletin.valid_from_utc) times.push('valide du ' + utcText(bulletin.valid_from_utc) + ' au ' + utcText(bulletin.valid_to_utc));
  if (bulletin.bulletin_age_min !== undefined) times.push('bulletin âgé de ' + durationText(bulletin.bulletin_age_min * 60));
  if (times.length) parent.append(el('small', times.join(' · '), { className: 'hint' }));
}
function atisBlock(parent, item) {
  let head = el('div', null, { className: 'row' });
  head.append(el('strong', item.station, { className: 'mono' }));
  if (item.revision) head.append(badge('Information ' + item.revision, 'accent'));
  if (item.change) head.append(badge(CHANGE_LABELS[item.change.kind]?.(item.change) || 'Modifié', 'warn'));
  head.append(el('small', 'émis ' + utcText(item.source_timestamp_utc) + (item.source_age_min !== undefined ? ' (il y a ' + durationText(item.source_age_min * 60) + ')' : ''), { className: 'hint' }));
  parent.append(head);
  if (item.lines) parent.append(el('div', item.lines.join('\n'), { className: 'route', style: 'white-space:pre-wrap' }));
}
function airportCard(parent, doc, weather, lookup = false) {
  let extra = lookup ? null : badge(weather.roles.map(role => ROLE_LABELS[role] || role).join(' · '), weather.roles.includes('destination') ? 'accent' : '');
  let c = card(parent, weather.icao, lookup ? 'Consultation ponctuelle, non incluse dans les exports' : null, extra);
  bulletinBlock(c, 'METAR publié', weather.metar, 'METAR');
  if (weather.taf) bulletinBlock(c, 'TAF publié', weather.taf, 'TAF');
  c.append(el('h4', 'ATIS'));
  let atis = (doc.atis || []).filter(item => item.airport === weather.icao);
  if (doc.controllers === null) c.append(el('p', 'Flux Whazzup indisponible.', { className: 'muted' }));
  else if (!atis.length) c.append(el('p', 'Aucun ATIS publié par une position de cet aérodrome.', { className: 'muted' }));
  for (let item of atis) atisBlock(c, item);
  let positions = (doc.controllers || []).filter(item => item.matched_by.some(m => m.basis === 'callsign_prefix' && m.airport === weather.icao));
  if (positions.length) {
    c.append(el('h4', 'Positions de l’aérodrome'));
    let row = el('div', null, { className: 'row' });
    for (let item of positions) row.append(badge(item.callsign + (item.frequency_mhz ? ' · ' + item.frequency_mhz.toFixed(3) : ''), 'ok'));
    c.append(row);
  }
}
function controllersCard(parent, doc) {
  let position = doc.selection.aircraft_position,
    c = card(parent, 'Positions en ligne retenues', 'Rayons : aérodrome ' + doc.selection.radii_nm.aerodrome + ' NM, approche ' + doc.selection.radii_nm.approach + ' NM, en route ' + doc.selection.radii_nm.enroute + ' NM · position de l’appareil : ' + (STATUS_LABELS[position.status] || position.status).toLowerCase() + (position.reason ? ' (' + position.reason + ')' : ''));
  if (doc.controllers === null) {
    c.append(el('p', 'Flux Whazzup indisponible : la présence de contrôleurs est inconnue.'));
    return;
  }
  if (!doc.controllers.length) c.append(el('p', 'Aucune position opérationnelle en ligne ne répond aux critères.'));
  else {
    let wrap = el('div', null, { className: 'table-wrap' }),
      table = el('table', null),
      tbody = el('tbody', null);
    table.innerHTML = '<thead><tr><th>Indicatif</th><th>Type</th><th>Fréquence</th><th>Retenue par</th><th>Distance à l’appareil</th></tr></thead>';
    for (let item of doc.controllers) {
      let tr = el('tr', null);
      tr.append(el('td', item.callsign, { className: 'mono' }), el('td', item.position || '—'), el('td', item.frequency_mhz ? item.frequency_mhz.toFixed(3) : '—', { className: 'value' }), el('td', matchText(item)), el('td', item.distance_to_aircraft_nm !== undefined ? item.distance_to_aircraft_nm + ' NM' : '—', { className: 'value' }));
      tbody.append(tr);
    }
    table.append(tbody);
    wrap.append(table);
    c.append(wrap);
  }
  if (doc.controllers_omitted) c.append(el('p', doc.controllers_omitted + ' position(s) supplémentaire(s) non affichée(s).', { className: 'muted' }));
  if (doc.observers?.length) {
    let details = el('details', null);
    details.append(el('summary', doc.observers_selected + ' observateur(s), sans position opérationnelle'));
    for (let item of doc.observers) details.append(el('div', item.callsign + ' — ' + matchText(item), { className: 'mono muted' }));
    c.append(details);
  }
  help(c, doc.selection.method);
}
function lookupCard(parent, settings) {
  let c = card(parent, 'Consulter un aérodrome', 'Lecture des données déjà récupérées : aucune requête supplémentaire vers IVAO'),
    grid = el('div', null, { className: 'grid' }),
    code = field(grid, 'Code OACI', ai.lookup?.weather.airports[0]?.icao || '');
  c.append(grid);
  let bar = cardActions(c);
  action('Consulter', async () => {
    ai.lookup = await api('ai/ivao/airport/' + encodeURIComponent(code().trim()));
    render();
  }, bar, 'small primary');
  action('Suivre dans les exports', async () => {
    let icao = code().trim().toUpperCase();
    if ((settings.airports || []).includes(icao)) throw Error(icao + ' est déjà suivi.');
    await saveNetwork({ airports: [...(settings.airports || []), icao] }, icao + ' ajouté aux aérodromes suivis.');
  }, bar, 'small');
  if (ai.lookup) airportCard(parent, ai.lookup, ai.lookup.weather.airports[0], true);
}
function networkSettings(parent, settings) {
  let c = card(parent, 'Réglages IVAO', 'Lecture seule, sans authentification ; réglages conservés dans local/ai-bridge.yaml'),
    grid = el('div', null, { className: 'grid' });
  c.append(grid);
  let enabled = field(grid, 'Récupérer les données publiques IVAO', settings.enabled, 'checkbox'),
    aerodrome = field(grid, 'Rayon DEL, GND, TWR (NM)', settings.radius_aerodrome_nm ?? 30, 'number'),
    approach = field(grid, 'Rayon APP, DEP (NM)', settings.radius_approach_nm ?? 80, 'number'),
    enroute = field(grid, 'Rayon CTR, FSS (NM)', settings.radius_enroute_nm ?? 400, 'number'),
    whazzup = field(grid, 'Intervalle Whazzup (s, 15 minimum)', settings.whazzup_interval_s ?? 60, 'number'),
    weather = field(grid, 'Intervalle METAR et TAF (s, 300 minimum)', settings.weather_interval_s ?? 600, 'number'),
    notify = field(grid, 'Notifier la connexion ou la déconnexion d’une position', settings.notifications, 'checkbox'),
    seconds = field(grid, 'Durée d’affichage de la notification (s)', settings.notification_seconds ?? 10, 'number');
  help(c, 'Notification : bande discrète toujours visible, sans prise de focus ni clic, pour les positions du départ, de l’arrivée, des dégagements, des aérodromes ajoutés et de la route de l’OFP. Visible sur MSFS en fenêtré ou plein écran sans bordure ; le plein écran exclusif peut la masquer, d’où le test ci-dessous.');
  help(c, 'Les rayons portent sur le centre déclaré de chaque position, autour de l’appareil et des aérodromes suivis : un centre contrôle une zone bien plus vaste qu’une tour. Départ, destination et dégagements viennent de l’OFP SimBrief. Aérodromes ajoutés, inclus dans les exports (6 au plus) :');
  let row = el('div', null, { className: 'row' });
  if (!settings.airports?.length) row.append(el('span', 'aucun', { className: 'muted' }));
  for (let icao of settings.airports || [])
    action('Retirer ' + icao, () => saveNetwork({ airports: settings.airports.filter(item => item !== icao) }, icao + ' retiré.'), row, 'small ghost');
  c.append(row);
  let bar = cardActions(c);
  action('Enregistrer', () => saveNetwork({ enabled: enabled(), radius_aerodrome_nm: aerodrome(), radius_approach_nm: approach(), radius_enroute_nm: enroute(), whazzup_interval_s: whazzup(), weather_interval_s: weather(), notifications: notify(), notification_seconds: seconds() }, 'Réglages IVAO enregistrés.'), bar, 'small primary');
  action('Tester la notification', async () => { await api('ai/ivao/notify-test', 'POST', {}); message('Notification envoyée : vérifiez qu’elle apparaît par-dessus MSFS.'); }, bar, 'small');
}
function networkView(view) {
  let page = ai.network || {},
    settings = page.settings || {},
    doc = page.view;
  if (!page.enabled) {
    let box = el('div', null, { className: 'banner warn' }),
      text = el('div', null),
      row = el('div', null, { className: 'row' });
    text.append(el('strong', 'Intégration IVAO désactivée. '), 'Aucune requête n’est envoyée à IVAO et les exports ne contiennent aucune donnée réseau.');
    action('Activer', () => saveNetwork({ enabled: true }, 'Intégration IVAO activée.'), row, 'small primary');
    box.append(text, row);
    view.append(box);
  }
  if (doc) {
    let tiles = el('div', null, { className: 'tiles' });
    for (let [name, feed] of Object.entries(doc.feeds)) {
      let [label, kind] = FEED_STATUS[feed.status],
        tile = el('div', null, { className: 'tile' }),
        strong = el('strong', null);
      strong.append(el('span', null, { className: 'dot ' + (kind === 'danger' ? 'warn' : kind) }), label);
      tile.append(el('span', FEED_NAMES[name]), strong, el('small', feedNote(feed)));
      tiles.append(tile);
    }
    view.append(tiles);
    help(view, 'Bulletins publiés par IVAO. Le METAR inclus dans l’OFP figure dans Plan de vol, les conditions observées dans MSFS dans Vol en cours.');
    if (!doc.weather.airports.length) view.append(el('div', 'Aucun aérodrome suivi : importer un OFP dans Plan de vol ou ajouter un aérodrome ci-dessous.', { className: 'empty' }));
    let grid = el('div', null, { className: 'groups' });
    view.append(grid);
    for (let weather of doc.weather.airports) airportCard(grid, doc, weather);
    controllersCard(view, doc);
    lookupCard(view, settings);
    help(view, 'Glareshield restitue ces données avec leur provenance ; leur interprétation revient à l’assistant. Un ATIS affiché ici n’a pas pour autant été consulté par le pilote ni annoncé au contrôleur.');
  }
  networkSettings(view, settings);
}

const AI_VIEWS = {
  'Vol en cours': ['plane', 'Télémétrie qualifiée et plan prévu, tels qu’ils seront transmis à l’assistant', liveView, true],
  'Plan de vol': ['plan', 'Dernier OFP SimBrief, importé manuellement', planView, false],
  'Réseau IVAO': ['network', 'Contrôleurs en ligne, ATIS et météo publiés par IVAO, en lecture seule', networkView, true],
  'Export IA': ['export', 'Contexte prêt à coller dans ChatGPT, Claude ou un autre assistant', exportView, false],
  'Variables IA': ['variables', 'Catalogue lu dans le simulateur, vérifications et LVars locales', variablesView, false],
};
for (let [name, [iconName, subtitle, renderer, live]] of Object.entries(AI_VIEWS))
  VIEWS[name] = {
    icon: iconName,
    subtitle,
    render: renderer,
    live,
    actions: bar => {
      if (name === 'Réseau IVAO' && ai.network?.enabled) action('Actualiser', refreshNetwork, bar, '', 'refresh');
      action('Copier pour l’IA', () => copyForChat(name === 'Export IA' ? ai.level : 'auto'), bar, 'primary', 'copy');
    },
    navBadge:
      name === 'Vol en cours' ? () => (ai.status?.mode === 'scenario' ? badge('Démo', 'sim') : null)
      : name === 'Réseau IVAO' ? () => (ai.status?.ivao?.atis_changes ? badge('ATIS', 'warn') : null)
      : null,
  };
VIEWS['Vol en cours'].summary = dashboardSummary;
const AI_READY = {
  'Vol en cours': () => ai.context,
  'Plan de vol': () => true,
  'Réseau IVAO': () => ai.network,
  'Export IA': () => ai.preview,
  'Variables IA': () => ai.variables,
};
for (let name of AI_PAGES) {
  VIEWS[name].ready = () => ai.status && ai.settings && AI_READY[name]();
  VIEWS[name].load = () => loadAI(true);
}
