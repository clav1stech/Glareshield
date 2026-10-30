// Session UI sends pilot gestures; the service owns persistence and arbitration.
const DISPLAY_THEMES = { auto: 'automatique', light: 'clair', dark: 'sombre' };
let display = { theme: 'auto', text_size: 'standard' };
function applyDisplay() {
  document.documentElement.dataset.theme = display.theme;
  document.documentElement.dataset.textSize = display.text_size;
  $('#themeButton').textContent = 'Thème : ' + DISPLAY_THEMES[display.theme];
}
async function loadDisplay() {
  display = await api('display');
  applyDisplay();
}
async function saveDisplay(next) {
  display = await api('display', 'PUT', next);
  applyDisplay();
}
$('#themeButton').onclick = async () => {
  try {
    let themes = Object.keys(DISPLAY_THEMES);
    await saveDisplay({ ...display, theme: themes[(themes.indexOf(display.theme) + 1) % themes.length] });
  } catch (e) { message(e.message, true); }
};

// Derive every label from reported evidence. Configured hardware is not a connection proof.
function preparationStatus(s, runtime, configuration, lost = false) {
  const item = (label, kind, detail) => ({ label, kind, detail });
  let sim = runtime?.simulator || {}, counts = s?.counts || {}, plan = s?.plan || {},
    network = s?.ivao || {}, demo = s?.mode === 'scenario',
    lights = Object.values(configuration?.devices || {}).filter(d => d.kind === 'light'),
    feeds = Object.values(network.feeds || {}), blockers = [], warnings = [];
  let simulator = !sim.enabled ? item('Désactivé', '', 'Aucune lecture SimConnect active.')
    : sim.error ? item('Erreur', 'danger', 'Lecture SimConnect en erreur : ' + sim.error)
    : sim.stale ? item('Périmé', 'warn', 'Aucun état récent reçu du simulateur.')
    : sim.connected ? item(sim.paused ? 'En pause' : 'Connecté', sim.paused ? 'warn' : 'ok', 'Connexion SimConnect observée, en lecture seule.')
    : item('En attente', 'warn', 'Aucun simulateur actif observé.');
  let bridge = s?.settings_error ? item('Erreur', 'danger', 'Réglages AI Bridge invalides.')
    : demo ? item('Démonstration', 'sim', 'Télémétrie fictive ; ne décrit pas le simulateur.')
    : !s?.enabled ? item('Désactivé', '', 'Activer la lecture dans Variables IA.')
    : counts.stale ? item('Périmé', 'warn', counts.stale + ' mesure(s) périmée(s).')
    : s.telemetry_errors ? item('Erreur', 'danger', s.telemetry_errors + ' mesure(s) en erreur.')
    : s.connected && counts.observed ? item('Connecté', 'ok', counts.observed + ' mesure(s) récente(s).')
    : item('En attente', 'warn', 'Aucune télémétrie récente observée.');
  let simbrief = plan.error ? item('Erreur', 'danger', plan.error + (plan.available ? ' Dernier plan conservé.' : ''))
    : plan.source === 'demo' ? item('Démonstration', 'sim', 'OFP fictif, à remplacer pour un vol réel.')
    : !plan.available ? item(s?.simbrief_configured ? 'Prêt à importer' : 'Non configuré', '', 'Import manuel du dernier OFP.')
    : plan.warnings?.length ? item('Périmé / à vérifier', 'warn', plan.warnings.join(' '))
    : item('Chargé', 'ok', 'OFP importé il y a ' + plan.fetched_age_min + ' min ; vérifier le vol prévu.');
  let ivao = !network.enabled ? item('Désactivé', '', 'Facultatif ; le suivi peut fonctionner sans IVAO.')
    : network.simulation ? item('Démonstration', 'sim', 'Flux IVAO fictifs embarqués ; aucun téléchargement.')
    : Object.keys(network.feed_errors || {}).length ? item('Erreur', 'danger', 'Un flux IVAO est en erreur ; les données conservées peuvent être périmées.')
    : feeds.includes('stale') ? item('Périmé', 'warn', 'Au moins un flux est périmé.')
    : feeds.length && feeds.every(f => f === 'current') ? item('Connecté', 'ok', 'Flux IVAO récents ; aucun ATIS n’est déclaré écouté.')
    : item('En attente', 'warn', 'Tous les flux ne sont pas encore disponibles.');
  let lighting = !lights.length ? item('Non configuré', '', 'Facultatif ; aucun éclairage configuré.')
    : Object.keys(runtime?.errors || {}).length || Object.keys(runtime?.controller_errors || {}).length ? item('Erreur', 'danger', 'Un pilote ou contrôleur signale une erreur.')
    : runtime?.suspended ? item('Suspendu', 'warn', 'Règles d’éclairage suspendues.')
    : lights.every(d => d.driver === 'mock') ? item('Démonstration', 'sim', 'Pilotes d’éclairage simulés uniquement.')
    : item('Configuré', '', 'Règles actives ; connexion des appareils non confirmée par ce statut.');
  if (!demo && simulator.kind !== 'ok') blockers.push('Simulateur : ' + simulator.detail);
  if (!demo && bridge.kind !== 'ok') blockers.push('AI Bridge : ' + bridge.detail);
  if (demo) warnings.push('Démonstration active : aucune préparation de vol réel ne peut être confirmée.');
  if (!plan.available || simbrief.kind !== 'ok') warnings.push('SimBrief : ' + simbrief.detail + ' Le plan reste facultatif pour la télémétrie.');
  if (ivao.kind !== 'ok') warnings.push('IVAO : ' + ivao.detail);
  if (lighting.kind !== 'ok') warnings.push('Éclairage : ' + lighting.detail);
  if (counts.unavailable) warnings.push(counts.unavailable + ' variable(s) indisponible(s) ; consulter Variables IA.');
  if (lost || !s) {
    for (let entry of [simulator, bridge, simbrief, ivao, lighting])
      Object.assign(entry, item('Indisponible', 'warn', 'Connexion à Glareshield interrompue ou état non reçu.'));
    blockers.unshift('Connexion à Glareshield indisponible : les états ne sont pas confirmés.');
  }
  return { simulator, bridge, simbrief, ivao, lighting, blockers, warnings, demo };
}
function currentPreparation() { return preparationStatus(ai.status, state, config, connectionLost); }
function updatePreparationFoot() {
  let status = currentPreparation();
  $('#connectionNotice').hidden = !connectionLost;
  for (let [key, text, dot] of [['simulator', 'connection', 'simDot'], ['lighting', 'rulesState', 'rulesDot'], ['ivao', 'ivaoState', 'ivaoDot']]) {
    let entry = status[key];
    $('#' + text).textContent = { simulator: 'Simulateur', lighting: 'Éclairage', ivao: 'IVAO' }[key] + ' · ' + entry.label;
    $('#' + dot).className = 'dot ' + entry.kind;
  }
}
async function importPlan() {
  message('Récupération du dernier OFP…');
  try {
    await api('ai/simbrief/refresh', 'POST', {});
    message('OFP importé.');
  } finally {
    // Refresh even on failure: the old OFP must not look like a successful import.
    await reloadAI();
  }
}
function preparationView(view) {
  let status = currentPreparation();
  let intro = sectionHead(view, 'Préparer le vol', 'Vérifier les sources, importer le plan prévu et préparer le contexte de l’assistant.');
  intro.append(badge(status.demo ? 'Démonstration' : 'Préparation', status.demo ? 'sim' : 'accent'));
  let grid = el('div', null, { className: 'preparation-grid' });
  view.append(grid);
  for (let [key, title, destination] of [
    ['simulator', 'Simulateur', 'Variables IA'], ['bridge', 'AI Bridge', 'Variables IA'],
    ['simbrief', 'SimBrief', 'Plan de vol'], ['ivao', 'IVAO', 'Réseau IVAO'],
    ['lighting', 'Éclairage', 'Contrôleurs'],
  ]) {
    let entry = status[key], c = card(grid, title, entry.detail, badge(entry.label, entry.kind)), bar = cardActions(c);
    action('Ouvrir ' + destination, () => navigate(destination), bar, 'small ghost');
    if (key === 'simbrief')
      action('Importer depuis SimBrief', importPlan, bar, 'small primary', 'refresh').disabled = !ai.status?.simbrief_configured;
  }
  let exports = card(grid, 'Export IA', 'Briefing, point en vol ou JSON complet ; données et déclarations restent distinctes.'), bar = cardActions(exports);
  action('Copier le briefing', () => copyForChat('briefing'), bar, 'small primary', 'copy');
  action('Tous les exports', () => navigate('Export IA'), bar, 'small');
  let split = el('div', null, { className: 'split preparation' }), left = el('div', null, { className: 'stack' }), right = el('div', null, { className: 'stack' });
  split.append(left, right); view.append(split);
  planSummary(left, ai.plan?.plan);
  if (ai.plan?.plan?.route) left.lastChild.append(el('div', ai.plan.plan.route, { className: 'route' }));
  notesCard(right);
  let readiness = card(view, 'Points à vérifier', 'Les intégrations facultatives ne sont pas des prérequis au suivi.');
  for (let [title, entries] of [['Prérequis au suivi réel', status.blockers], ['Avertissements facultatifs', status.warnings]]) {
    readiness.append(el('h4', title));
    if (!entries.length) readiness.append(el('p', 'Aucun manque détecté.'));
    else {
      let list = el('ul', null);
      entries.forEach(text => list.append(el('li', text)));
      readiness.append(list);
    }
  }
  readiness.append(el('p', 'Même identifiant OFP : cases conservées, corrections signalées. Nouvel identifiant : suivi précédent archivé et nouvelles cases vides. Sans identifiant, le vol, les aérodromes et l’heure de départ prévue définissent le suivi. Démonstration et SimConnect restent séparés.', { id: 'startExplanation', className: 'muted' }));
  for (let text of ai.session?.warnings || []) readiness.append(el('p', text, { className: 'banner warn' }));
  let start = action(ai.session?.session ? 'Ouvrir le suivi du vol' : 'Démarrer le suivi du vol', async () => {
    if (!ai.session?.session) await sessionAction('start');
    navigate('Vol');
  }, cardActions(readiness), 'primary', 'play');
  start.disabled = connectionLost || (!ai.session?.session && (ai.session?.storage_blocked || status.blockers.length > 0));
  start.setAttribute('aria-describedby', 'startExplanation');
  action('Voir le mode Vol', () => navigate('Vol'), cardActions(readiness), 'small');
}
// Vol: one screen per stage. The service decides the stage and what matters; this only draws it.
let flightPreview = null;
let flightEditing = null;
let flightPointerDown = false;
if (typeof document !== 'undefined') {
  document.addEventListener('pointerdown', () => { flightPointerDown = true; });
  document.addEventListener('pointerup', () => { flightPointerDown = false; });
  document.addEventListener('pointercancel', () => { flightPointerDown = false; });
}
const FLIGHT_STATUS = {
  live: ['Données en direct', 'ok'], demo: ['Démonstration', 'sim'], paused: ['Simulateur en pause', 'warn'],
  disconnected: ['Simulateur déconnecté', 'warn'], stale: ['Données périmées', 'warn'],
};
const fmt = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString('fr-FR', { maximumFractionDigits: digits });
function flightNode(tag, className, text = null) { return el(tag, text, className ? { className } : {}); }
function flightKey(node, key) { node.dataset.key = key; return node; }
function flightPill(text, tone = '') { return flightNode('span', 'fl-pill ' + tone, text); }
function flightKv(label, value, extra = null) {
  let kv = flightNode('div', 'fl-kv');
  kv.append(flightNode('span', null, label), flightNode('b', null, value));
  if (extra) kv.append(flightNode('small', null, extra));
  return kv;
}
function flightPanel(parent, title) {
  let panel = flightNode('section', 'fl-panel');
  if (title) panel.append(flightNode('h2', 'fl-h2', title));
  parent.append(panel);
  return panel;
}

function flightBar(cockpit) {
  let h = cockpit.header, bar = flightNode('div', 'fl-bar'), ident = flightNode('div', 'fl-ident');
  ident.append(flightNode('div', 'fl-cs', h.callsign || '<indicatif>'));
  let route = flightNode('div', 'fl-route');
  route.append(flightNode('b', null, h.origin || '<départ>'), ' ' + (h.origin_name || '') + ' → ',
    flightNode('b', null, h.destination || '<arrivée>'), ' ' + (h.destination_name || '') + (h.aircraft ? ' · ' + h.aircraft : ''));
  ident.append(route);
  bar.append(ident, flightKv('Heure UTC', new Date(h.utc * 1000).toISOString().slice(11, 19)));
  if (h.eta) bar.append(flightKv('Arrivée prévue', h.eta));
  if (h.ofp_age_min != null) bar.append(flightKv('OFP', h.ofp_age_min + ' min' + (h.airac ? ' · AIRAC ' + h.airac : '')));
  bar.append(flightNode('div', 'fl-spacer'));
  let [label, tone] = FLIGHT_STATUS[h.status] || FLIGHT_STATUS.stale;
  if (connectionLost) [label, tone] = ['Connexion à Glareshield perdue', 'bad'];
  bar.append(flightPill(label, tone));
  return bar;
}

function flightTrack(cockpit) {
  let nav = flightNode('nav', 'fl-track');
  nav.setAttribute('aria-label', 'Phases du vol : cliquer pour consulter une autre phase');
  for (let leg of cockpit.track) {
    let button = flightKey(el('button', null, { type: 'button', className: 'fl-leg ' + leg.state }), 'leg-' + leg.id);
    if (leg.state === 'current') button.setAttribute('aria-current', 'step');
    if (flightPreview === leg.id) button.classList.add('preview');
    let bar = flightNode('span', 'fl-legbar'), fill = flightNode('i');
    fill.style.width = leg.progress + '%';
    bar.append(fill);
    button.append(bar, flightNode('span', 'fl-legname', leg.label), flightNode('span', 'fl-legsub', leg.sub));
    button.title = leg.done + '/' + leg.total + ' étapes cochées';
    button.onclick = () => { flightPreview = leg.state === 'current' ? null : leg.id; updateFlightView(true); };
    nav.append(button);
  }
  return nav;
}

function flightNow(cockpit) {
  let now = cockpit.now, panel = flightNode('section', 'fl-panel fl-now');
  panel.append(flightNode('div', 'fl-eyebrow', 'Maintenant' + (cockpit.stage_label ? ' · ' + cockpit.stage_label : '')),
    flightNode('div', 'fl-big', now.title));
  if (now.why) panel.append(flightNode('div', 'fl-why', now.why));
  if (now.pills.length) {
    let pills = flightNode('div', 'fl-pills');
    now.pills.forEach(p => pills.append(flightPill(p.text, p.tone)));
    panel.append(pills);
  }
  return panel;
}

function flightValue(value) {
  if (flightEditing === value.key) {
    let input = flightKey(el('input', null, { type: 'text', className: 'fl-edit', value: value.open ? '' : value.text,
      placeholder: value.label, maxLength: 80 }), 'edit-' + value.key);
    input.setAttribute('aria-label', 'Saisir : ' + value.label);
    let done = false;
    const save = async keep => {
      if (done) return;
      done = true;
      flightEditing = null;
      if (keep && input.value.trim() !== (value.open ? '' : value.text)) {
        try { await sessionAction('values/' + value.key, 'PUT', { value: input.value.trim() || null }); return; }
        catch (e) { message(e.message, true); }
      }
      updateFlightView(true);
    };
    input.onkeydown = e => {
      if (e.key === 'Enter') { e.preventDefault(); save(true); }
      if (e.key === 'Escape') { e.preventDefault(); save(false); }
    };
    input.onblur = () => save(true);
    return input;
  }
  let chip = flightKey(el('button', null, { type: 'button', className: 'fl-val' + (value.open ? ' open' : '') }), 'val-' + value.key);
  chip.append(value.text);
  if (value.source) chip.append(flightNode('small', 'fl-src', value.source));
  chip.title = (value.open ? 'Inconnu : cliquer pour saisir ' : 'Cliquer pour corriger ') + value.label;
  chip.onclick = e => { e.preventDefault(); flightEditing = value.key; updateFlightView(true); };
  return chip;
}

function flightGroup(group) {
  let section = flightNode('section', 'fl-group'), head = flightNode('div', 'fl-ghead');
  let done = group.steps.filter(s => s.checked).length;
  head.append(flightNode('h2', 'fl-h2', group.label), flightNode('span', 'fl-count', done + '/' + group.steps.length));
  let items = flightNode('div', 'fl-items');
  for (let step of group.steps) {
    let row = flightNode('label', 'fl-item' + (step.checked ? ' done' : '')),
      input = flightKey(el('input', null, { type: 'checkbox', checked: step.checked }), 'step-' + step.id),
      label = flightNode('span', 'fl-lbl', step.label), right = flightNode('span', 'fl-right');
    input.setAttribute('aria-label', step.label);
    if (step.detected) label.append(flightNode('small', null, 'Détecté par le simulateur'));
    input.onchange = async () => {
      input.disabled = true;
      try { await sessionAction('steps/' + step.id, 'PUT', { checked: input.checked }); }
      catch (e) { input.checked = step.checked; input.disabled = false; message(e.message, true); }
    };
    step.values.forEach(v => right.append(flightValue(v)));
    row.append(input, label, right);
    items.append(row);
  }
  section.append(head, items);
  return section;
}

function flightRadio(cockpit) {
  let section = flightNode('section', 'fl-group'), head = flightNode('div', 'fl-ghead'), items = flightNode('div', 'fl-items');
  head.append(flightNode('h2', 'fl-h2', 'Radio'), flightNode('span', 'fl-when', 'Messages prêts · copier n’émet rien'));
  for (let r of cockpit.radio) {
    let box = flightNode('div', 'fl-radio'), top = flightNode('div', 'fl-radiotop');
    top.append(flightNode('span', 'fl-trg', r.trigger));
    if (r.station) top.append(flightPill(r.station + (r.frequency ? ' · ' + r.frequency : ''), 'ivao'));
    if (r.mode === 'texte') top.append(flightPill('texte'));
    top.append(flightNode('span', 'fl-spacer'));
    let copy = flightKey(el('button', 'Copier', { type: 'button', className: 'small' }), 'copy-' + r.id);
    copy.onclick = async () => {
      try { await copyText(r.text); message('Copié.'); }
      catch (e) { message('Sélectionnez le texte pour copier.', true); }
    };
    top.append(copy);
    box.append(top, flightNode('pre', 'fl-msg' + (r.mode === 'texte' ? ' txt' : ''), r.text));
    items.append(box);
  }
  section.append(head, items);
  return section;
}

function flightSituation(cockpit) {
  let col = flightNode('aside', 'fl-col'), s = cockpit.situation;
  col.setAttribute('aria-label', 'Situation du vol');
  let panel = flightPanel(col, 'Situation'), tele = flightNode('div', 'fl-tele');
  const signed = v => v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(Math.round(v / 50) * 50));
  tele.append(flightKv('Altitude', s.altitude_ft == null ? '—' : fmt(Math.round(s.altitude_ft / 10) * 10) + ' ft'),
    flightKv('Vitesse sol', s.ground_speed_kt == null ? '—' : fmt(s.ground_speed_kt) + ' kt'),
    flightKv('Vario', s.vertical_speed_fpm == null ? '—' : signed(s.vertical_speed_fpm) + ' fpm'),
    flightKv('Carburant', s.fuel_kg == null ? '—' : fmt(Math.round(s.fuel_kg / 10) * 10) + ' kg',
      s.fuel_vs_plan_kg == null ? null : (s.fuel_vs_plan_kg >= 0 ? '+' : '−') + fmt(Math.abs(s.fuel_vs_plan_kg)) + ' kg vs plan'));
  if (s.distance_total_nm) {
    let gauge = flightNode('div', 'fl-gauge'), row = flightNode('div', 'fl-gaugerow'), rail = flightNode('div', 'fl-rail'), fill = flightNode('i');
    row.append(flightNode('span', null, 'Distance parcourue'), flightNode('b', null, fmt(s.distance_flown_nm) + ' / ' + fmt(s.distance_total_nm) + ' NM'));
    fill.style.width = Math.min(100, 100 * (s.distance_flown_nm || 0) / s.distance_total_nm) + '%';
    rail.append(fill);
    if (s.tod_ratio != null) { let tod = flightNode('u'); tod.style.left = (100 * s.tod_ratio) + '%'; tod.title = 'TOD'; rail.append(tod); }
    let ends = flightNode('div', 'fl-gaugerow');
    ends.append(flightNode('span', null, 'Départ'), ...(s.tod_ratio != null ? [flightNode('span', null, 'TOD')] : []), flightNode('span', null, 'Arrivée'));
    gauge.append(row, rail, ends);
    tele.append(gauge);
  }
  panel.append(tele);
  if (cockpit.atc.length) {
    let atc = flightPanel(col, 'ATC en ligne');
    for (let a of cockpit.atc) {
      let row = flightNode('div', 'fl-atcrow');
      row.append(flightNode('span', 'fl-atccs', a.callsign), flightNode('span', 'fl-freq', a.frequency || '—'), flightNode('span', 'fl-note', a.note));
      atc.append(row);
    }
  }
  if (cockpit.atis) {
    let a = cockpit.atis, atis = flightPanel(col, (a.letter ? 'ATIS ' + a.airport + ' · ' + a.letter : a.source + ' · ' + a.airport));
    if (a.changed) atis.append(flightNode('div', 'fl-change', a.changed));
    let text = flightNode('div', 'fl-atis');
    a.lines.forEach((line, i) => { if (i) text.append(el('br')); text.append(line); });
    atis.append(text);
    if (a.age_min != null) atis.append(flightNode('div', 'fl-note', 'Publié il y a ' + a.age_min + ' min · lu ≠ écouté'));
  }
  if (cockpit.upcoming.length) {
    let next = flightPanel(col, 'À venir'), list = flightNode('div', 'fl-upc');
    for (let u of cockpit.upcoming) {
      let row = flightNode('div', 'fl-u');
      row.append(flightNode('span', null, u.at), flightNode('div', null, u.text));
      list.append(row);
    }
    next.append(list);
  }
  return col;
}

function flightDashboard(data) {
  let cockpit = data.cockpit, root = flightNode('div', 'fl');
  root.id = 'flightDashboard';
  root.dataset.session = data.session.id;
  for (let text of data.warnings || []) root.append(el('p', text, { className: 'banner warn' }));
  root.append(flightBar(cockpit), flightTrack(cockpit));
  let shown = flightPreview || cockpit.phase || 'preflight', label = data.phases.find(p => p.id === shown)?.label;
  if (flightPreview) {
    let banner = flightNode('div', 'fl-preview');
    banner.append(flightNode('span', null, 'Aperçu de la phase ' + label + ' · le suivi reste en ' + (cockpit.stage_label || 'détection') + '.'));
    let bar = flightNode('span', 'fl-previewactions');
    action('Je suis en ' + label, async () => { await sessionAction('phase', 'PUT', { phase: shown }); flightPreview = null; updateFlightView(true); }, bar, 'small');
    action('Revenir à la phase en cours', () => { flightPreview = null; updateFlightView(true); }, bar, 'small ghost');
    banner.append(bar);
    root.append(banner);
  }
  let grid = flightNode('div', 'fl-grid'), left = flightNode('div', 'fl-col');
  left.append(flightNow(cockpit));
  cockpit.groups.filter(g => g.phase === shown).forEach(g => left.append(flightGroup(g)));
  if (!flightPreview && cockpit.radio.length) left.append(flightRadio(cockpit));
  grid.append(left, flightSituation(cockpit));
  root.append(grid);
  let foot = flightNode('div', 'fl-foot');
  foot.append(flightNode('span', 'fl-note', cockpit.mode === 'manual'
    ? 'Phase corrigée à la main ; le suivi automatique reprend à partir d’elle.'
    : 'Phase détectée automatiquement. Cliquer une phase du parcours pour la consulter ou la corriger.'));
  foot.append(flightNode('span', 'fl-spacer'));
  action('Terminer le suivi', () => sessionAction('end'), foot, 'small ghost');
  root.append(foot);
  return root;
}

function flightPendingView(view) {
  let data = ai.session, session = data?.session;
  if (session?.status === 'active' && !data.storage_blocked && data.cockpit) {
    view.append(flightDashboard(data));
    return;
  }
  let c = card(view, 'Suivi du vol', data?.universe === 'demo' ? 'Démonstration' : 'SimConnect · lecture seule du cockpit');
  for (let text of data?.warnings || []) c.append(el('p', text, { className: 'banner warn' }));
  c.append(el('p', session ? 'Suivi terminé. Les cases cochées et les valeurs saisies sont conservées.'
    : 'Aucun suivi démarré. La phase sera détectée automatiquement, même si le vol est déjà en cours.'));
  let bar = cardActions(c);
  if (!session) action('Démarrer le suivi du vol', () => sessionAction('start'), bar, 'primary').disabled = data?.storage_blocked || connectionLost;
  else action('Reprendre le suivi', () => sessionAction('resume'), bar, 'primary');
  action('Retour à l’initialisation', () => navigate('Initialisation'), bar);
  action('Nouveau suivi vide', async () => {
    if (confirm('Ouvrir un suivi vide ? Le suivi précédent reste archivé sous local/.')) await sessionAction('reset');
  }, bar, 'danger');
}

function updateFlightView(force = false) {
  if (tab !== 'Vol') return;
  const data = ai.session, root = $('#flightDashboard');
  if (!force && (flightPointerDown || flightEditing)) return;
  const active = data?.session?.status === 'active' && !data.storage_blocked && data.cockpit;
  if (!root || !active || root.dataset.session !== data.session.id) {
    if (!force && isEditing() && !root) return;
    flightPreview = null;
    flightEditing = null;
    render();
    return;
  }
  // Rebuild, then put focus back on the same control so keyboard use survives each refresh.
  const key = document.activeElement?.closest?.('[data-key]')?.dataset.key;
  const next = flightDashboard(data);
  root.replaceWith(next);
  const target = key && next.querySelector('[data-key="' + key + '"]');
  if (target) target.focus({ preventScroll: true });
  if (flightEditing) {
    const input = next.querySelector('.fl-edit');
    if (input) { input.focus({ preventScroll: true }); input.select(); }
  }
}

async function sessionAction(path, method = 'POST', values = {}) {
  let current = ai.session;
  const mounted = $('#flightDashboard');
  if (tab === 'Vol' && mounted && mounted.dataset.session !== current?.session?.id) {
    render(); throw Error('Le suivi a changé : vérifier le nouveau vol avant de réessayer.');
  }
  try {
    ai.session = await api('ai/session/' + path, method, { session_id: current?.session?.id || null, universe: current.universe, ...values });
    if (tab === 'Vol' && mounted && current?.session?.id === ai.session?.session?.id && ai.session?.session?.status === 'active') updateFlightView(true);
    else render();
  } catch (e) {
    // A stale tab must not apply a gesture to a newly opened flight.
    ai.session = await api('ai/session');
    render();
    throw e;
  }
}

function settingsHome(view) {
  for (let [category, names] of SETTINGS) {
    let c = card(view, category), bar = cardActions(c);
    for (let name of names) action(name, () => navigate(name), bar, 'small');
  }
}
function displayView(view) {
  let c = card(view, 'Affichage', 'Préférences conservées dans local/display.json ; application immédiate.'),
    theme = field(c, 'Thème', display.theme, 'text', Object.keys(DISPLAY_THEMES)),
    size = field(c, 'Taille du texte', display.text_size, 'text', ['standard', 'large', 'extra']);
  for (let option of c.querySelectorAll('select')[0].options) option.textContent = DISPLAY_THEMES[option.value];
  for (let option of c.querySelectorAll('select')[1].options) option.textContent = { standard: 'Standard', large: 'Grande', extra: 'Très grande' }[option.value];
  action('Appliquer l’affichage', async () => {
    await saveDisplay({ theme: theme(), text_size: size() });
    message('Affichage enregistré.');
  }, cardActions(c), 'primary');
}
function copilotSettingsView(view) {
  let c = card(view, 'Copilote A320', 'Navigation et préparation du vol');
  c.append(el('p', 'La phase est détectée en continu depuis le simulateur ; un clic sur le parcours la corrige. Cases cochées et valeurs saisies restent sous local/copilot/.'));
  action('Variables et démonstration', () => navigate('Variables IA'), cardActions(c));
}
function applicationView(view) {
  let c = card(view, 'Application locale', 'Les configurations, plans, notes et exports restent sous local/.');
  c.append(el('p', 'Les journaux et les réglages du moteur restent accessibles dans leurs pages dédiées.'));
  let bar = cardActions(c);
  action('Journal', () => navigate('Journal'), bar);
  action('Moteur d’éclairage', () => navigate('Moteur d’éclairage'), bar);
}
for (let [name, renderer, iconName, subtitle] of [
  ['Initialisation', preparationView, 'plan', 'Sources et préparation du vol'],
  ['Vol', flightPendingView, 'plane', 'Suivi du vol en cours'],
  ['Réglages', settingsHome, 'settings', 'Copilote, affichage, intégrations, éclairage et application'],
  ['Affichage', displayView, 'settings', 'Thème et lisibilité'],
  ['Copilote', copilotSettingsView, 'plane', 'Préparation du copilote A320'],
  ['Application', applicationView, 'settings', 'Données locales et diagnostic'],
]) VIEWS[name] = { render: renderer, icon: iconName, subtitle };
VIEWS['Initialisation'].live = true;
VIEWS['Initialisation'].ready = () => ai.status && ai.settings && ai.plan;
VIEWS['Initialisation'].load = () => loadAI(true);
VIEWS['Vol'].live = true;
VIEWS['Vol'].update = updateFlightView;
VIEWS['Vol'].ready = () => ai.session;
VIEWS['Vol'].load = () => loadAI(true);
