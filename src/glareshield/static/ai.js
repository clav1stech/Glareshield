// AI Bridge views: live flight context, SimBrief plan, export and variable catalogue.
const AI_PAGES = ['Vol en cours', 'Plan de vol', 'Export IA', 'Variables IA'];
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
let ai = { status: null, context: null, settings: null, variables: null, level: 'auto', preview: null };
const LEVELS = {
  auto: ['Automatique', 'Briefing au sol, point en vol une fois en l’air.'],
  briefing: ['Briefing', 'À envoyer une fois, au sol : plan complet (route, SID, STAR, points de route, carburant, masses, METAR, horaires) et état de l’avion.'],
  flight: ['Point en vol', 'À envoyer aussi souvent que nécessaire : trajectoire, configuration, autopilote, prochains points, distance restante et carburant comparé au plan. Complète le briefing déjà transmis.'],
  full: ['Complet', 'Diagnostic : toutes les variables avec leur source et leur vérification, et le plan intégral.'],
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
  if (tab === 'Vol en cours') ai.context = await api('ai/context?level=full');
  if (full || !ai.settings) ai.settings = await api('ai/settings');
  if (tab === 'Variables IA' && (full || !ai.variables || !isEditing())) ai.variables = await api('ai/variables');
  if (tab === 'Export IA' && !isEditing()) ai.preview = await api('ai/context?level=' + ai.level);
}
REFRESH_HOOKS.push(async () => {
  if (AI_PAGES.includes(tab) || tab === 'Tableau de bord') await loadAI();
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
    area = el('textarea', null, { value: notes.text || '', maxLength: 2000, rows: 5, placeholder: 'Ex. : STAR LERG1D via ELRUN, ILS 31R, ATIS K, QNH 1022, clairance FL340' }),
    counter = el('small', null, { className: 'hint' });
  area.setAttribute('aria-label', 'Notes pilote');
  let count = () => (counter.textContent = area.value.length + ' / 2000' + (notes.updated_utc ? ' · mises à jour ' + notes.updated_utc.replace('T', ' ').replace('Z', ' UTC') : ''));
  area.oninput = count;
  count();
  c.append(area, counter);
  let bar = cardActions(c);
  action('Enregistrer les notes', async () => {
    let saved = await api('ai/notes', 'PUT', { text: area.value });
    ai.status = { ...ai.status, notes: saved };
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
    action('Ouvrir Plan de vol', () => { tab = 'Plan de vol'; render(); }, bar, 'small');
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
  action('Vol en cours', () => { tab = 'Vol en cours'; render(); }, bar, 'small ghost');
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
    message('Récupération du dernier OFP…');
    await api('ai/simbrief/refresh', 'POST', {});
    message('OFP importé.');
    await reloadAI();
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

const AI_VIEWS = {
  'Vol en cours': ['plane', 'Télémétrie qualifiée et plan prévu, tels qu’ils seront transmis à l’assistant', liveView, true],
  'Plan de vol': ['plan', 'Dernier OFP SimBrief, importé manuellement', planView, false],
  'Export IA': ['export', 'Contexte prêt à coller dans ChatGPT, Claude ou un autre assistant', exportView, false],
  'Variables IA': ['variables', 'Catalogue lu dans le simulateur, vérifications et LVars locales', variablesView, false],
};
for (let [name, [iconName, subtitle, renderer, live]] of Object.entries(AI_VIEWS))
  VIEWS[name] = {
    icon: iconName,
    subtitle,
    render: renderer,
    live,
    actions: bar => action('Copier pour l’IA', () => copyForChat(name === 'Export IA' ? ai.level : 'auto'), bar, 'primary', 'copy'),
    navBadge: name === 'Vol en cours' ? () => (ai.status?.mode === 'scenario' ? badge('Démo', 'sim') : null) : null,
  };
VIEWS['Vol en cours'].summary = dashboardSummary;
const AI_READY = {
  'Vol en cours': () => ai.context,
  'Plan de vol': () => true,
  'Export IA': () => ai.preview,
  'Variables IA': () => ai.variables,
};
for (let name of AI_PAGES) {
  VIEWS[name].ready = () => ai.status && ai.settings && AI_READY[name]();
  VIEWS[name].load = () => loadAI(true);
}
