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
  let phaseData = data.phase, effectivePhase = phaseData?.effective?.value;
  let phase = card(view, 'Phase du vol', 'Changer de phase ne coche aucune case. Le choix manuel reste actif jusqu’au retour explicite en automatique.');
  const phaseLabel = id => data.phases.find(p => p.id === id)?.label || 'Non confirmée';
  const substates = { taxi: 'Roulage', takeoff: 'Décollage', approach: 'Approche', landing: 'Atterrissage', parking: 'Parking', go_around: 'Remise des gaz' };
  phase.append(el('p', phaseLabel(effectivePhase) + ' · ' + (phaseData?.mode === 'manual' ? 'Déclarée par le pilote' : 'Calculée') + (phaseData?.substate ? ' · ' + substates[phaseData.substate] : ''), { id: 'flightPhase' }));
  if (phaseData?.suspended) phase.append(el('p', 'Transitions automatiques suspendues.', { className: 'banner warn' }));
  if (phaseData?.effective?.status === 'stale') phase.append(el('p', 'Dernière phase connue · données périmées.', { className: 'banner warn' }));
  for (let text of phaseData?.evidence || []) phase.append(el('p', text, { className: 'muted' }));
  for (let text of phaseData?.uncertainty || []) phase.append(el('p', text, { className: 'banner warn' }));
  if (phaseData?.automatic?.method) phase.append(el('p', phaseData.automatic.method, { className: 'muted' }));
  if (phaseData?.next_trigger) phase.append(el('p', 'Prochain déclencheur : ' + phaseData.next_trigger.label + (phaseData.next_trigger.elapsed_s ? ' · confirmation ' + Math.floor(phaseData.next_trigger.elapsed_s) + '/' + phaseData.next_trigger.hold_s + ' s' : '')));
  let progress = phaseData?.geometry?.route_progress;
  if (progress) phase.append(el('p', 'Route prévue : prochain point géométrique ' + progress.next_waypoint + ', reste ' + progress.remaining_along_route_nm + ' NM. Un direct ou un écart à la route peut fausser cet avancement ; il ne décrit pas la route active du MCDU.', { className: 'muted' }));
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
  declarationForms(view, session);
  let current = card(view, 'Déclarations du pilote', 'Saisies explicites, datées et révisées ; aucune interprétation des notes libres. L’ATIS est déclaré consulté à l’heure saisie.');
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
  for (let p of data.phases) {
    let details = el('details', null), summary = el('summary', p.label);
    details.open = (effectivePhase || 'preflight') === p.id;
    details.append(summary); view.append(details);
    for (let group of data.groups.filter(g => g.phase === p.id)) {
      let groupCard = card(details, group.label);
      for (let step of group.steps) {
        let label = el('label', null, { className: 'check' }), input = el('input', null, { type: 'checkbox', checked: step.checked });
        input.setAttribute('aria-label', step.label);
        input.onchange = async () => {
          input.disabled = true;
          try { await sessionAction('steps/' + step.id, 'PUT', { checked: input.checked }); }
          catch (e) { input.checked = step.checked; message(e.message, true); }
          finally { input.disabled = false; }
        };
        label.append(input, el('span', step.label + ' · ' + ({manual:'Manuel', detected:'Détecté', pending:'À confirmer'}[step.provenance])));
        groupCard.append(label);
        if (step.detected) groupCard.append(el('small', 'Observation ' + (step.detected.checked ? 'cochée' : 'décochée') + ' · ' + step.detected.reference + (step.detection_current ? '' : ' · historique à reconfirmer'), { className: 'muted' }));
        if (step.conflict) groupCard.append(el('p', 'Observation contradictoire ; le geste manuel reste prioritaire.', { className: 'banner warn' }));
      }
    }
  }
}

async function sessionAction(path, method = 'POST', values = {}) {
  let current = ai.session;
  try {
    ai.session = await api('ai/session/' + path, method, { session_id: current?.session?.id || null, universe: current.universe, ...values });
    render();
  } catch (e) {
    // A stale tab must not apply a gesture to a newly opened flight.
    ai.session = await api('ai/session');
    render();
    throw e;
  }
}

let declarationDrafts = {};
const DECLARATION_LABELS = {
  clearance:'Clairance', selection:'Choix', atis:'ATIS consulté', performance:'Performance',
  altitude:'Altitude autorisée', heading:'Cap autorisé', speed:'Vitesse autorisée', squawk:'Code transpondeur', instruction:'Instruction reçue',
  runway:'Piste', approach:'Approche', sid:'SID', star:'STAR', heard_letter:'Lettre écoutée',
  v1:'V1', vr:'VR', v2:'V2', flex:'FLEX', vapp:'VAPP', thr_red:'THR RED', acc:'ACC',
  departure:'Départ', arrival:'Arrivée', climb:'Montée', descent:'Descente', taxi:'Roulage', transfer:'Transfert',
  type:'Type', station:'Station', stage:'Départ / arrivée', airport:'Aérodrome', version:'Version ATIS',
  aircraft:'Appareil', mass:'Masse', configuration:'Configuration', weather:'Météo',
};
function declarationLabel(value) {
  let text = String(value), parts = text.split('.');
  return parts.length === 2 && ['clearance','selection','atis','performance'].includes(parts[0])
    ? parts.map(key => DECLARATION_LABELS[key] || key).join(' · ') : DECLARATION_LABELS[text] || text;
}
function declarationForms(view, session) {
  if (declarationDrafts.sessionId !== session.id) declarationDrafts = { sessionId: session.id };
  for (let [kind, title, fields, contextFields] of [
    ['clearance', 'Déclarer une clairance', ['altitude', 'heading', 'speed', 'squawk', 'instruction'], [['type','Type de clairance', ['departure','climb','descent','approach','runway','taxi','transfer']], ['station','Station / origine']]],
    ['selection', 'Déclarer la piste ou l’approche retenue', ['runway','approach','sid','star'], [['stage','Départ / arrivée', ['departure','arrival']]]],
    ['atis', 'Déclarer un ATIS effectivement consulté', ['heard_letter'], [['airport','Aérodrome OACI'], ['version','Version / référence du bulletin']]],
    ['performance', 'Déclarer une performance manuelle', ['v1','vr','v2','flex','vapp','thr_red','acc'], [['aircraft','Appareil'], ['runway','Piste'], ['mass','Masse et unité'], ['configuration','Configuration'], ['weather','Météo associée']]],
  ]) {
    let draft = declarationDrafts[kind] ||= {}, details = el('details', null);
    details.append(el('summary', title)); view.append(details);
    let c = card(details, title, 'Référence et contexte obligatoires. Une nouvelle saisie remplace le même champ ; l’historique est conservé.');
    const draftField = (key, label, choices = null) => {
      let get = field(c, label, draft[key] ?? choices?.[0] ?? '', 'text', choices), input = c.lastChild.querySelector('input,select');
      if (choices) for (let option of input.options) option.textContent = declarationLabel(option.value);
      input.oninput = () => { draft[key] = get(); };
      return get;
    };
    let getField = draftField('field', 'Champ déclaré', fields), value = draftField('value', 'Valeur déclarée'), unit = draftField('unit', 'Unité (ex. kt, ft, °C)'), reference = draftField('reference', 'Référence (EFB, ATC ou bulletin)');
    let getTime = null;
    if (kind === 'atis') {
      let now = new Date(), local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0,16);
      getTime = field(c, 'ATIS consulté le', draft.time || local, 'datetime-local');
      c.lastChild.querySelector('input').oninput = () => { draft.time = getTime(); };
    }
    let getters = contextFields.map(([key,label,choices]) => [key, draftField(key,label,choices)]);
    action('Enregistrer : ' + title, async () => {
      let raw = value().trim();
      if (!raw || !reference().trim()) throw Error('Valeur et référence obligatoires.');
      if (kind === 'performance' && !Number.isFinite(Number(raw))) throw Error('Saisir une performance numérique.');
      if (getTime && !Number.isFinite(new Date(getTime()).getTime())) throw Error('Saisir l’heure de consultation de l’ATIS.');
      await sessionAction('declarations', 'PUT', { declaration: { kind, field: kind + '.' + getField(), value: kind === 'performance' ? Number(raw) : raw, unit: unit().trim() || null, reference: reference().trim(), occurred_at: getTime ? new Date(getTime()).getTime()/1000 : null, context: Object.fromEntries(getters.map(([key,get]) => [key,get().trim()])) } });
      delete declarationDrafts[kind];
      render();
    }, cardActions(c), 'primary');
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
VIEWS['Vol'].ready = () => ai.session;
VIEWS['Vol'].load = () => loadAI(true);
