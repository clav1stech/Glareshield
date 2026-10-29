// Preparation and navigation only. Flight sessions will be connected by their service.
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
  readiness.append(el('p', 'Le service de session n’est pas encore livré. Le démarrage du suivi sera raccordé à ce service.', { id: 'startExplanation', className: 'muted' }));
  let start = action('Démarrer le suivi du vol', () => {}, cardActions(readiness), 'primary', 'play');
  start.disabled = true;
  start.setAttribute('aria-describedby', 'startExplanation');
  action('Voir le mode Vol', () => navigate('Vol'), cardActions(readiness), 'small');
}
function flightPendingView(view) {
  let c = card(view, 'Suivi du vol bientôt disponible', 'Aucune session de suivi n’est démarrée.');
  c.append(el('p', 'Le service de session et le contenu dynamique du vol seront livrés dans les étapes suivantes du copilote.'));
  let bar = cardActions(c);
  action('Retour à l’initialisation', () => navigate('Initialisation'), bar, 'primary');
  action('Consulter la télémétrie existante', () => navigate('Vol en cours'), bar);
  action('Ouvrir Export IA', () => navigate('Export IA'), bar);
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
  c.append(el('p', 'Le contrat A320 est disponible. Le suivi de session, les phases et les procédures dynamiques seront raccordés lors des prochaines étapes.'));
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
