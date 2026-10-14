// Glareshield local interface. Lighting views; AI Bridge views live in ai.js.
let config,
  state,
  tab = 'Tableau de bord',
  editing = null,
  connectionLost = false,
  sessionToken = TOKEN;
const $ = s => document.querySelector(s);
const ICONS = {
  dashboard: 'M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z',
  log: 'M4 6h16M4 12h16M4 18h10',
  assign: 'M7 7h10M7 12h10M7 17h6M3 7h.01M3 12h.01M3 17h.01',
  rules: 'M9 5h11M9 12h11M9 19h11M4 5l1 1 2-2M4 12l1 1 2-2M4 19l1 1 2-2',
  effects: 'M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 100 8 4 4 0 000-8z',
  sources: 'M2 12h4l3-8 4 16 3-8h6',
  devices: 'M9 18h6M10 21h4M12 3a6 6 0 00-4 10.5c.7.7 1 1.4 1 2.5h6c0-1.1.3-1.8 1-2.5A6 6 0 0012 3z',
  controllers: 'M5 12h14M5 12a7 7 0 0114 0M5 12a7 7 0 0014 0M12 5v14',
  groups: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  scopes: 'M12 2a10 10 0 100 20 10 10 0 000-20zm0 5a5 5 0 100 10 5 5 0 000-10z',
  settings: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4',
  plane: 'M21 16v-2l-8-5V3.5a1.5 1.5 0 00-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z',
  plan: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14',
  export: 'M12 3v12M7 10l5 5 5-5M5 21h14',
  variables: 'M4 7V5h16v2M9 19h6M12 5v14',
  play: 'M7 4l13 8-13 8z',
  stop: 'M6 6h12v12H6z',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  refresh: 'M20 11a8 8 0 10-2.3 5.7M20 4v7h-7',
};
function icon(name) {
  let svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  let path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[name] || '');
  svg.append(path);
  return svg;
}
// Each view declares its section, icon, subtitle, renderer and whether lighting tests apply.
const VIEWS = {};
const NAV = [
  ['Pilotage', ['Tableau de bord', 'Journal']],
  ['Éclairage', ['Affectations', 'Règles', 'Effets', 'Sources']],
  ['Matériel', ['Appareils', 'Contrôleurs', 'Groupes', 'Portées']],
  ['Assistant IA', ['Vol en cours', 'Plan de vol', 'Export IA', 'Variables IA']],
  ['Système', ['Réglages']],
];
function el(tag, text, attrs = {}) {
  let n = document.createElement(tag);
  if (text !== null) n.textContent = text;
  Object.assign(n, attrs);
  return n;
}
function badge(text, kind = '') {
  return el('span', text, { className: 'badge ' + kind });
}
function setConnection(text, kind) {
  $('#connection').textContent = text;
  $('#simDot').className = 'dot ' + kind;
}
async function api(path, method = 'GET', body) {
  let r;
  let send = () =>
    fetch('/api/' + path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-Glareshield-Token': sessionToken },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  try {
    r = await send();
    if (r.status === 403) {
      let page = await fetch('/', { cache: 'no-store' }),
        match = (await page.text()).match(/const TOKEN='([^']+)'/);
      if (match && match[1] !== sessionToken) {
        sessionToken = match[1];
        r = await send();
      }
    }
  } catch (e) {
    connectionLost = true;
    setConnection('Reconnexion en cours…', 'danger');
    throw Error('Connexion à Glareshield interrompue. Reconnexion en cours…');
  }
  let d = await r.json();
  if (r.status === 403) throw Error('Session renouvelée après redémarrage : actualisez la page (F5).');
  if (!r.ok) throw Error(d.detail || 'Opération refusée');
  return d;
}
let lastToast = null;
function message(text, error = false) {
  let note = $('#editorStatus');
  if (note && note.closest('dialog').open) {
    note.hidden = false;
    note.textContent = text;
    note.className = 'dialog-body ' + (error ? 'error' : 'ok');
  }
  if (lastToast && lastToast.textContent === text) return;
  let toast = el('div', text, { className: 'toast ' + (error ? 'error' : 'ok') });
  $('#toasts').append(toast);
  lastToast = toast;
  setTimeout(() => {
    toast.remove();
    if (lastToast === toast) lastToast = null;
  }, error ? 7000 : 3500);
  while ($('#toasts').children.length > 3) $('#toasts').firstChild.remove();
}
function action(text, fn, parent, className = '', iconName = null) {
  let b = el('button', null, { type: 'button', className });
  if (iconName) b.append(icon(iconName));
  b.append(text);
  b.onclick = async () => {
    b.disabled = true;
    try {
      await fn();
    } catch (e) {
      message(e.message, true);
    } finally {
      b.disabled = false;
    }
  };
  parent.append(b);
  return b;
}
function card(parent, title, subtitle = null, extra = null) {
  let c = el('div', null, { className: 'card' }),
    head = el('div', null, { className: 'card-head' }),
    text = el('div', null);
  text.append(el('h3', title));
  if (subtitle) text.append(el('small', subtitle));
  head.append(text);
  if (extra) head.append(extra);
  c.append(head);
  parent.append(c);
  return c;
}
function cardActions(c) {
  let bar = el('div', null, { className: 'card-actions' });
  c.append(bar);
  return bar;
}
function sectionHead(parent, title, text = null) {
  let head = el('div', null, { className: 'section-head' }),
    box = el('div', null);
  box.append(el('h2', title));
  if (text) box.append(el('p', text));
  head.append(box);
  parent.append(head);
  return head;
}
const OPTION_LABELS = {
  always: 'Toujours',
  eq: 'Égal à',
  ne: 'Différent de',
  gt: 'Supérieur à',
  ge: 'Supérieur ou égal',
  lt: 'Inférieur à',
  le: 'Inférieur ou égal',
  active: 'Active',
  all: 'Toutes (ET)',
  any: 'Au moins une (OU)',
  static: 'Fixe',
  blink: 'Clignotement',
  pulse: 'Impulsions',
  level_map: 'Paliers',
  sound: 'Son',
  mock: 'Simulée',
  lvar: 'Variable du cockpit',
  audio_process: 'Activité audio',
  simulator_state: 'État du simulateur',
  keyboard: 'Touche clavier',
  light: 'Lampe',
  audio: 'Sortie audio',
};
function field(parent, name, value, type = 'text', choices = null) {
  let l = el('label', name),
    i = choices ? el('select', null) : el('input', null, { type });
  if (choices)
    for (let c of choices)
      i.append(
        el(
          'option',
          OPTION_LABELS[c] ||
            (['Effet', 'Son associé'].includes(name) && config?.effects[c] ? effectTitle(c) : c),
          { value: c },
        ),
      );
  if (type === 'checkbox') {
    l.className = 'check';
    i.checked = !!value;
  } else i.value = value ?? '';
  if (type === 'number') {
    i.step = 'any';
    let limits = {
      'Luminosité (%)': [0, 100],
      'Luminosité haute (%)': [1, 100],
      'Luminosité basse (%)': [1, 100],
      'Temps en phase haute (%)': [0, 100],
      'Volume (%)': [0, 100],
      'Température (K)': [1000, 10000, 1],
      'Transition (ms)': [0, 60000, 1],
      'Cycles (0 : continu)': [0, null, 1],
      'Intervalle (ms)': [50, 60000, 1],
      'Seuil audio (0 à 1)': [0, 1],
      'Code de touche Windows (0 : aucun)': [0, 254, 1],
    };
    if (name.startsWith('Fréquence des ')) limits[name] = [0, config?.settings.max_flash_hz ?? 2];
    if (limits[name]) {
      let [min, max, step] = limits[name];
      i.min = min;
      if (max !== null) i.max = max;
      if (step) i.step = step;
    }
  }
  i.setAttribute('aria-label', name);
  l.append(i);
  let hint =
    (name === 'Couleur' && type === 'color'
      ? 'Cliquer sur la couleur pour choisir la teinte du flash.'
      : FIELD_HELP[name]) || Object.entries(SETTING_LABELS).find(([k, v]) => v === name)?.[0];
  if (hint)
    l.append(
      el(
        'small',
        name === 'Couleur' && type === 'color'
          ? 'Cliquer sur la couleur pour choisir la teinte du flash.'
          : FIELD_HELP[name] || SETTING_HELP[hint],
        { className: 'muted' },
      ),
    );
  parent.append(l);
  return () => (type === 'checkbox' ? i.checked : type === 'number' ? Number(i.value) : i.value);
}
function checks(parent, title, choices, selected = []) {
  let box = el('div', null);
  box.append(el('h4', title));
  let readers = choices.map(([id, label]) => [id, field(box, label, selected.includes(id), 'checkbox')]);
  parent.append(box);
  return () => readers.filter(([id, read]) => read()).map(([id]) => id);
}
function light(parent, state = {}) {
  let box = el('div', null, { className: 'grid' });
  parent.append(box);
  let on = field(box, 'Allumée', state.on ?? true, 'checkbox'),
    bright = field(box, 'Luminosité (%)', state.brightness ?? 100, 'number'),
    mode = field(box, 'Couleur', state.color ? 'RVB' : state.kelvin ? 'Température' : 'Conserver', 'text', [
      'Conserver',
      'RVB',
      'Température',
    ]),
    color = field(
      box,
      'Couleur RVB',
      '#' + (state.color || [255, 255, 255]).map(v => v.toString(16).padStart(2, '0')).join(''),
      'color',
    ),
    kelvin = field(box, 'Température (K)', state.kelvin ?? 2700, 'number'),
    transition = field(box, 'Transition (ms)', state.transition_ms ?? 0, 'number');
  return () => {
    let out = { on: on(), brightness: bright(), transition_ms: transition() };
    if (mode() === 'RVB')
      out.color = color()
        .slice(1)
        .match(/../g)
        .map(v => parseInt(v, 16));
    if (mode() === 'Température') out.kelvin = kelvin();
    return out;
  };
}
function condition(parent, c = { op: 'always' }) {
  let box = el('div', null, { className: 'condition' }),
    content = el('div', null);
  parent.append(box);
  let op = field(box, 'Condition', c.op, 'text', [
    'always',
    'eq',
    'ne',
    'gt',
    'ge',
    'lt',
    'le',
    'active',
    'all',
    'any',
  ]);
  box.append(content);
  let read;
  function update() {
    content.replaceChildren();
    if (['all', 'any'].includes(op())) {
      let children = (c.conditions?.length ? c.conditions : [{ op: 'always' }]).map(v =>
        condition(content, v),
      );
      action('Ajouter une condition', () => children.push(condition(content)), content);
      read = () => ({ op: op(), conditions: children.map(fn => fn()) });
    } else if (op() === 'always') read = () => ({ op: 'always' });
    else {
      let source = field(
        content,
        'Source',
        c.source || Object.keys(config.sources)[0],
        'text',
        Object.keys(config.sources),
      );
      let value = field(content, 'Valeur', c.value ?? 1, 'number');
      read = () =>
        op() === 'active' ? { op: op(), source: source() } : { op: op(), source: source(), value: value() };
    }
  }
  box.querySelector('select').onchange = update;
  update();
  return () => read();
}
function selectors(parent, selected) {
  let choices = [
    ['scope:active', 'Portée active'],
    ...Object.keys(config.groups).map(k => ['group:' + k, 'Groupe : ' + k]),
    ...Object.entries(config.devices).map(([k, v]) => ['device:' + k, v.name]),
  ];
  let include = checks(parent, 'Cibles', choices, selected),
    exclude = checks(
      parent,
      'Exclusions',
      choices.filter(([id]) => id !== 'scope:active'),
      selected.filter(v => v.startsWith('exclude:')).map(v => v.slice(8)),
    );
  return () => [...include(), ...exclude().map(v => 'exclude:' + v)];
}
function selectedDevices(targets) {
  function group(id, seen = new Set()) {
    if (seen.has(id)) return [];
    return (config.groups[id] || []).flatMap(v =>
      v.startsWith('group:') ? group(v.slice(6), new Set([...seen, id])) : [v],
    );
  }
  function expand(v) {
    if (v === 'scope:active') return (config.scopes[config.active_scope] || []).flatMap(v => group(v));
    if (v.startsWith('group:')) return group(v.slice(6));
    if (v.startsWith('device:')) return [v.slice(7)];
    return [];
  }
  let included = new Set(targets.filter(v => !v.startsWith('exclude:')).flatMap(expand));
  for (let id of targets.filter(v => v.startsWith('exclude:')).flatMap(v => expand(v.slice(8))))
    included.delete(id);
  return [...included].filter(id => config.devices[id]);
}
function assignments(view) {
  let cards = el('div', null, { className: 'cards' });
  view.append(cards);
  if (!config.rules.length) cards.append(el('div', 'Aucune fonction définie : créer une règle.', { className: 'empty' }));
  for (let rule of config.rules) {
    let ids = selectedDevices(rule.targets),
      c = card(cards, rule.name || rule.id, 'Priorité ' + rule.priority, badge(rule.enabled ? 'Activée' : 'Désactivée', rule.enabled ? 'ok' : ''));
    c.append(
      el('p', ids.length ? ids.map(id => config.devices[id].name).join(', ') : 'Aucun appareil affecté'),
      el('small', rule.targets.includes('scope:active') ? 'Suit la portée active' : 'Sélection indépendante de la portée'),
    );
    let bar = cardActions(c);
    action('Choisir les appareils', () => editAssignment(rule.id), bar, 'small');
    action('Régler la fonction', () => edit('rules', rule.id), bar, 'small ghost');
    action('Tester 3 s', () => openTest(testContext('assignments', rule.id)), bar, 'small ghost', 'play');
  }
}
function editAssignment(id) {
  let rule = config.rules.find(v => v.id === id);
  $('#title').textContent = 'Affectations · ' + (rule.name || id);
  let p = $('#fields');
  p.replaceChildren();
  let enabled = field(p, 'Fonction activée', rule.enabled, 'checkbox'),
    mode = field(
      p,
      'Mode de sélection',
      rule.targets.every(v => v.startsWith('device:')) ? 'Lampes individuelles' : 'Groupes et portée',
      'text',
      ['Lampes individuelles', 'Groupes et portée'],
    );
  let individual = el('div', null),
    advanced = el('div', null),
    preview = el('p', null, { className: 'muted' });
  p.append(individual, advanced, preview);
  let lamps = checks(
      individual,
      'Appareils de cette fonction',
      Object.entries(config.devices).map(([k, v]) => [k, v.name + (v.kind === 'audio' ? ' (audio)' : '')]),
      selectedDevices(rule.targets),
    ),
    targets = selectors(advanced, rule.targets);
  let read = () => (mode() === 'Lampes individuelles' ? lamps().map(v => 'device:' + v) : targets());
  function update() {
    individual.hidden = mode() !== 'Lampes individuelles';
    advanced.hidden = mode() !== 'Groupes et portée';
    let ids = selectedDevices(read());
    preview.textContent = ids.length
      ? 'Sélection effective : ' + ids.map(id => config.devices[id].name).join(', ')
      : 'Aucune cible : cette fonction ne pilotera aucun appareil.';
  }
  p.onchange = update;
  update();
  draftPreview = () => {
    let c = structuredClone(config),
      r = c.rules.find(v => v.id === id);
    r.targets = read();
    r.enabled = enabled();
    return testContext('assignments', id, c);
  };
  $('#editorStatus').hidden = true;
  let copy = field(p, 'Copier les affectations de', '', 'text', [
    '',
    ...config.rules.filter(v => v.id !== id).map(v => v.id),
  ]);
  action(
    'Copier les appareils actuels',
    () => {
      let other = config.rules.find(v => v.id === copy());
      if (!other) return;
      let ids = new Set(selectedDevices(other.targets));
      for (let input of individual.querySelectorAll('input'))
        input.checked = ids.has(
          Object.keys(config.devices)[[...individual.querySelectorAll('input')].indexOf(input)],
        );
      let select = p.querySelector('select');
      select.value = 'Lampes individuelles';
      update();
    },
    p,
  );
  $('#remove').hidden = true;
  $('#form').onsubmit = async e => {
    e.preventDefault();
    try {
      let current = config.rules.find(v => v.id === id);
      current.targets = read();
      current.enabled = enabled();
      await persist();
      editor.close();
    } catch (e) {
      config = await api('config');
      message(e.message, true);
    }
  };
  editor.showModal();
}
const SETTING_LABELS = {
  render_hz: 'Cadence du moteur (Hz)',
  max_flash_hz: 'Plafond du clignotement (Hz, maximum 2)',
  brightness_threshold: 'Écart minimal de luminosité (%)',
  timeout_s: 'Délai maximal de commande (s)',
  restore_timeout_s: 'Délai maximal de restauration (s)',
  sound_timeout_s: 'Délai maximal de diffusion sonore (s)',
  retry_initial_s: 'Délai initial après erreur (s)',
  retry_max_s: 'Délai maximal après erreur (s)',
  discovery_interval_s: 'Actualisation des adresses (s)',
  ui_refresh_ms: 'Actualisation de l’interface (ms)',
  test_duration_s: 'Durée des tests de source (s)',
};
const SETTING_HELP = {
  render_hz:
    'Nombre de calculs par seconde. 10 Hz donne une mise à jour toutes les 100 ms ; augmenter cette valeur ne garantit pas que les lampes suivent plus vite.',
  max_flash_hz:
    'Limite autorisée pour les effets : 2 Hz correspond à deux flashes par seconde. Une fréquence supérieure est refusée.',
  brightness_threshold:
    'Un changement inférieur à ce nombre de points de luminosité n’envoie pas de nouvelle commande. 3 signifie, par exemple, qu’un passage de 50 % à 51 % est ignoré.',
  timeout_s:
    'Temps maximal d’attente d’une commande. Augmenter aide un appareil lent ; diminuer signale les problèmes plus vite.',
  restore_timeout_s:
    'Temps laissé aux appareils pour retrouver leur état initial, notamment une scène Hue dynamique.',
  sound_timeout_s:
    'Temps maximal laissé à une diffusion sonore. Les sorties sonores restent inactives tant qu’elles ne sont pas configurées.',
  retry_initial_s:
    'Attente avant le premier nouvel essai après une erreur. Le délai double lors des échecs suivants.',
  retry_max_s: 'Plafond de cette attente. Doit être au moins égal au délai initial.',
  discovery_interval_s: 'Intervalle entre les recherches d’adresse réseau des appareils déjà appairés.',
  ui_refresh_ms:
    'Fréquence de rafraîchissement des indicateurs. 1 500 ms = 1,5 seconde ; cela ne change pas la vitesse des lampes.',
  test_duration_s:
    'Durée par défaut des tests de source à durée personnalisée. Les boutons « Tester 3 s » durent toujours trois secondes.',
};
const FIELD_HELP = {
  Identifiant:
    'Nom technique unique utilisé pour les références. Choisir un nom simple ; modifier les références associées avant de le renommer.',
  Priorité:
    'Plus le nombre est élevé, plus la fonction est prioritaire sur une même lampe. Les flashes et les fonds fixes gardent deux priorités séparées.',
  'Exiger le simulateur connecté':
    'La fonction reste inactive si Glareshield ne reçoit pas de données du simulateur.',
  'Suspendre pendant la pause': 'Restaure les lampes de cette fonction pendant une pause du simulateur.',
  'Luminosité (%)': '0 à 100 %. L’extinction se règle avec la case « Allumée ».',
  Couleur:
    'RVB pour une couleur choisie, Température pour du blanc, Conserver pour garder la couleur actuelle.',
  'Température (K)':
    'Blanc chaud vers 2 700 K, neutre vers 4 000 K, froid vers 6 500 K. La plage réellement acceptée dépend de la lampe.',
  'Transition (ms)': 'Durée du changement sur Hue. 0 = immédiat ; 1 000 ms = une seconde.',
  'Fréquence des pulsations (Hz)':
    'Nombre de montées et descentes progressives par seconde. Maximum : le plafond défini dans Réglages.',
  'Fréquence des flashes (Hz)':
    'Nombre de flashes par seconde. 2 Hz = un cycle de 0,5 seconde. Maximum : le plafond défini dans Réglages.',
  'Luminosité haute (%)': 'Intensité pendant la phase lumineuse du flash.',
  'Luminosité basse (%)':
    'Intensité entre les flashes lorsqu’aucun fond fixe n’est actif. S’il existe un fond ATC ou DOME, ce fond est affiché à la place.',
  'Temps en phase haute (%)':
    'Part du cycle passée à la luminosité haute. 50 % à 2 Hz = 250 ms en phase haute et 250 ms en phase basse.',
  'Cycles (0 : continu)':
    'Nombre de cycles avant la fin de l’effet. 0 maintient l’effet tant que sa fonction est active.',
  'Volume (%)': 'Volume demandé à la sortie sonore, entre 0 et 100 %.',
  'Répétition (s, 0 : unique)':
    '0 joue une seule fois ; 10 relance le son toutes les dix secondes tant que la fonction reste active.',
  'Intervalle (ms)': 'Temps entre deux lectures de cette source. 100 ms = dix lectures par seconde.',
  'Seuil audio (0 à 1)':
    'Niveau minimal pour détecter un son. 0,02 est plus sensible que 0,10. Observer le niveau au tableau de bord pour l’ajuster.',
  'Durée minimale (ms)': 'Le son doit dépasser le seuil pendant cette durée avant de déclencher la fonction.',
  'Délai entre contacts (s)':
    'Attente minimale entre deux déclenchements audio pour éviter des activations répétées.',
  'Maintien du contact (s)': 'Durée pendant laquelle la détection audio reste active après un déclenchement.',
  'Code de touche Windows (0 : aucun)':
    'Code de la touche à surveiller : 163 = Ctrl droit. La touche est seulement lue, sans interception.',
  'Source pour table de niveaux': 'Source qui choisit le palier, par exemple 0, 1 ou 2 pour DOME.',
  'Valeur de source': 'Valeur qui sélectionne ce palier. Pour DOME : 0 = OFF, 1 = DIM, 2 = BRT.',
};
function help(parent, text) {
  parent.append(el('p', text, { className: 'muted' }));
}
function colourText(rgb) {
  let known = {
    '255,0,0': 'rouge',
    '255,140,0': 'ambre',
    '0,200,255': 'cyan',
    '255,255,255': 'blanc',
    '0,0,0': 'noir',
  };
  return known[rgb.join(',')] || '#' + rgb.map(v => v.toString(16).padStart(2, '0')).join('');
}
function lightText(v) {
  if (!v.on) return 'Éteinte';
  return (
    'Allumée à ' +
    v.brightness +
    ' %' +
    (v.color
      ? ' · ' + colourText(v.color)
      : v.kelvin
        ? ' · blanc à ' + v.kelvin + ' K'
        : ' · couleur conservée') +
    (v.transition_ms ? ' · transition de ' + v.transition_ms + ' ms' : '')
  );
}
function ruleName(id, cfg = config) {
  return cfg.rules.find(r => r.id === id)?.name || id;
}
function effectTitle(id, cfg = config) {
  let users = cfg.rules.filter(r => r.effect === id || r.sound === id).map(r => r.name || r.id);
  return users.length ? users.join(' / ') : OPTION_LABELS[cfg.effects[id]?.type] || id;
}
function describeEffect(parent, v) {
  parent.append(el('span', OPTION_LABELS[v.type], { className: 'badge accent' }));
  if (['blink', 'pulse'].includes(v.type)) {
    parent.append(
      el(
        'p',
        colourText(v.color) +
          ' · ' +
          Number((1 / v.period_s).toFixed(2)) +
          ' ' +
          (v.type === 'blink' ? 'flashes' : 'cycles') +
          ' par seconde',
      ),
      el('p', 'Luminosité : ' + v.high + ' % en phase haute, ' + v.low + ' % en phase basse'),
      el(
        'p',
        v.type === 'blink'
          ? 'Un cycle dure ' +
              Math.round(v.period_s * 1000) +
              ' ms : ' +
              Math.round(v.period_s * v.duty * 1000) +
              ' ms en phase haute, ' +
              Math.round(v.period_s * (1 - v.duty) * 1000) +
              ' ms en phase basse.'
          : 'Montée et descente progressives sur un cycle de ' + Math.round(v.period_s * 1000) + ' ms.',
      ),
      el('p', v.cycles ? v.cycles + ' cycles, puis arrêt.' : 'Continue tant que la fonction est active.'),
    );
    if (v.type === 'blink')
      help(parent, 'Entre les flashes, un fond ATC ou DOME actif remplace la luminosité basse.');
  } else if (v.type === 'static') parent.append(el('p', lightText(v.state)));
  else if (v.type === 'level_map') {
    for (let [key, state] of Object.entries(v.map))
      parent.append(
        el(
          'p',
          'Palier ' +
            key +
            (key === '0' && !state.on ? ' · OFF' : { 1: ' · DIM', 2: ' · BRT' }[key] || '') +
            ' : ' +
            lightText(state),
        ),
      );
  } else
    parent.append(
      el('p', 'Fichier : ' + v.file),
      el('p', 'Volume : ' + Math.round(v.volume * 100) + ' %'),
      el('p', v.repeat_s ? 'Répété toutes les ' + v.repeat_s + ' secondes.' : 'Joué une seule fois.'),
    );
}
function conditionText(c) {
  if (c.op === 'always') return 'Toujours';
  if (['all', 'any'].includes(c.op))
    return c.conditions.map(conditionText).join(c.op === 'all' ? ' ET ' : ' OU ');
  return c.source + ' ' + (OPTION_LABELS[c.op] || c.op) + (c.op === 'active' ? '' : ' ' + c.value);
}
function describeCard(parent, section, id, v) {
  if (section === 'effects') {
    describeEffect(parent, v);
    return;
  }
  if (section === 'rules') {
    parent.append(
      el('p', (v.enabled ? 'Activée' : 'Désactivée') + ' · priorité ' + v.priority),
      el('p', 'Déclenchement : ' + conditionText(v.condition)),
      el('p', 'Effet : ' + effectTitle(v.effect)),
      el(
        'p',
        'Appareils : ' +
          (selectedDevices(v.targets)
            .map(k => config.devices[k].name)
            .join(', ') || 'aucun'),
      ),
    );
    return;
  }
  if (section === 'sources') {
    parent.append(el('p', OPTION_LABELS[v.type] + ' · lecture toutes les ' + v.poll_ms + ' ms'));
    if (v.type === 'audio_process')
      parent.append(
        el('p', 'Processus : ' + v.process_names.join(', ')),
        el(
          'p',
          'Seuil ' +
            v.threshold +
            ' pendant ' +
            v.min_ms +
            ' ms ; maintien ' +
            v.hold_s +
            ' s ; délai ' +
            v.cooldown_s +
            ' s.',
        ),
      );
    else if (v.type === 'keyboard')
      parent.append(
        el('p', 'Touche surveillée : ' + v.key_code + (v.key_code === 163 ? ' (Ctrl droit)' : '')),
      );
    else if (v.name) parent.append(el('p', 'Variable : ' + v.name));
    return;
  }
  if (Array.isArray(v)) {
    parent.append(
      el(
        'p',
        v.map(k => config.devices[k]?.name || k.replace('group:', 'Groupe : ')).join(', ') || 'Aucun membre',
      ),
    );
    return;
  }
  parent.append(
    el(
      'p',
      section === 'devices'
        ? (v.kind === 'audio' ? 'Sortie audio' : 'Lampe') + ' · ' + v.driver
        : 'Contrôleur ' + v.type,
    ),
  );
  if (v.controller) parent.append(el('p', 'Contrôleur : ' + v.controller));
  if (section === 'controllers')
    parent.append(
      el('p', v.host ? 'Adresse manuelle : ' + v.host : 'Adresse trouvée automatiquement sur le réseau'),
    );
}
function testContext(section, id, candidate = config) {
  if (['devices', 'controllers'].includes(section) && !candidate[section][id])
    throw Error('Enregistrer cet appareil ou ce contrôleur avant de tester ses lampes.');
  let ctx = { configuration: candidate, rule: section === 'rules' || section === 'assignments' ? id : null };
  if (section === 'effects') ctx.effect = id;
  if (section === 'devices') {
    ctx.targets = ['device:' + id];
    if (candidate.devices[id]?.kind === 'audio')
      ctx.effect = Object.keys(candidate.effects).find(k => candidate.effects[k].type === 'sound');
    ctx.connectionOnly = true;
  }
  if (section === 'controllers') {
    ctx.targets = Object.entries(candidate.devices)
      .filter(([k, d]) => d.controller === id)
      .map(([k]) => 'device:' + k);
    if (candidate.controllers[id]?.type === 'airplay')
      ctx.effect = Object.keys(candidate.effects).find(k => candidate.effects[k].type === 'sound');
    ctx.connectionOnly = true;
  }
  if (section === 'groups') ctx.targets = ['group:' + id];
  if (section === 'scopes') {
    let current = config;
    config = candidate;
    ctx.targets = [
      ...new Set((candidate.scopes[id] || []).flatMap(k => selectedDevices(['group:' + k]))),
    ].map(k => 'device:' + k);
    config = current;
  }
  if (section === 'sources') ctx.source = id;
  return ctx;
}
function openTest(ctx = { configuration: config }) {
  if (ctx.source) {
    openSourceTest(ctx.source);
    return;
  }
  let cfg = ctx.configuration || config,
    p = $('#previewFields');
  p.replaceChildren();
  $('#previewError').textContent = '';
  help(
    p,
    ctx.source
      ? 'Simule une valeur de cette source pendant 3 secondes. Les seuils audio et la touche se vérifient ensuite avec le moniteur réel.'
      : 'Aperçu des réglages affichés, sans enregistrement. Choisir la fonction et les appareils à tester.',
  );
  if (ctx.connectionOnly)
    help(
      p,
      'Ce test utilise la connexion enregistrée. Enregistrer les changements de connexion avant de tester une nouvelle adresse ou ressource.',
    );
  if (!cfg.rules.length) {
    message('Créer une fonction dans Règles avant de lancer un aperçu.', true);
    return;
  }
  let initial =
      ctx.rule ||
      cfg.rules.find(r => r.effect === ctx.effect || r.sound === ctx.effect)?.id ||
      cfg.rules[0].id,
    choice = field(
      p,
      'Fonction à tester',
      initial,
      'text',
      cfg.rules.map(r => r.id),
    );
  for (let option of p.querySelector('select').options) option.textContent = ruleName(option.value, cfg);
  let body = el('div', null);
  p.append(body);
  let targets, value;
  function update() {
    body.replaceChildren();
    let r = cfg.rules.find(r => r.id === choice()),
      effect = cfg.effects[ctx.effect || r.effect];
    let ids = ctx.targets ? selectedIn(cfg, ctx.targets) : selectedIn(cfg, r.targets),
      kind = effect?.type === 'sound' ? 'audio' : 'light';
    targets = checks(
      body,
      kind === 'audio' ? 'Sorties audio à tester' : 'Lampes à tester',
      Object.entries(cfg.devices)
        .filter(([k, d]) => d.kind === kind)
        .map(([k, d]) => [k, d.name]),
      ids,
    );
    value =
      effect?.type === 'level_map'
        ? field(
            body,
            'Palier à tester',
            Object.keys(effect.map).includes('1') ? '1' : Object.keys(effect.map)[0],
            'text',
            Object.keys(effect.map),
          )
        : ctx.source
          ? field(body, 'Valeur simulée', 1, 'number')
          : () => 1;
    if (kind === 'audio' && !Object.values(cfg.devices).some(d => d.kind === 'audio'))
      help(body, 'Aucune sortie audio configurée. Le son reste désactivé.');
    help(
      body,
      'La fonction testée est activée pour cet aperçu, même si sa condition réelle n’est pas remplie.',
    );
  }
  p.querySelector('select').onchange = update;
  update();
  $('#previewForm').onsubmit = async e => {
    e.preventDefault();
    let submit = e.submitter;
    submit.disabled = true;
    try {
      if (ctx.source) {
        await api('test/source', 'POST', { source: ctx.source, value: Number(value()), seconds: 3 });
      } else {
        await api('test/preview', 'POST', {
          configuration: cfg,
          rule: choice(),
          effect: ctx.effect || null,
          targets: targets().map(k => 'device:' + k),
          value: Number(value()),
        });
      }
      previewDialog.close();
      message('Test en cours pendant 3 secondes, puis retour aux règles normales.');
    } catch (e) {
      $('#previewError').textContent = e.message;
    } finally {
      submit.disabled = false;
    }
  };
  previewDialog.showModal();
}
function selectedIn(cfg, targets) {
  let current = config;
  config = cfg;
  try {
    return selectedDevices(targets);
  } finally {
    config = current;
  }
}
function openSourceTest(id) {
  if (!config.sources[id]) {
    message('Enregistrer cette source avant de tester sa sortie.', true);
    return;
  }
  let p = $('#previewFields');
  p.replaceChildren();
  $('#previewError').textContent = '';
  help(
    p,
    'Simule uniquement la valeur de « ' +
      id +
      ' » pendant trois secondes. Toutes les fonctions liées à cette source utilisent leurs affectations et priorités normales. Aucune commande n’est envoyée au simulateur. Les seuils audio et la touche se vérifient avec le moniteur réel.',
  );
  let value = field(p, 'Valeur simulée', 1, 'number');
  $('#previewForm').onsubmit = async e => {
    e.preventDefault();
    try {
      await api('test/source', 'POST', { source: id, value: value(), seconds: 3 });
      previewDialog.close();
      message('Source simulée pendant 3 secondes, puis retour aux valeurs réelles.');
    } catch (e) {
      $('#previewError').textContent = e.message;
    }
  };
  previewDialog.showModal();
}
async function persist() {
  try {
    await api('config', 'PUT', config);
  } catch (e) {
    config = await api('config');
    throw e;
  }
  config = await api('config');
  message('Configuration enregistrée et appliquée.');
  render();
}
function edit(section, id = null) {
  $('#editorStatus').hidden = true;
  draftPreview = null;
  editing = { section, id };
  let old = id ? (section === 'rules' ? config.rules.find(v => v.id === id) : config[section][id]) : null;
  $('#title').textContent =
    (id ? 'Modifier : ' + (section === 'effects' ? effectTitle(id) : old?.name || id) : 'Ajouter') +
    ' · ' +
    ({
      devices: 'Appareils',
      controllers: 'Contrôleurs',
      groups: 'Groupes',
      scopes: 'Portées',
      sources: 'Sources',
      effects: 'Effets',
      rules: 'Règles',
    }[section] || section);
  let p = $('#fields');
  p.onchange = null;
  p.replaceChildren();
  let key = field(p, 'Identifiant', id || '');
  let read;
  if (section === 'devices') {
    let name = field(p, 'Nom', old?.name || ''),
      driver = field(p, 'Pilote', old?.driver || 'hue', 'text', ['hue', 'nanoleaf', 'airplay', 'mock']),
      controller = field(p, 'Contrôleur', old?.controller || '', 'text', [
        '',
        ...Object.keys(config.controllers),
      ]),
      kind = field(p, 'Type', old?.kind || 'light', 'text', ['light', 'audio']),
      resource = field(p, 'Identifiant de ressource', old?.resource_id || ''),
      stable = field(p, 'Identifiant stable', old?.stable_id || '');
    read = () => ({
      name: name(),
      driver: driver(),
      controller: controller() || null,
      kind: kind(),
      resource_id: resource() || null,
      stable_id: stable() || null,
    });
  }
  if (section === 'controllers') {
    let type = field(p, 'Type', old?.type || 'hue', 'text', ['hue', 'nanoleaf', 'airplay']),
      stable = field(p, 'Identifiant stable', old?.stable_id || ''),
      host = field(p, 'Adresse manuelle (vide : découverte)', old?.host || ''),
      port = field(p, 'Port manuel (0 : automatique)', old?.port || 0, 'number');
    read = () => ({ type: type(), stable_id: stable(), host: host() || null, port: port() || null });
  }
  if (section === 'groups')
    read = checks(
      p,
      'Membres',
      [
        ...Object.entries(config.devices).map(([k, v]) => [k, v.name]),
        ...Object.keys(config.groups)
          .filter(k => k !== id)
          .map(k => ['group:' + k, 'Groupe : ' + k]),
      ],
      old || [],
    );
  if (section === 'scopes')
    read = checks(
      p,
      'Groupes',
      Object.keys(config.groups).map(k => [k, k]),
      old || [],
    );
  if (section === 'sources') {
    let type = field(p, 'Type', old?.type || 'mock', 'text', [
        'mock',
        'lvar',
        'audio_process',
        'simulator_state',
        'keyboard',
      ]),
      name = field(p, 'Variable (pause : paused, état : running)', old?.name || ''),
      poll = field(p, 'Intervalle (ms)', old?.poll_ms ?? 100, 'number'),
      processes = field(p, 'Processus audio (séparés par virgules)', old?.process_names?.join(', ') || ''),
      threshold = field(p, 'Seuil audio (0 à 1)', old?.threshold ?? 0.02, 'number'),
      min = field(p, 'Durée minimale (ms)', old?.min_ms ?? 300, 'number'),
      cooldown = field(p, 'Délai entre contacts (s)', old?.cooldown_s ?? 10, 'number'),
      hold = field(p, 'Maintien du contact (s)', old?.hold_s ?? 5, 'number'),
      keyCode = field(p, 'Code de touche Windows (0 : aucun)', old?.key_code ?? 0, 'number');
    read = () => ({
      type: type(),
      name: name() || null,
      poll_ms: poll(),
      process_names: processes()
        .split(',')
        .map(v => v.trim())
        .filter(Boolean),
      threshold: threshold(),
      min_ms: min(),
      cooldown_s: cooldown(),
      hold_s: hold(),
      key_code: keyCode() || null,
    });
  }
  if (section === 'effects') {
    let type = field(p, 'Type', old?.type || 'static', 'text', [
        'static',
        'blink',
        'pulse',
        'level_map',
        'sound',
      ]),
      body = el('div', null);
    p.append(body);
    let effectRead;
    function build() {
      body.replaceChildren();
      let value = old?.type === type() ? old : {};
      if (type() === 'static') {
        let l = light(body, value.state);
        effectRead = () => ({ type: 'static', state: l() });
      } else if (['blink', 'pulse'].includes(type())) {
        let color = field(
            body,
            'Couleur',
            '#' + (value.color || [255, 0, 0]).map(v => v.toString(16).padStart(2, '0')).join(''),
            'color',
          ),
          frequency = field(
            body,
            type() === 'pulse' ? 'Fréquence des pulsations (Hz)' : 'Fréquence des flashes (Hz)',
            1 / (value.period_s || 1),
            'number',
          ),
          high = field(body, 'Luminosité haute (%)', value.high ?? 100, 'number'),
          low = field(body, 'Luminosité basse (%)', value.low ?? 15, 'number'),
          duty =
            type() === 'blink'
              ? field(body, 'Temps en phase haute (%)', (value.duty ?? 0.5) * 100, 'number')
              : () => 50,
          cycles = field(body, 'Cycles (0 : continu)', value.cycles || 0, 'number');
        effectRead = () => ({
          type: type(),
          color: color()
            .slice(1)
            .match(/../g)
            .map(v => parseInt(v, 16)),
          period_s: 1 / frequency(),
          high: high(),
          low: low(),
          duty: duty() / 100,
          cycles: cycles() || null,
        });
      } else if (type() === 'sound') {
        let file = field(body, 'Fichier WAV dans local/sounds', value.file || 'warning.wav'),
          volume = field(body, 'Volume (%)', (value.volume ?? 0.5) * 100, 'number'),
          repeat = field(body, 'Répétition (s, 0 : unique)', value.repeat_s ?? 0, 'number');
        effectRead = () => ({ type: 'sound', file: file(), volume: volume() / 100, repeat_s: repeat() });
      } else {
        let rows = [];
        function row(k, v) {
          let box = el('div', null, { className: 'card' });
          body.append(box);
          let key = field(box, 'Valeur de source', k),
            l = light(box, v);
          let record = { enabled: true, key, l };
          rows.push(record);
          action(
            'Retirer ce palier',
            () => {
              record.enabled = false;
              box.remove();
            },
            box,
          );
        }
        for (let [k, v] of Object.entries(value.map || {})) row(k, v);
        action('Ajouter un palier', () => row('', {}), body);
        effectRead = () => ({
          type: 'level_map',
          map: Object.fromEntries(rows.filter(v => v.enabled).map(v => [v.key(), v.l()])),
        });
      }
    }
    p.querySelector('select').onchange = build;
    build();
    read = () => {
      let v = effectRead();
      if (['blink', 'pulse'].includes(v.type)) {
        let hz = 1 / v.period_s;
        if (!Number.isFinite(hz) || hz <= 0 || hz > config.settings.max_flash_hz)
          throw Error(
            'Choisir une fréquence supérieure à 0 et au plus égale à ' +
              config.settings.max_flash_hz +
              ' Hz.',
          );
        if (v.low > v.high)
          throw Error('La luminosité basse doit rester inférieure ou égale à la luminosité haute.');
        if (v.duty <= 0 || v.duty >= 1)
          throw Error('Le temps en phase haute doit être strictement compris entre 0 et 100 %.');
      }
      return v;
    };
  }
  if (section === 'rules') {
    let name = field(p, 'Nom de la fonction', old?.name || ''),
      enabled = field(p, 'Activée', old?.enabled ?? true, 'checkbox'),
      priority = field(p, 'Priorité', old?.priority ?? 10, 'number'),
      source = field(p, 'Source pour table de niveaux', old?.source || '', 'text', [
        '',
        ...Object.keys(config.sources),
      ]),
      effect = field(
        p,
        'Effet',
        old?.effect || Object.keys(config.effects)[0],
        'text',
        Object.keys(config.effects),
      ),
      sound = field(p, 'Son associé', old?.sound || '', 'text', [
        '',
        ...Object.entries(config.effects)
          .filter(([k, v]) => v.type === 'sound')
          .map(([k]) => k),
      ]),
      sim = field(p, 'Exiger le simulateur connecté', old?.requires_simulator ?? true, 'checkbox'),
      pause = field(p, 'Suspendre pendant la pause', old?.suspend_when_paused ?? false, 'checkbox'),
      cond = condition(p, old?.condition),
      targets = selectors(p, old?.targets || []);
    read = () => ({
      id: key(),
      name: name() || null,
      enabled: enabled(),
      priority: priority(),
      source: source() || null,
      effect: effect(),
      sound: sound() || null,
      requires_simulator: sim(),
      suspend_when_paused: pause(),
      condition: cond(),
      targets: targets(),
    });
  }
  draftPreview = () => {
    let c = structuredClone(config),
      k = key().trim() || 'new_preview',
      v = read();
    if (section === 'rules') {
      let index = c.rules.findIndex(r => r.id === id);
      if (index >= 0) c.rules[index] = v;
      else c.rules.push(v);
    } else if (!['devices', 'controllers', 'sources'].includes(section)) c[section][k] = v;
    return testContext(section, ['devices', 'controllers', 'sources'].includes(section) ? id : k, c);
  };
  $('#remove').hidden = !id;
  $('#remove').onclick = async () => {
    try {
      if (section === 'rules') config.rules = config.rules.filter(v => v.id !== id);
      else delete config[section][id];
      await persist();
      editor.close();
    } catch (e) {
      config = await api('config');
      message(e.message, true);
    }
  };
  $('#form').onsubmit = async e => {
    e.preventDefault();
    try {
      let k = key().trim();
      if (!k) throw Error('Identifiant requis.');
      if (k !== id && (section === 'rules' ? config.rules.some(v => v.id === k) : k in config[section]))
        throw Error('Identifiant déjà utilisé.');
      let value = read();
      if (section === 'rules') {
        config.rules = config.rules.filter(v => v.id !== id);
        config.rules.push(value);
      } else {
        if (id) delete config[section][id];
        config[section][k] = value;
      }
      await persist();
      editor.close();
    } catch (e) {
      config = await api('config');
      message(e.message, true);
    }
  };
  editor.showModal();
}
let draftPreview = null;
function stopTest() {
  return api('test/stop', 'POST', {}).then(() => message('Test arrêté ; retour aux règles normales.'));
}
function testActions(bar) {
  action('Tester 3 s', () => openTest(tab === 'Réglages' && draftPreview ? draftPreview() : { configuration: config }), bar, '', 'play');
  action('Arrêter le test', stopTest, bar, 'ghost', 'stop');
}
function errorsOf(status) {
  return Object.entries({ ...status?.controller_errors, ...status?.source_errors, ...status?.errors });
}
function dashboard(view) {
  let tiles = el('div', null, { className: 'tiles' }),
    errors = errorsOf(state),
    driven = Object.keys(state?.winners || {}).length;
  view.append(tiles);
  for (let [label, value, kind, note] of [
    ['Simulateur', state?.connected ? 'Connecté' : 'En attente', state?.connected ? 'ok' : 'warn', state?.paused ? 'En pause' : 'Lecture en cours'],
    ['Règles', state?.suspended ? 'Suspendues' : 'Actives', state?.suspended ? 'warn' : 'ok', 'Portée : ' + config.active_scope],
    ['Appareils pilotés', String(driven), driven ? 'ok' : '', (state?.snapshots ?? 0) + ' état(s) sauvegardé(s)'],
    ['Erreurs', String(errors.length), errors.length ? 'danger' : 'ok', errors.length ? 'Voir ci-dessous' : 'Aucune erreur'],
  ]) {
    let tile = el('div', null, { className: 'tile' }),
      strong = el('strong', null);
    strong.append(el('span', null, { className: 'dot ' + kind }), value);
    tile.append(el('span', label), strong, el('small', note));
    tiles.append(tile);
  }
  if (errors.length) {
    let box = el('div', null, { className: 'banner danger' }),
      list = el('div', null);
    for (let [id, error] of errors) list.append(el('div', id + ' : ' + error));
    box.append(list);
    view.append(box);
  }
  let split = el('div', null, { className: 'split' });
  view.append(split);
  let left = el('div', null, { className: 'stack' }),
    right = el('div', null, { className: 'stack' });
  split.append(left, right);
  let active = card(left, 'Fonctions en cours', 'Fonction gagnante et fond fixe par appareil');
  let winners = Object.entries(state?.winners || {});
  if (!winners.length) active.append(el('p', 'Aucune fonction ne pilote actuellement d’appareil.'));
  else {
    let wrap = el('div', null, { className: 'table-wrap' }),
      table = el('table', null);
    table.innerHTML = '<thead><tr><th>Appareil</th><th>Fonction</th><th>Fond</th></tr></thead>';
    let tbody = el('tbody', null);
    for (let [id, rule] of winners) {
      let tr = el('tr', null),
        background = state.backgrounds?.[id];
      tr.append(el('td', config.devices[id]?.name || id), el('td', ruleName(rule)), el('td', background && background !== rule ? ruleName(background) : '—'));
      tbody.append(tr);
    }
    table.append(tbody);
    wrap.append(table);
    active.append(wrap);
  }
  let monitor = card(left, 'Moniteur des sources', 'Valeurs reçues ; un test simule une valeur pendant 3 secondes sans écrire dans le simulateur');
  let wrap = el('div', null, { className: 'table-wrap' }),
    table = el('table', null);
  table.innerHTML = '<thead><tr><th>Source</th><th>Valeur</th><th>Test</th></tr></thead>';
  let tbody = el('tbody', null);
  for (let [key, source] of Object.entries(config.sources)) {
    let tr = el('tr', null),
      name = el('td', key),
      value = el('td', String(state?.values?.[key] ?? '—'), { className: 'value' }),
      test = el('td', null),
      row = el('div', null, { className: 'row' }),
      input = el('input', null, { type: 'number', value: 1, step: 'any', style: 'width:80px' });
    input.setAttribute('aria-label', 'Valeur de test pour ' + key);
    name.append(el('span', OPTION_LABELS[source.type] + (source.name ? ' · ' + source.name : ''), { className: 'sub' }));
    if (source.type === 'audio_process') value.append(el('span', 'Niveau ' + (state?.audio_levels?.[key] ?? 0).toFixed(4), { className: 'sub' }));
    row.append(input);
    action('Tester 3 s', () => api('test/source', 'POST', { source: key, value: Number(input.value), seconds: 3 }), row, 'small ghost', 'play');
    test.append(row);
    tr.append(name, value, test);
    tbody.append(tr);
  }
  table.append(tbody);
  wrap.append(table);
  monitor.append(wrap);
  let control = card(right, 'Portée et règles', 'La portée active détermine les appareils suivis par les fonctions qui l’utilisent');
  let scopes = el('div', null, { className: 'segmented' });
  for (let name of Object.keys(config.scopes)) {
    let b = el('button', name, { type: 'button', className: name === config.active_scope ? 'active' : '' });
    b.onclick = async () => {
      try {
        await api('scope', 'POST', { scope: name });
        config = await api('config');
        message('Portée appliquée.');
        render();
      } catch (e) {
        message(e.message, true);
      }
    };
    scopes.append(b);
  }
  control.append(scopes);
  let bar = cardActions(control);
  action(
    state?.suspended ? 'Reprendre les règles' : 'Suspendre et restaurer les lampes',
    async () => {
      await api('suspend', 'POST', { suspended: !state.suspended });
      await refresh();
      render();
    },
    bar,
    state?.suspended ? 'primary' : '',
  );
  if (VIEWS['Vol en cours']?.summary) VIEWS['Vol en cours'].summary(right);
  help(right, 'Les tests durent 3 secondes et ne sont pas enregistrés. Les priorités des autres fonctions restent actives ; à la fin, les règles reprennent l’état courant du cockpit.');
}
function journal(view) {
  let logs = [...(state?.logs || [])].reverse(),
    c = card(view, 'Événements récents', logs.length + ' entrée(s) conservée(s) en mémoire ; le journal complet reste dans local/logs');
  if (!logs.length) {
    c.append(el('p', 'Aucun événement.'));
    return;
  }
  let wrap = el('div', null, { className: 'table-wrap' }),
    table = el('table', null),
    tbody = el('tbody', null);
  table.innerHTML = '<thead><tr><th>Heure</th><th>Événement</th><th>Détails</th></tr></thead>';
  for (let log of logs) {
    let tr = el('tr', null),
      details = el('td', null);
    if (log.details !== null && log.details !== undefined) {
      let text = typeof log.details === 'string' ? log.details : JSON.stringify(log.details);
      if (text.length > 90) {
        let d = el('details', null);
        d.append(el('summary', text.slice(0, 90) + '…'), el('pre', JSON.stringify(log.details, null, 2), { className: 'json' }));
        details.append(d);
      } else details.append(el('span', text, { className: 'mono' }));
    }
    tr.append(el('td', log.time, { className: 'log-time' }), el('td', log.event), details);
    tbody.append(tr);
  }
  table.append(tbody);
  wrap.append(table);
  c.append(wrap);
}
function settingsView(view) {
  let readers = {},
    grid = el('div', null, { className: 'cards' });
  view.append(grid);
  for (let [key, value] of Object.entries(config.settings))
    if (typeof value === 'number') {
      let box = el('div', null, { className: 'card' });
      grid.append(box);
      readers[key] = field(box, SETTING_LABELS[key] || key, value, 'number');
    }
  let ratesCard = card(view, 'Cadence des pilotes', 'Commandes envoyées par seconde. Pour Hue, elle règle aussi le limiteur du pont ; une valeur trop élevée peut provoquer des erreurs ou du retard.'),
    ratesGrid = el('div', null, { className: 'grid' }),
    rates = {};
  ratesCard.append(ratesGrid);
  for (let key of new Set([...Object.keys(config.settings.driver_rates), ...Object.values(config.devices).map(d => d.driver)]))
    rates[key] = field(ratesGrid, 'Commandes par seconde : ' + key, config.settings.driver_rates[key] || 10, 'number');
  draftPreview = () => {
    let c = structuredClone(config);
    for (let [key, read] of Object.entries(readers)) c.settings[key] = read();
    c.settings.driver_rates = Object.fromEntries(Object.entries(rates).map(([k, v]) => [k, v()]));
    return { configuration: c };
  };
  let bar = el('div', null, { className: 'row' });
  view.append(bar);
  action(
    'Enregistrer les réglages',
    async () => {
      config = draftPreview().configuration;
      await persist();
    },
    bar,
    'primary',
  );
}
function controllerSetup(view) {
  let setup = card(view, 'Découverte et appairage', 'Hue : appuyer sur le bouton du pont pendant l’attente. Nanoleaf : ouvrir Connexion à l’API dans les réglages du constructeur. Les clés restent dans le dossier local.'),
    bar = cardActions(setup);
  action(
    'Découvrir',
    async () => {
      message('Découverte en cours…');
      let r = await api('setup/discover', 'POST', {});
      message(r.services + ' services découverts.');
    },
    bar,
    'small',
  );
  action(
    'Appairer Hue',
    async () => {
      message('Appuyer maintenant sur le bouton du pont Hue.');
      await api('setup/pair', 'POST', { driver: 'hue' });
      message('Pont appairé. Importer les appareils pour les ajouter.');
    },
    bar,
    'small',
  );
  action(
    'Appairer Nanoleaf',
    async () => {
      let model = prompt('Modèle Nanoleaf à sélectionner (vide si un seul contrôleur)');
      if (model === null) return;
      message('Ouvrir maintenant Connexion à l’API dans l’application Nanoleaf.');
      await api('setup/pair', 'POST', { driver: 'nanoleaf', model: model || null });
      message('Contrôleur appairé.');
    },
    bar,
    'small',
  );
  action(
    'Importer les appareils appairés',
    async () => {
      let r = await api('setup/import', 'POST', {});
      config = await api('config');
      message(r.devices + ' appareils importés. Vérifier les groupes et les portées.');
      render();
    },
    bar,
    'small',
  );
}
const SECTIONS = { Appareils: 'devices', Contrôleurs: 'controllers', Groupes: 'groups', Portées: 'scopes', Sources: 'sources', Effets: 'effects', Règles: 'rules' };
function collection(view) {
  if (tab === 'Contrôleurs') controllerSetup(view);
  let section = SECTIONS[tab],
    entries = section === 'rules' ? config.rules.map(v => [v.id, v]) : Object.entries(config[section]),
    cards = el('div', null, { className: 'cards' });
  view.append(cards);
  if (!entries.length) cards.append(el('div', 'Aucun élément. Utiliser « Ajouter » pour commencer.', { className: 'empty' }));
  for (let [id, value] of entries) {
    let title = section === 'effects' ? effectTitle(id) : value.name || id,
      extra = section === 'rules' ? badge(value.enabled ? 'Activée' : 'Désactivée', value.enabled ? 'ok' : '') : null,
      c = card(cards, title, value.name || section === 'effects' ? id : null, extra);
    describeCard(c, section, id, value);
    let bar = cardActions(c);
    action('Modifier', () => edit(section, id), bar, 'small');
    action('Tester 3 s', () => openTest(testContext(section, id)), bar, 'small ghost', 'play');
  }
}
const LIGHTING_VIEWS = {
  'Tableau de bord': ['dashboard', 'État du simulateur, des règles et des sources', dashboard],
  Journal: ['log', 'Derniers événements du moteur et des connexions', journal],
  Affectations: ['assign', 'Chaque fonction possède sa propre sélection ; un groupe suit ses membres, la portée active suit le tableau de bord', assignments],
  Règles: ['rules', 'Conditions, priorités et effets de chaque fonction', collection],
  Effets: ['effects', 'Couleurs, flashes, paliers et sons', collection],
  Sources: ['sources', 'Variables du cockpit, activité audio et touches surveillées', collection],
  Appareils: ['devices', 'Lampes et sorties audio pilotées', collection],
  Contrôleurs: ['controllers', 'Ponts Hue, contrôleurs Nanoleaf et sorties AirPlay', collection],
  Groupes: ['groups', 'Ensembles d’appareils, éventuellement imbriqués', collection],
  Portées: ['scopes', 'Jeux de groupes sélectionnables depuis le tableau de bord', collection],
  Réglages: ['settings', 'Cadences, délais et limites du moteur', settingsView],
};
for (let [name, [iconName, subtitle, renderer]] of Object.entries(LIGHTING_VIEWS))
  VIEWS[name] = { icon: iconName, subtitle, render: renderer, tests: name !== 'Journal', live: ['Tableau de bord', 'Journal'].includes(name) };
function renderNav() {
  let nav = $('#nav');
  nav.replaceChildren();
  for (let [group, names] of NAV) {
    let box = el('div', null, { className: 'nav-group' });
    box.append(el('span', group));
    for (let name of names) {
      let view = VIEWS[name];
      if (!view) continue;
      let b = el('button', null, { type: 'button', className: 'nav-item' + (tab === name ? ' active' : '') });
      b.append(icon(view.icon), el('span', name));
      if (view.navBadge) {
        let extra = view.navBadge();
        if (extra) b.append(extra);
      }
      if (tab === name) b.setAttribute('aria-current', 'page');
      b.onclick = () => {
        tab = name;
        draftPreview = null;
        render();
        window.scrollTo(0, 0);
      };
      box.append(b);
    }
    nav.append(box);
  }
}
function render() {
  let current = VIEWS[tab] || VIEWS['Tableau de bord'];
  if (current.ready && !current.ready()) {
    current.load().then(render).catch(e => message(e.message, true));
    return;
  }
  renderNav();
  $('#pageTitle').textContent = tab;
  $('#pageSubtitle').textContent = current.subtitle || '';
  let bar = $('#pageActions'),
    view = $('#view');
  bar.replaceChildren();
  view.replaceChildren();
  if (SECTIONS[tab]) action('Ajouter', () => edit(SECTIONS[tab]), bar, 'primary');
  if (current.tests) testActions(bar);
  if (current.actions) current.actions(bar);
  current.render(view);
}
function isEditing() {
  let active = document.activeElement;
  return ['INPUT', 'SELECT', 'TEXTAREA'].includes(active?.tagName) || document.querySelector('dialog[open]');
}
async function refresh() {
  let wasTesting = (state?.test_remaining_s || 0) > 0;
  state = await api('status');
  $('#testState').hidden = !(state.test_remaining_s > 0);
  $('#testState').textContent = 'Test en cours : ' + Math.ceil(state.test_remaining_s) + ' s';
  if (!(state.test_remaining_s > 0) && wasTesting) message('Test terminé ; retour aux règles normales.');
  if (connectionLost) {
    connectionLost = false;
    message('Connexion rétablie.');
  }
  setConnection(state.connected ? (state.paused ? 'Simulateur en pause' : 'Simulateur connecté') : 'Simulateur en attente', state.connected ? (state.paused ? 'warn' : 'ok') : 'warn');
  $('#rulesState').textContent = state.suspended ? 'Règles suspendues' : 'Règles actives';
  $('#rulesDot').className = 'dot ' + (state.suspended ? 'warn' : 'ok');
  for (let hook of REFRESH_HOOKS) await hook();
  if (VIEWS[tab]?.live && !isEditing()) render();
  else renderNav();
}
const REFRESH_HOOKS = [];
function scheduleRefresh() {
  setTimeout(async () => {
    try {
      if (!config) config = await api('config');
      await refresh();
    } catch (e) {
      message(e.message, true);
    }
    scheduleRefresh();
  }, config?.settings.ui_refresh_ms ?? 1500);
}
action('Tester 3 s', () => openTest(draftPreview ? draftPreview() : { configuration: config }), $('#form>.row'), '', 'play');
action('Arrêter le test', stopTest, $('#form>.row'), 'ghost', 'stop');
window.addEventListener('DOMContentLoaded', async () => {
  try {
    config = await api('config');
    if (!Object.keys(config.devices).length && !Object.keys(config.controllers).length) tab = 'Contrôleurs';
    await refresh();
    render();
  } catch (e) {
    message(e.message, true);
  } finally {
    scheduleRefresh();
  }
});
