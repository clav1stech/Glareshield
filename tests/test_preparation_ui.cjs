// Run with node; optional browser pass: NODE_PATH=<playwright install>/node_modules node ... --browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({
  $: () => ({}), VIEWS: {},
});
vm.runInContext(fs.readFileSync('src/glareshield/static/copilot.js', 'utf8'), context);
const prepare = context.preparationStatus;
const settings = { devices: { lamp: { kind: 'light', driver: 'mock' } } };
const live = { enabled: true, connected: true, counts: { observed: 2 }, plan: { available: false }, ivao: { enabled: false } };
const runtime = { simulator: { enabled: true, connected: true } };
let result = prepare(live, runtime, settings);
assert.equal(result.blockers.length, 0, 'Missing OFP, IVAO and lamps do not block telemetry');
assert.equal(result.lighting.label, 'Démonstration');
assert.equal(result.simulator.label, 'Connecté');
assert.equal(prepare(live, { connected: true }, settings).simulator.label, 'Désactivé');
assert.equal(prepare({ ...live, enabled: false }, runtime, settings).bridge.label, 'Désactivé');
assert.equal(prepare({ ...live, settings_error: 'Invalid' }, runtime, settings).bridge.label, 'Erreur');
assert.equal(prepare({ ...live, counts: { stale: 2 } }, runtime, settings).bridge.label, 'Périmé');
assert.equal(prepare({ ...live, counts: {}, telemetry_errors: 1 }, runtime, settings).bridge.label, 'Erreur');
assert.equal(prepare({ ...live, counts: {}, connected: true }, runtime, settings).bridge.label, 'En attente');
assert.equal(prepare(live, { simulator: { enabled: true, connected: true, stale: true } }, settings).simulator.label, 'Périmé');
assert.equal(prepare(live, { simulator: { enabled: true, error: 'FixtureError' } }, settings).simulator.label, 'Erreur');
assert.equal(prepare(live, { simulator: { enabled: true, connected: true, paused: true } }, settings).blockers.length, 1);
result = prepare({ ...live, mode: 'scenario' }, {}, settings);
assert.equal(result.bridge.label, 'Démonstration');
assert.equal(result.simulator.label, 'Désactivé', 'Demo never claims a real simulator connection');
assert.equal(result.demo, true);
assert.match(result.warnings[0], /Démonstration/);
for (const [plan, label] of [
  [{ available: true, source: 'demo' }, 'Démonstration'],
  [{ available: true, error: 'Import failed' }, 'Erreur'],
  [{ available: true, warnings: ['Old OFP'] }, 'Périmé / à vérifier'],
  [{ available: true, source: 'simbrief', fetched_age_min: 1 }, 'Chargé'],
]) assert.equal(prepare({ ...live, plan }, runtime, settings).simbrief.label, label);
for (const [ivao, label] of [
  [{ enabled: false }, 'Désactivé'],
  [{ enabled: true, feeds: { whazzup: 'unavailable' } }, 'En attente'],
  [{ enabled: true, feeds: { whazzup: 'stale' } }, 'Périmé'],
  [{ enabled: true, feed_errors: { whazzup: 'FixtureError' } }, 'Erreur'],
  [{ enabled: true, feeds: { whazzup: 'current', metar: 'current', taf: 'current' } }, 'Connecté'],
]) {
  result = prepare({ ...live, ivao }, runtime, { devices: {} });
  assert.equal(result.ivao.label, label);
  assert.equal(result.blockers.length, 0);
}
assert.equal(prepare(live, runtime, { devices: { lamp: { kind: 'light', driver: 'hue' } } }).lighting.label, 'Configuré');
result = prepare(live, runtime, settings, true);
for (const key of ['simulator', 'bridge', 'simbrief', 'ivao', 'lighting']) assert.equal(result[key].label, 'Indisponible');
assert.ok(result.blockers.length);
console.log('Preparation state tests passed.');

async function browserPass() {
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const base = 'http://127.0.0.1:18762';
  try {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: async text => { window.testCopiedText = text; } } });
    });
    await page.goto(base);
    await page.getByRole('heading', { name: 'Préparer le vol', exact: true }).waitFor();
    const before = await (await page.request.get(base+'/test/identity')).json();
    assert.equal(await page.locator('#nav button').count(), 3);
    assert.equal(await page.getByRole('button', { name: 'Démarrer le suivi du vol', exact: true }).isDisabled(), false);
    const notes = page.getByRole('textbox', { name: 'Notes pilote', exact: true });
    await notes.fill('Déclaration fictive : piste à confirmer.');
    await page.getByRole('button', { name: 'Enregistrer les notes', exact: true }).click();
    await page.getByText('Notes enregistrées.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Importer depuis SimBrief', exact: true }).click();
    await page.getByText('OFP importé.', { exact: true }).waitFor();
    await page.locator('.route').first().waitFor();
    await page.getByRole('button', { name: 'Démarrer le suivi du vol', exact: true }).click();
    await page.getByRole('heading', { name: 'Suivi du vol', exact: true }).waitFor();
    const firstStep = page.locator('#view input[type=checkbox]').first();
    const stepLabel = await firstStep.getAttribute('aria-label');
    await firstStep.check();
    await page.getByText('Manuel', { exact: false }).first().waitFor();
    await page.getByLabel('Phase', { exact: true }).selectOption('cruise');
    // The draft must survive a poll or unrelated render before explicit save.
    await page.evaluate(() => render());
    assert.equal(await page.getByLabel('Phase', { exact: true }).inputValue(), 'cruise');
    await page.getByRole('button', { name: 'Enregistrer la phase', exact: true }).click();
    const selection = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Déclarer la piste ou l’approche retenue' }) });
    await selection.locator('summary').click();
    await selection.getByLabel('Valeur déclarée', { exact: true }).fill('27');
    await selection.getByLabel('Référence (EFB, ATC ou bulletin)', { exact: true }).fill('Briefing fictif');
    await selection.getByRole('button', { name: 'Enregistrer : Déclarer la piste ou l’approche retenue', exact: true }).click();
    await page.getByText('Choix · Piste : 27', { exact: false }).waitFor();
    await page.screenshot({ path: 'local/ui-test/flight-session.png', fullPage: true, animations: 'disabled' });
    await page.reload();
    await page.locator('#nav').getByRole('button', { name: 'Vol', exact: true }).click();
    await page.getByRole('heading', { name: 'Suivi du vol', exact: true }).waitFor();
    assert.equal(await page.getByLabel('Phase', { exact: true }).inputValue(), 'cruise');
    await page.locator('summary').filter({ hasText: 'Prévol' }).click();
    assert.equal(await page.getByRole('checkbox', { name: stepLabel, exact: true }).isChecked(), true);
    await page.getByRole('checkbox', { name: stepLabel, exact: true }).uncheck();
    await page.getByRole('button', { name: 'Terminer le suivi', exact: true }).click();
    await page.getByRole('button', { name: 'Reprendre le suivi', exact: true }).click();
    await page.locator('summary').filter({ hasText: 'Prévol' }).click();
    assert.equal(await page.getByRole('checkbox', { name: stepLabel, exact: true }).isChecked(), false);
    await page.getByText('Choix · Piste : 27', { exact: false }).waitFor();
    const names = await page.evaluate(() => SETTINGS.flatMap(([, pages]) => pages));
    await page.waitForTimeout(1200);
    assert.match(await page.locator('#flightPhase').textContent(), /Croisière.*Déclarée/);
    await page.getByRole('button', { name: 'Revenir en automatique', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#flightPhase').textContent.includes('Prévol'));
    assert.match(await page.locator('#flightPhase').textContent(), /Prévol.*Calculée/);
    assert.equal(await page.getByLabel('Phase', { exact: true }).inputValue(), 'automatic');
    assert.equal(await page.getByRole('checkbox', { name: stepLabel, exact: true }).isChecked(), false);
    await page.getByText('Prochain déclencheur :', { exact: false }).waitFor();
    await page.screenshot({ path: 'local/ui-test/flight-phase-automatic.png', fullPage: true, animations: 'disabled' });
    await page.locator('#nav').getByRole('button', { name: 'Réglages', exact: true }).click();
    for (const name of names) {
      await page.locator('#settingsNav').getByRole('button', { name, exact: true }).click();
      await page.waitForFunction(name => document.querySelector('#pageTitle').textContent === name, name);
      assert.ok(await page.locator('#view').textContent(), name+' is accessible');
      if (name === 'Export IA') {
        await page.getByRole('button', { name: 'Copier le JSON seul', exact: true }).click();
        await page.waitForFunction(() => typeof window.testCopiedText === 'string');
        const exported = await page.evaluate(() => JSON.parse(window.testCopiedText));
        assert.equal(exported.schema, 'glareshield.flight_context/3');
        assert.equal(exported.pilot_notes.text, 'Déclaration fictive : piste à confirmer.');
        await page.getByRole('button', { name: 'Enregistrer dans local/exports', exact: true }).click();
        await page.getByText('Fichier enregistré :', { exact: false }).waitFor();
        const download = page.waitForEvent('download');
        await page.getByRole('button', { name: 'Télécharger le fichier JSON', exact: true }).click();
        assert.match((await download).suggestedFilename(), /^flight-context-.*\.json$/);
      }
    }
    await page.locator('#settingsNav').getByRole('button', { name: 'Affichage', exact: true }).click();
    await page.getByLabel('Thème', { exact: true }).selectOption('light');
    await page.getByLabel('Taille du texte', { exact: true }).selectOption('extra');
    await page.getByRole('button', { name: 'Appliquer l’affichage', exact: true }).click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
    assert.equal(await page.locator('html').getAttribute('data-text-size'), 'extra');
    await page.reload();
    await page.getByRole('heading', { name: 'Préparer le vol', exact: true }).waitFor();
    assert.equal(await notes.inputValue(), 'Déclaration fictive : piste à confirmer.');
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: 'local/ui-test/preparation-light.png', fullPage: true, animations: 'disabled' });
    await page.locator('#themeButton').click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: 'local/ui-test/preparation-dark.png', fullPage: true, animations: 'disabled' });
    // Focus survives polling; Enter opens the mode and moves focus to its title.
    const flight = page.locator('#nav').getByRole('button', { name: 'Vol', exact: true });
    await flight.focus();
    await page.waitForTimeout(1800);
    assert.equal(await flight.evaluate(el => el === document.activeElement), true);
    await page.keyboard.press('Enter');
    await page.getByRole('heading', { name: 'Suivi du vol', exact: true }).waitFor();
    assert.equal(await page.locator('#pageTitle').evaluate(el => el === document.activeElement), true);
    await page.getByRole('button', { name: 'Retour à l’initialisation', exact: true }).click();
    await notes.fill('Brouillon fictif non enregistré.');
    await page.locator('#nav').getByRole('button', { name: 'Vol', exact: true }).click();
    await page.getByRole('button', { name: 'Retour à l’initialisation', exact: true }).click();
    assert.equal(await notes.inputValue(), 'Brouillon fictif non enregistré.');
    await page.setViewportSize({ width: 780, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: 'local/ui-test/preparation-mobile.png', fullPage: true, animations: 'disabled' });
    await page.locator('#nav').getByRole('button', { name: 'Vol', exact: true }).click();
    await page.getByRole('button', { name: 'Retour à l’initialisation', exact: true }).click();
    await page.route('**/api/status', route => route.abort());
    await page.locator('#connectionNotice').waitFor({ state: 'visible' });
    await page.getByRole('heading', { name: 'Simulateur', exact: true }).locator('../..').getByText('Indisponible', { exact: true }).waitFor();
    await page.unroute('**/api/status');
    await page.locator('#connectionNotice').waitFor({ state: 'hidden' });
    const after = await (await page.request.get(base+'/test/identity')).json();
    assert.deepEqual(after, before, 'Mode, display, imports and notes preserve runtime resources');
    assert.deepEqual(errors, []);
    console.log('Browser navigation, notes, import, display, keyboard and runtime preservation passed.');
  } finally { await browser.close(); }
}
if (process.argv.includes('--browser')) browserPass().catch(error => { console.error(error); process.exitCode = 1; });
