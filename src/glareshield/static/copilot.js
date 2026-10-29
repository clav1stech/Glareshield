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
let phaseDraft = null;
let flightPointerDown = false;
if (typeof document !== 'undefined') {
  document.addEventListener('pointerdown', () => { flightPointerDown = true; });
  document.addEventListener('pointerup', () => { flightPointerDown = false; });
  document.addEventListener('pointercancel', () => { flightPointerDown = false; });
}
// Live islands update text and checked state; controls and their closures stay mounted.
function flightValue(value) {
  if (value?.value == null) return value?.placeholder || '<…>';
  return (typeof value.value === 'boolean' ? (value.value ? 'Oui' : 'Non') :
    typeof value.value === 'number' ? value.value.toLocaleString('fr-FR', {maximumFractionDigits: 1}) : value.value) +
    (value.unit ? ' ' + value.unit : '');
}
function flightSource(value) {
  return (value?.source || 'Source inconnue') + ' · ' +
    ({planned:'Prévu', declared:'Déclaré', published:'Publié', observed:'Simulateur', procedure:'Procédure'}[value?.nature] || 'Calculé') +
    ' · ' + ({available:'Disponible', observed:'Observé', simulated:'Démonstration', stale:'Périmé', unavailable:'Indisponible', derived:'Calculé'}[value?.status] || 'Indisponible') +
    (value?.age_s == null ? '' : ' · ' + Math.floor(value.age_s) + ' s') +
    (value?.reference && value.reference !== value.source ? ' · ' + value.reference : '');
}
function flightPhaseEvidence(target, phase) {
  target.replaceChildren();
  if (phase?.suspended) target.append(el('p', 'Transitions automatiques suspendues.', {className:'banner warn'}));
  if (phase?.effective?.status === 'stale') target.append(el('p', 'Dernière phase connue · données périmées.', {className:'banner warn'}));
  for (let text of phase?.evidence || []) target.append(el('p', text, {className:'muted'}));
  for (let text of phase?.uncertainty || []) target.append(el('p', text, {className:'banner warn'}));
  if (phase?.automatic?.method) target.append(el('p', phase.automatic.method, {className:'muted'}));
  if (phase?.next_trigger) target.append(el('p', 'Prochain déclencheur : ' + phase.next_trigger.label +
    (phase.next_trigger.elapsed_s ? ' · confirmation ' + Math.floor(phase.next_trigger.elapsed_s) + '/' + phase.next_trigger.hold_s + ' s' : '')));
}
function flightDashboard(view, data) {
  let root = el('div', null, {id:'flightDashboard'});
  root.dataset.session = data.session.id;
  root.dataset.activePhase = data.phase?.effective?.value || '';
  view.append(root);
  root.append(el('div', null, {id:'flightBanner', className:'flight-banner'}));
  root.append(el('small', null, {id:'flightBannerSource', className:'muted'}));
  let phases = el('nav', null, {className:'flight-phases', 'aria-label':'Progression des six phases'});
  root.append(phases);
  for (let p of data.phases) {
    let button = action(p.label, () => sessionAction('phase', 'PUT', {phase:p.id}), phases, 'ghost');
    button.dataset.phase = p.id;
    button.title = 'Correction manuelle : ' + p.label + ' (ne coche aucune case)';
    button.setAttribute('aria-label', 'Corriger la phase : ' + p.label);
  }
  let columns = el('div', null, {className:'flight-columns'}), left = el('div', null, {className:'stack flight-actions'}), right = el('aside', null, {className:'stack flight-situation', 'aria-label':'Situation du vol'});
  columns.append(left, right); root.append(columns);
  let now = card(left, 'Maintenant', 'Priorité du profil dans la phase courante ; déclencheur à confirmer par le pilote.');
  now.id = 'flightNow'; now.classList.add('flight-now');
  now.append(el('h3', null, {id:'flightNowTitle'}), el('p', null, {id:'flightNowContext'}), el('p', null, {id:'flightNowValue'}), el('small', null, {id:'flightNowSource', className:'muted'}));
  for (let p of data.phases) {
    let details = el('details', null), summary = el('summary', p.label);
    details.open = (data.phase?.effective?.value || 'preflight') === p.id;
    details.dataset.phaseGroup = p.id;
    details.append(summary); left.append(details);
    for (let group of data.groups.filter(g => g.phase === p.id)) {
      let groupCard = card(details, group.label), count = el('p', null, {className:'muted'});
      count.dataset.group = group.id; groupCard.append(count);
      for (let step of group.steps) {
        let row = el('div', null, {className:'flight-step'}), label = el('label', null, {className:'check'}), input = el('input', null, {type:'checkbox', checked:step.checked});
        row.dataset.step = step.id;
        input.setAttribute('aria-label', step.label);
        input.onchange = async () => {
          input.disabled = true;
          try { await sessionAction('steps/' + step.id, 'PUT', {checked:input.checked}); }
          catch (e) { input.checked = step.checked; message(e.message, true); }
          finally { input.disabled = false; }
        };
        label.append(input, el('span', step.label)); row.append(label);
        row.append(el('small', null, {className:'step-status muted'}));
        for (let id of step.expected) {
          let value = el('div', null, {className:'step-value'});
          value.dataset.value = id;
          value.append(el('p'), el('small', null, {className:'muted'})); row.append(value);
        }
        row.append(el('small', 'Contexte : ' + step.trigger, {className:'muted'}));
        groupCard.append(row);
      }
    }
  }
  let telemetry = card(right, 'Situation', 'Mesures du simulateur · lecture seule');
  for (let key of ['altitude_indicated','altitude_msl','ias','ground_speed','vertical_speed','fuel_total']) {
    let row = el('div', null, {className:'flight-metric'}); row.dataset.metric = key;
    row.append(el('span'), el('strong'), el('small', null, {className:'muted'})); telemetry.append(row);
  }
  let route = card(right, 'Route prévue', 'Géométrie OFP et position ; un direct peut fausser cet avancement.');
  route.append(el('div', null, {id:'flightRoute'}));
  right.append(el('div', null, {id:'flightNetwork'}));
  let events = card(right, 'Prochains événements', 'Déclencheur de phase, prochains points et événements réseau disponibles.');
  events.append(el('div', null, {id:'flightEvents'}));
  let messages = card(left, 'Rappels', 'Un rappel reste présent jusqu’à acquittement ; les actions de procédure restent séparées.');
  messages.append(el('p', null, {id:'flightReminderStatus', className:'muted'}), el('div', null, {id:'flightReminders'}));
  let radio = card(left, 'Messages radio', 'Lecture et copie uniquement ; aucun envoi automatique.');
  radio.append(el('div', null, {id:'flightRadio'}));
  updateFlightView();
}
function updateFlightView() {
  if (tab !== 'Vol') return;
  const data = ai.session, flight = data?.flight, root = $('#flightDashboard');
  if (!root || root.dataset.session !== data?.session?.id || data?.session?.status !== 'active') {
    if (root) {
      $('#flightBanner').textContent = 'Le suivi a changé : terminer la saisie puis actualiser avant toute action.';
      root.querySelectorAll('button,input').forEach(n => { n.disabled = true; });
    }
    if (!isEditing() && !flightPointerDown) render();
    return;
  }
  if (!flight) return;
  if (flightPointerDown) return;
  let active = data.phase?.effective?.value;
  if (root.dataset.activePhase !== active) {
    let section = root.querySelector('[data-phase-group="' + active + '"]');
    if (section) section.open = true;
    root.dataset.activePhase = active || '';
  }
  const set = (id, text) => { let node = $('#' + id); if (node) node.textContent = text; };
  const v = id => flight.values[id];
  set('flightBanner', flightValue(v('callsign')) + ' · ' + flightValue(v('origin')) + ' → ' + flightValue(v('destination')) +
    ' · OFP prévu · ' + (flight.plan_age_min == null ? '<âge OFP>' : flight.plan_age_min + ' min') +
    ' · ' + new Date(flight.utc * 1000).toISOString().slice(11,19) + ' UTC' +
    (data.universe === 'demo' ? ' · DÉMONSTRATION' : '') + (flight.paused ? ' · EN PAUSE' : '') +
    (!flight.connected ? ' · DÉCONNECTÉ' : '') + (flight.stale ? ' · DONNÉES PÉRIMÉES' : '') +
    (connectionLost ? ' · CONNEXION À GLARESHIELD PERDUE' : ''));
  set('flightBannerSource', 'Source du trajet : OFP prévu · ' + (flight.plan?.aircraft?.icao || '<appareil>') +
    ' · Arrivée prévue : ' + (flight.plan?.times?.scheduled_in_utc || '<…>') + ' · Horloge UTC : serveur Glareshield');
  for (let p of data.phases) {
    let steps = data.groups.filter(g => g.phase === p.id).flatMap(g => g.steps), button = root.querySelector('[data-phase="' + p.id + '"]');
    button.textContent = p.label + ' · ' + steps.filter(s => s.checked).length + '/' + steps.length;
    if (p.id === active) button.setAttribute('aria-current', 'step'); else button.removeAttribute('aria-current');
  }
  const current = flight.now;
  set('flightNowTitle', current?.label || (active ? 'Actions de cette phase terminées' : 'Phase à confirmer'));
  set('flightNowContext', (current ? current.trigger + ' · priorité ' + current.priority : 'Les autres phases conservent leurs cases.') +
    ' · Prochain déclencheur : ' + (data.phase?.next_trigger?.label || '<…>'));
  set('flightNowValue', current?.kind === 'reminder' ? 'Rappel maintenu jusqu’à acquittement.' : current ? current.expected.map(id => v(id).label + ' : ' + flightValue(v(id))).join(' · ') : '<…>');
  set('flightNowSource', current?.kind === 'reminder' ? 'Source : ' + current.source + ' · ' + current.reference : current ? current.expected.map(id => flightSource(v(id))).join(' · ') : 'Source : progression du suivi');
  for (let group of data.groups) {
    root.querySelector('[data-group="' + group.id + '"]').textContent = group.steps.filter(s => s.checked).length + '/' + group.steps.length + ' terminées · ' + ({mcdu:'MCDU',fcu:'FCU',checklist:'Checklist'}[group.kind]);
    for (let step of group.steps) {
      let row = root.querySelector('[data-step="' + step.id + '"]'), input = row.querySelector('input');
      if (!input.disabled) input.checked = step.checked;
      row.querySelector('.step-status').textContent = ({manual:'Manuel',detected:'Détecté',pending:'À confirmer'}[step.provenance]) +
        (step.conflict ? ' · Observation contradictoire ; geste manuel prioritaire.' : '') +
        (step.detected ? ' · ' + step.detected.reference + ' · ' + new Date(step.detected.recorded_at * 1000).toLocaleString('fr-FR') + (step.detection_current ? '' : ' · historique à reconfirmer') : '') +
        (step.observation ? ' · ' + (step.observation.origin === 'scenario' ? 'Démonstration' : 'SimConnect') + ' · ' + step.observation.reason +
          (step.observation.observed_at != null ? ' · mesure du ' + new Date(step.observation.observed_at * 1000).toLocaleString('fr-FR') : '') : '');
      for (let cell of row.querySelectorAll('[data-value]')) {
        let value = v(cell.dataset.value);
        cell.firstChild.textContent = value.label + ' : ' + flightValue(value);
        cell.lastChild.textContent = flightSource(value);
      }
    }
  }
  for (let row of root.querySelectorAll('[data-metric]')) {
    let value = flight.telemetry[row.dataset.metric];
    row.children[0].textContent = value?.label || row.dataset.metric;
    row.children[1].textContent = flightValue(value);
    row.children[2].textContent = flightSource(value);
  }
  let route = flight.derived.route_progress, routeNode = $('#flightRoute');
  routeNode.textContent = route ? 'Prochain point : ' + route.next_waypoint + ' · reste ' + route.remaining_along_route_nm + ' NM · Source : position simulateur + OFP · Calculé. ' + route.method : '<avancement sur la route prévue> · Source : position simulateur + OFP indisponible';
  const reminderStatus = flight.reminder_status, tod = reminderStatus?.tod;
  routeNode.append(el('p', tod?.kind === 'supplied' ? 'TOD fourni : ' + new Date(tod.value * 1000).toISOString() + ' · ' + tod.reference + ' · ' + tod.notice : 'TOD MCDU : <…> · ' + (tod?.notice || 'Source indisponible ; aucune déduction.')));
  let network = $('#flightNetwork');
  if (!network.contains(document.activeElement) && !flightPointerDown) {
    network.replaceChildren(); flightNetworkView(network, data.network);
  }
  let events = $('#flightEvents'); events.replaceChildren();
  events.append(el('p', 'Prochain déclencheur : ' + (data.phase?.next_trigger?.label || '<…>') + ' · Source : moteur de phase'));
  for (let point of route?.upcoming || []) events.append(el('p', point.ident + ' · ' + point.distance_nm + ' NM · Source : OFP + position · Calculé'));
  for (let event of reminderStatus?.upcoming?.filter(e => !e.fired && e.eligible) || []) events.append(el('p', event.label + ' · ' + event.trigger + (event.uncertainty.length ? ' · ' + event.uncertainty.join(' ') : '')));
  set('flightReminderStatus', (reminderStatus?.suspended ? 'Déclenchements suspendus ; rappels historiques conservés. ' : '') +
    (reminderStatus?.critical ? 'Phase critique : rappels prioritaires seulement. ' : '') +
    (reminderStatus?.pending_count || 0) + ' rappel(s) à acquitter' + (reminderStatus?.deferred_count ? ' · ' + reminderStatus.deferred_count + ' différé(s)' : '') +
    (reminderStatus?.gap ? ' · Flux d’événements incomplet ; aucun événement manquant supposé.' : ''));
  updateReminders($('#flightReminders'), flight.reminders);
  updateRadio($('#flightRadio'), flight.radio);
  let label = data.phases.find(p => p.id === active)?.label || 'Non confirmée';
  const substates = {taxi:'Roulage',takeoff:'Décollage',approach:'Approche',landing:'Atterrissage',parking:'Parking',go_around:'Remise des gaz'};
  set('flightPhase', label + ' · ' + (data.phase?.mode === 'manual' ? 'Déclarée par le pilote' : 'Calculée') + (data.phase?.substate ? ' · ' + substates[data.phase.substate] : ''));
  if ($('#flightPhaseEvidence')) flightPhaseEvidence($('#flightPhaseEvidence'), data.phase);
}
function updateReminders(target, reminders) {
  const ids = new Set(reminders.map(r => r.id));
  for (let row of [...target.children]) if (!ids.has(row.dataset.reminder)) row.remove();
  for (let [index, reminder] of reminders.entries()) {
    let row = target.querySelector('[data-reminder="' + reminder.id + '"]');
    if (!row) {
      row = el('article', null, {className:'flight-message'}); row.dataset.reminder = reminder.id;
      row.append(el('h3'), el('p'), el('small', null, {className:'muted'}));
      const acknowledge = action('Acquitter le rappel', () => sessionAction('reminders/' + reminder.id + '/acknowledge'), row, 'small');
      acknowledge.setAttribute('aria-label', 'Acquitter le rappel : ' + reminder.label);
      target.append(row);
    }
    row.querySelector('h3').textContent = reminder.label;
    row.querySelector('p').textContent = reminder.method;
    row.querySelector('small').textContent = reminder.source + ' · ' + reminder.reference + ' · détecté le ' + new Date(reminder.triggered_at * 1000).toLocaleString('fr-FR');
    if (target.children[index] !== row) target.insertBefore(row, target.children[index] || null);
  }
}
function updateRadio(target, entries) {
  const ids = new Set(entries.map(r => r.id));
  for (let row of [...target.children]) if (!ids.has(row.dataset.radio)) row.remove();
  for (let [index, entry] of entries.entries()) {
    let row = target.querySelector('[data-radio="' + entry.id + '"]');
    if (!row) {
      row = el('article', null, {className:'flight-message'}); row.dataset.radio = entry.id;
      row.append(el('h3'), el('p', null, {className:'radio-station'}), el('p', null, {className:'radio-trigger muted'}));
      for (let [kind, title] of [['voice','Pilote · voix'], ['readback','Collationnement après réception'], ['voice_alternate','Variante voix française · station inconnue'], ['readback_alternate','Variante collationnement français après réception'], ['unicom','Variante UNICOM · texte']]) {
        let block = el('div', null, {className:'radio-variant'}); block.dataset.variant = kind;
        block.append(el('strong', title), el('pre'), el('small', null, {className:'muted'}));
        const copyLabel = {voice:'la voix',readback:'le collationnement',voice_alternate:'la variante française',readback_alternate:'le collationnement français',unicom:'le texte UNICOM'}[kind];
        const button = action('Copier ' + copyLabel, async () => {
          let latest = ai.session?.flight?.radio?.find(r => r.id === entry.id)?.[kind];
          if (!latest) throw Error('Message indisponible : actualiser.');
          await copyText(latest);
          message('Message copié. Copier ne signifie pas émettre.');
        }, block, 'small');
        button.setAttribute('aria-label', 'Copier ' + copyLabel + ' : ' + entry.trigger.label);
        row.append(block);
      }
      let details = el('details', null); details.append(el('summary', 'Valeurs et sources'), el('div', null, {className:'radio-sources muted'})); row.append(details);
      target.append(row);
    }
    row.querySelector('h3').textContent = entry.trigger.label + ' · ' + ({ready:'Déclencheur confirmé',upcoming:'À venir',unknown:'Condition à confirmer'}[entry.trigger.status]);
    row.querySelector('.radio-station').textContent = (ai.session?.universe === 'demo' ? 'Démonstration · ' : '') + (entry.station.callsign || '<station>') + ' · ' +
      (entry.station.frequency_mhz == null ? '<fréquence>' : entry.station.frequency_mhz.toFixed(3) + ' MHz publiée') +
      ' · Voix ' + (entry.language === 'fr' ? 'française' : 'anglaise') + ' · ' + entry.station.notice;
    row.querySelector('.radio-trigger').textContent = entry.copy_notice;
    for (let [kind, text] of [['voice',entry.voice],['readback',entry.readback],['voice_alternate',entry.voice_alternate],['readback_alternate',entry.readback_alternate],['unicom',entry.unicom]]) {
      let block = row.querySelector('[data-variant="' + kind + '"]'); block.hidden = !text;
      block.querySelector('pre').textContent = text || '';
      block.querySelector('small').textContent = kind.startsWith('readback') ? entry.readback_notice : kind === 'unicom' ? entry.unicom_notice : entry.station.notice;
    }
    let sources = row.querySelector('.radio-sources'); sources.replaceChildren();
    for (let value of Object.values(entry.values)) sources.append(el('p', value.label + ' : ' + flightValue(value) + ' · ' + flightSource(value)));
    if (target.children[index] !== row) target.insertBefore(row, target.children[index] || null);
  }
}
function flightPendingView(view) {
  let data = ai.session, session = data?.session;
  let c = card(view, 'Suivi du vol', data?.universe === 'demo' ? 'Démonstration · suivi séparé de SimConnect' : 'SimConnect · lecture seule du cockpit');
  for (let text of data?.warnings || []) c.append(el('p', text, { className: 'banner warn' }));
  let bar = cardActions(c);
  action('Retour à l’initialisation', () => navigate('Initialisation'), bar);
  action('Consulter la télémétrie existante', () => navigate('Vol en cours'), bar);
  if (!session) {
    c.append(el('p', 'Aucun suivi démarré. Les notes libres ne renseignent jamais les déclarations ci-dessous.'));
    action('Démarrer le suivi du vol', () => sessionAction('start'), bar, 'primary').disabled = data?.storage_blocked || connectionLost;
  } else {
    c.append(el('p', (session.status === 'active' ? 'Suivi actif' : 'Suivi terminé') + ' · OFP : ' + (session.plan_summary.ofp_id || 'sans identifiant') + ' · révision ' + session.plan_revision + ' · ' + data.archived_count + ' suivi(s) archivé(s).'));
    action(session.status === 'active' ? 'Terminer le suivi' : 'Reprendre le suivi', () => sessionAction(session.status === 'active' ? 'end' : 'resume'), bar);
  }
  action('Réinitialiser le suivi', async () => {
    if (confirm('Ouvrir un suivi vide ? Le suivi précédent sera conservé sous local/, y compris un fichier ancien ou invalide.')) await sessionAction('reset');
  }, bar, 'danger');
  if (!session || session.status !== 'active' || data.storage_blocked) return;
  flightDashboard(view, data);
  let phaseData = data.phase, effectivePhase = phaseData?.effective?.value;
  let phase = card(view, 'Phase du vol', 'Changer de phase ne coche aucune case. Le choix manuel reste actif jusqu’au retour explicite en automatique.');
  const phaseLabel = id => data.phases.find(p => p.id === id)?.label || 'Non confirmée';
  const substates = { taxi: 'Roulage', takeoff: 'Décollage', approach: 'Approche', landing: 'Atterrissage', parking: 'Parking', go_around: 'Remise des gaz' };
  phase.append(el('p', phaseLabel(effectivePhase) + ' · ' + (phaseData?.mode === 'manual' ? 'Déclarée par le pilote' : 'Calculée') + (phaseData?.substate ? ' · ' + substates[phaseData.substate] : ''), { id: 'flightPhase' }));
  let getPhase = field(phase, 'Phase', phaseDraft?.sessionId === session.id ? phaseDraft.value : session.forced_phase || 'automatic', 'text', ['automatic', ...data.phases.map(p => p.id)]);
  phase.querySelector('select').oninput = () => { phaseDraft = { sessionId: session.id, value: getPhase() }; };
  for (let option of phase.querySelector('select').options) option.textContent = option.value === 'automatic' ? 'Automatique' : data.phases.find(p => p.id === option.value).label;
  let phaseActions = cardActions(phase);
  action('Enregistrer la phase', async () => {
    await sessionAction('phase', 'PUT', { phase: getPhase() === 'automatic' ? null : getPhase() });
    phaseDraft = null;
    render();
  }, phaseActions);
  action('Revenir en automatique', async () => {
    await sessionAction('phase', 'PUT', { phase: null });
    phaseDraft = null; render();
  }, phaseActions).disabled = !session.forced_phase;
  action('Prêt pour le départ', () => sessionAction('declarations', 'PUT', { declaration: {
    kind: 'event', field: 'event.departure_ready', value: true, reference: 'Geste explicite du pilote', context: { stage: 'departure' },
  } }), phaseActions).disabled = effectivePhase !== 'preflight';
  let evidence = el('div', null, {id:'flightPhaseEvidence'}); phase.append(evidence);
  flightPhaseEvidence(evidence, phaseData);
  declarationForms(view, session);
  let current = card(view, 'Déclarations du pilote', 'Saisies explicites, datées et révisées ; aucune interprétation des notes libres. Consultation et annonce ATIS sont déclarées séparément, à l’heure saisie.');
  if (!session.declarations.length) current.append(el('p', 'Aucune déclaration.'));
  for (let d of session.declarations) {
    let line = el('div', null, { className: 'card' });
    line.append(el('p', declarationLabel(d.field) + ' : ' + d.value + (d.unit ? ' ' + d.unit : '') + ' · déclarée · révision ' + d.revision + ' · ' + new Date(d.recorded_at * 1000).toLocaleString('fr-FR')));
    if (d.occurred_at) line.append(el('p', 'Heure déclarée : ' + new Date(d.occurred_at * 1000).toLocaleString('fr-FR')));
    line.append(el('p', 'Référence : ' + d.reference + ' · ' + Object.entries(d.context).map(([k,v]) => declarationLabel(k) + ' : ' + declarationLabel(v)).join(' · ')));
    if (d.revoked_at || d.invalidated_reason) line.append(el('p', d.revoked_at ? 'Révoquée / remplacée' : d.invalidated_reason, { className: 'banner warn' }));
    if (!d.revoked_at) action('Révoquer', () => sessionAction('declarations/' + d.id + '/revoke'), cardActions(line), 'small');
    current.append(line);
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
    if (tab === 'Vol' && current?.session?.id === ai.session?.session?.id && current?.session?.status === ai.session?.session?.status && path.startsWith('steps/')) updateFlightView();
    else render();
  } catch (e) {
    // A stale tab must not apply a gesture to a newly opened flight.
    ai.session = await api('ai/session');
    render();
    throw e;
  }
}

let declarationDrafts = {};
const DECLARATION_LABELS = {
  true:'Oui', false:'Non', radio:'Radio', event:'Événement', stand:'Poste', exit:'Sortie de piste', approach_position:'Position en approche', tod_utc:'TOD fourni (date et heure avec fuseau)',
  clearance:'Clairance', selection:'Choix', atis:'ATIS déclaré', performance:'Performance',
  altitude:'Altitude autorisée', heading:'Cap autorisé', speed:'Vitesse autorisée', squawk:'Code transpondeur', instruction:'Instruction reçue',
  runway:'Piste', approach:'Approche', sid:'SID', star:'STAR', heard_letter:'Lettre écoutée', announced_letter:'Lettre annoncée', callsign:'Indicatif utilisé',
  preflight:'Prévol', cruise:'Croisière',
  v1:'V1', vr:'VR', v2:'V2', flex:'FLEX', vapp:'VAPP', thr_red:'THR RED', acc:'ACC',
  departure:'Départ', arrival:'Arrivée', climb:'Montée', descent:'Descente', taxi:'Roulage', transfer:'Transfert',
  type:'Type', station:'Station', stage:'Départ / arrivée', airport:'Aérodrome', version:'Version ATIS',
  aircraft:'Appareil', mass:'Masse', configuration:'Configuration', weather:'Météo',
};
function declarationLabel(value) {
  let text = String(value), parts = text.split('.');
  return parts.length === 2 && ['clearance','selection','atis','performance','station'].includes(parts[0])
    ? parts.map(key => DECLARATION_LABELS[key] || key).join(' · ') : DECLARATION_LABELS[text] || text;
}
function declarationForms(view, session) {
  if (declarationDrafts.sessionId !== session.id) declarationDrafts = { sessionId: session.id };
  for (let [kind, title, fields, contextFields] of [
    ['clearance', 'Déclarer une clairance', ['altitude', 'heading', 'speed', 'squawk', 'instruction','runway','sid','qnh','frequency','taxi_route'], [['type','Type de clairance', ['departure','climb','descent','approach','runway','taxi','transfer']], ['station','Station / origine']]],
    ['selection', 'Déclarer la piste ou l’approche retenue', ['runway','approach','sid','star','tod_utc'], [['stage','Départ / arrivée', ['departure','arrival']]]],
    ['atis', 'Déclarer un ATIS consulté ou annoncé', ['heard_letter','announced_letter'], [['airport','Aérodrome OACI'], ['version','Version / référence du bulletin']]],
    ['station', 'Déclarer la station réellement utilisée', ['callsign'], [['stage','Phase de déclaration', ['preflight','departure','climb','cruise','descent','arrival']]]],
    ['radio', 'Déclarer la position ou le poste pour la radio', ['stand','exit','approach_position'], [['stage','Phase de déclaration', ['preflight','departure','climb','cruise','descent','arrival']]]],
    ['event', 'Confirmer un événement de procédure', ['before_start','ready_pushback','after_start','before_taxi','holding_point','handoff','traffic_announcement','before_tod','approach_ready','landing_ready','go_around','runway_vacated','parked','securing','departure_ready'], [['stage','Phase de déclaration', ['preflight','departure','climb','cruise','descent','arrival']]]],
    ['performance', 'Déclarer une performance manuelle', ['v1','vr','v2','flex','vapp','thr_red','acc'], [['aircraft','Appareil'], ['runway','Piste'], ['mass','Masse et unité'], ['configuration','Configuration'], ['weather','Météo associée']]],
  ]) {
    let draft = declarationDrafts[kind] ||= {}, details = el('details', null);
    details.open = !!draft.open;
    details.ontoggle = () => { draft.open = details.open; };
    details.append(el('summary', title)); view.append(details);
    let c = card(details, title, 'Référence et contexte obligatoires. Une nouvelle saisie remplace le même champ ; l’historique est conservé.');
    const draftField = (key, label, choices = null) => {
      let get = field(c, label, draft[key] ?? choices?.[0] ?? '', 'text', choices), input = c.lastChild.querySelector('input,select');
      if (choices) for (let option of input.options) option.textContent = declarationLabel(option.value);
      input.oninput = () => { draft[key] = get(); };
      return get;
    };
    let getField = draftField('field', 'Champ déclaré', fields), value = draftField('value', kind === 'event' ? 'Événement confirmé' : 'Valeur déclarée', kind === 'event' ? ['true','false'] : null), unit = draftField('unit', 'Unité (ex. kt, ft, °C)'), reference = draftField('reference', 'Référence (EFB, ATC ou bulletin)');
    let getTime = null;
    if (kind === 'atis') {
      let now = new Date(), local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0,16);
      getTime = field(c, 'ATIS consulté ou annoncé le', draft.time || local, 'datetime-local');
      c.lastChild.querySelector('input').oninput = () => { draft.time = getTime(); };
    }
    let getters = contextFields.map(([key,label,choices]) => [key, draftField(key,label,choices)]);
    action('Enregistrer : ' + title, async () => {
      let raw = value().trim();
      if (!raw || !reference().trim()) throw Error('Valeur et référence obligatoires.');
      if (kind === 'performance' && !Number.isFinite(Number(raw))) throw Error('Saisir une performance numérique.');
      if (getTime && !Number.isFinite(new Date(getTime()).getTime())) throw Error('Saisir l’heure de consultation de l’ATIS.');
      if (kind === 'event' && !['true','false'].includes(raw.trim().toLowerCase())) throw Error('Confirmer un événement avec true ou false.');
      await sessionAction('declarations', 'PUT', { declaration: { kind, field: kind + '.' + getField(), value: kind === 'performance' ? Number(raw) : kind === 'event' ? raw.trim().toLowerCase() === 'true' : raw, unit: unit().trim() || null, reference: reference().trim(), occurred_at: getTime ? new Date(getTime()).getTime()/1000 : null, context: Object.fromEntries(getters.map(([key,get]) => [key,get().trim()])) } });
      delete declarationDrafts[kind];
      render();
    }, cardActions(c), 'primary');
  }
}
let networkDetailsOpen = false;
function flightNetworkView(view, network) {
  if (!network) return;
  const states = { disabled:'Intégration désactivée', unknown:'Flux inconnu', stale:'Données périmées', empty:'Aucune position candidate en ligne', current:'Cache disponible' };
  const sourceLabel = source => {
    if (!source) return 'Source inconnue';
    const status = { current:'actuel', stale:'périmé', unavailable:'inconnu' }[source.status] || source.status;
    return source.source + ' · ' + status + (source.age_s == null ? ' · âge inconnu' : ' · âge ' + Math.floor(source.age_s) + ' s');
  };
  let c = card(view, 'Réseau pour le suivi', states[network.state] || 'État inconnu');
  c.append(el('p', network.notice, { className: 'muted' }));
  if (connectionLost) c.append(el('p', 'Connexion à Glareshield perdue : état réseau non confirmé.', { className: 'banner warn' }));
  if (network.used_station) c.append(el('p', 'Station utilisée : ' + network.used_station.value + ' · déclarée par le pilote · ' + Math.floor(network.used_station.age_s) + ' s · ' + ({ disabled:'intégration désactivée', unknown:'présence inconnue', stale:'présence non confirmée, flux périmé', online:'position publiée en ligne', offline:'position absente du dernier flux' }[network.used_station_state]) + '. Cette déclaration ne confirme pas la couverture.'));
  else c.append(el('p', 'Station utilisée : <station à déclarer>.'));
  if (network.state === 'disabled') return;
  c.append(el('p', sourceLabel(network.feeds.whazzup), { className: 'muted' }));
  let positions = (network.positions || []).filter(p => p.useful_for.length || p.pilot_selected);
  if (!positions.length && network.positions !== null) c.append(el('p', 'Aucune position candidate pour la phase courante ou suivante. La couverture reste à vérifier.'));
  for (let p of positions) {
    let matches = p.matched_by.map(m => ({ callsign_prefix:'Préfixe OACI', distance_to_airport:'Proximité aérodrome', distance_to_aircraft:'Proximité appareil', published_range:'Portée publiée' }[m.basis] || m.basis) + (m.airport ? ' ' + m.airport : '')).join(', ');
    c.append(el('p', p.callsign + (p.frequency_mhz == null ? ' · fréquence inconnue' : ' · ' + p.frequency_mhz.toFixed(3) + ' MHz publiée') + ' · ' + p.useful_for.map(slot => slot === 'current' ? 'phase courante' : 'phase suivante').join(', ') + ' · ' + (matches || 'Déclaration pilote') + ' · couverture non confirmée' + (p.pilot_selected ? ' · station déclarée utilisée' : '')));
  }
  let details = el('details', null);
  details.open = networkDetailsOpen;
  details.ontoggle = () => { networkDetailsOpen = details.open; };
  details.append(el('summary', 'ATIS et météo publiés')); c.append(details);
  for (let a of network.atis) {
    details.append(el('h4', a.station + ' · ATIS téléchargé ' + (a.revision || '<lettre inconnue>')));
    details.append(el('p', sourceLabel(a.provenance) + ' · texte non interprété · référence ' + a.reference, { className: 'muted' }));
    details.append(el('pre', a.lines.join('\n')));
  }
  if (!network.atis.length) details.append(el('p', 'Aucun ATIS téléchargé pour les positions candidates.'));
  for (let w of network.weather) for (let kind of ['metar', 'taf']) {
    let bulletin = w[kind];
    details.append(el('h4', w.icao + ' · ' + kind.toUpperCase() + ' IVAO'));
    details.append(el('p', sourceLabel(bulletin.provenance), { className: 'muted' }));
    details.append(el('pre', bulletin.raw || ({ feed_unavailable:'Flux inconnu', not_published:'Bulletin non publié' }[bulletin.status] || 'Inconnu')));
    if (bulletin.values) for (let [key, value] of Object.entries(bulletin.values)) {
      details.append(el('p', ({ qnh:'QNH', temperature:'Température', wind:'Vent' }[key]) + ' : ' + (value.value ?? '<inconnu>') + (value.unit ? ' ' + value.unit : '') + ' · ' + ({ available:'publié', stale:'périmé', unavailable:'inconnu' }[value.status]) + ' · lecture ' + ({ parsed:'réussie', ambiguous:'ambiguë', missing:'absente', unsupported:'format non pris en charge', truncated:'texte tronqué' }[value.reading_status])));
    }
  }
  for (let a of network.pilot_atis) c.append(el('p', (a.field === 'atis.announced_letter' ? 'ATIS annoncé' : 'ATIS consulté') + ' : ' + a.context.airport + ' ' + a.value + ' · déclaré à ' + new Date(a.occurred_at * 1000).toLocaleString('fr-FR') + ' · ' + ({ same_letter:'même lettre publiée ; vérifier aussi le texte', different_letter:'lettre publiée différente : nouvelle consultation à confirmer', unknown:'comparaison non confirmée' }[a.comparison] || 'comparaison non confirmée'), { className: a.comparison === 'different_letter' ? 'banner warn' : 'muted' }));
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
  c.append(el('p', 'Le suivi conserve les cases, déclarations et phases forcées sous local/copilot/. Les phases automatiques et détections seront raccordées lors des prochaines étapes.'));
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
  ['Vol', flightPendingView, 'plane', 'État du suivi de session'],
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
