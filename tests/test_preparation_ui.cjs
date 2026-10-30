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
assert.equal(prepare({...live, ivao:{enabled:true, simulation:true, feeds:{whazzup:'current'}}}, runtime, settings).ivao.label, 'Démonstration');
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
  const base = process.env.GLARESHIELD_TEST_URL || 'http://127.0.0.1:18762';
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
    await page.locator('#flightDashboard').waitFor();
    const firstStep = page.locator('#flightDashboard input[type=checkbox]').first();
    const stepLabel = await firstStep.getAttribute('aria-label');
    await firstStep.check();
    await page.waitForFunction(label => ai.session.groups.some(g => g.steps.some(s => s.label === label && s.checked)), stepLabel);
    // Polling rebuilds Vol but keeps keyboard focus and never moves a target during a click.
    await firstStep.focus();
    await page.evaluate(() => refresh());
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), stepLabel);
    const box = await firstStep.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.evaluate(() => refresh());
    assert.deepEqual(await firstStep.boundingBox(), box, 'Polling cannot move a target during a click');
    await page.mouse.up();
    await firstStep.uncheck();
    await firstStep.check();
    // Unknown values are typed in place; a poll does not interrupt typing.
    await page.locator('[data-key="val-cleared_altitude"]').first().click();
    const typed = page.locator('.fl-edit');
    await typed.fill('5000');
    await page.evaluate(() => refresh());
    assert.equal(await typed.inputValue(), '5000');
    await typed.press('Enter');
    await page.waitForFunction(() => ai.session.flight.values.cleared_altitude.value === 5000);
    assert.match(await page.locator('[data-key="val-cleared_altitude"]').first().textContent(), /5.000 ft/);
    // Demo flight in cruise: stage-driven guidance, radio copied without emission.
    await page.evaluate(async () => {
      await api('ai/scenario', 'POST', {active:true, phase:'cruise', offline_network:true});
      await api('ai/simbrief/demo', 'POST', {});
      let state = await api('ai/session');
      await api('ai/session/start', 'POST', {session_id:state.session?.id || null, universe:state.universe});
      await reloadAI();
    });
    await page.waitForFunction(() => ai.session?.cockpit?.stage === 'cruise' && $('#flightDashboard'), null, { timeout: 15000 });
    await page.waitForFunction(() => document.querySelector('.fl-leg[aria-current="step"] .fl-legname')?.textContent === 'Croisière');
    assert.equal(await page.locator('.fl-big').textContent(), 'Préparer l’arrivée avant le TOD');
    assert.equal(await page.locator('#ivaoState').textContent(), 'IVAO · Démonstration');
    const beforeCopy = await page.evaluate(async () => (await api('ai/session')).session.history);
    await page.locator('[data-key^="copy-"]').first().click();
    assert.equal(await page.evaluate(() => window.testCopiedText), await page.locator('.fl-msg').first().textContent());
    assert.deepEqual(await page.evaluate(async () => (await api('ai/session')).session.history), beforeCopy, 'Copy does not emit or check');
    await page.screenshot({path:'local/ui-test/radio-copy.png', animations:'disabled'});
    // Another phase is previewed first; the correction is an explicit second gesture.
    await page.locator('[data-key="leg-descent"]').click();
    await page.getByText('Aperçu de la phase Descente', { exact: false }).waitFor();
    assert.equal(await page.evaluate(() => ai.session.phase.phase), 'cruise');
    await page.getByRole('button', { name: 'Je suis en Descente', exact: true }).click();
    await page.waitForFunction(() => ai.session.phase.phase === 'descent' && ai.session.phase.mode === 'manual');
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => saveDisplay({ theme, text_size: 'standard' }), theme);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: 'local/ui-test/flight-'+theme+'.png', fullPage: true, animations: 'disabled' });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    }
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.screenshot({ path: 'local/ui-test/flight-1920.png', animations: 'disabled' });
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.evaluate(async () => {
      await api('ai/scenario', 'POST', {active:false});
      await reloadAI();
    });
    // Back to the SimConnect universe: gestures persisted across reload, end and resume.
    await page.reload();
    await page.locator('#nav').getByRole('button', { name: 'Vol', exact: true }).click();
    await page.locator('#flightDashboard').waitFor();
    assert.equal(await page.getByRole('checkbox', { name: stepLabel, exact: true }).isChecked(), true);
    await page.getByRole('checkbox', { name: stepLabel, exact: true }).uncheck();
    await page.waitForFunction(label => ai.session.groups.some(g => g.steps.some(s => s.label === label && !s.checked)), stepLabel);
    await page.getByRole('button', { name: 'Terminer le suivi', exact: true }).click();
    await page.getByRole('button', { name: 'Reprendre le suivi', exact: true }).click();
    await page.locator('#flightDashboard').waitFor();
    assert.equal(await page.getByRole('checkbox', { name: stepLabel, exact: true }).isChecked(), false);
    assert.match(await page.locator('[data-key="val-cleared_altitude"]').first().textContent(), /5.000 ft/);
    await page.screenshot({ path: 'local/ui-test/flight-session.png', fullPage: true, animations: 'disabled' });
    const names = await page.evaluate(() => SETTINGS.flatMap(([, pages]) => pages));
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
    await page.locator('#flightDashboard').waitFor();
    assert.equal(await page.locator('#pageTitle').evaluate(el => el === document.activeElement), true);
    await page.locator('#nav').getByRole('button', { name: 'Initialisation', exact: true }).click();
    await notes.fill('Brouillon fictif non enregistré.');
    await page.locator('#nav').getByRole('button', { name: 'Vol', exact: true }).click();
    await page.locator('#nav').getByRole('button', { name: 'Initialisation', exact: true }).click();
    assert.equal(await notes.inputValue(), 'Brouillon fictif non enregistré.');
    await page.setViewportSize({ width: 780, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: 'local/ui-test/preparation-mobile.png', fullPage: true, animations: 'disabled' });
    await page.locator('#nav').getByRole('button', { name: 'Vol', exact: true }).click();
    await page.locator('#flightDashboard').waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: 'local/ui-test/flight-mobile.png', fullPage: true, animations: 'disabled' });
    await page.locator('#nav').getByRole('button', { name: 'Initialisation', exact: true }).click();
    await page.route('**/api/status', route => route.abort());
    await page.locator('#connectionNotice').waitFor({ state: 'visible' });
    await page.getByRole('heading', { name: 'Simulateur', exact: true }).locator('../..').getByText('Indisponible', { exact: true }).waitFor();
    await page.unroute('**/api/status');
    await page.locator('#connectionNotice').waitFor({ state: 'hidden' });
    const after = await (await page.request.get(base+'/test/identity')).json();
    assert.deepEqual(after, before, 'Mode, display, imports and notes preserve runtime resources');
    assert.deepEqual(errors, []);
    console.log('Browser navigation, notes, import, display, keyboard and runtime preservation passed.');
  } catch (error) {
    await page.screenshot({ path: 'local/ui-test/failure.png', fullPage: true }).catch(() => {});
    throw error;
  } finally { await browser.close(); }
}
if (process.argv.includes('--browser')) browserPass().catch(error => { console.error(error); process.exitCode = 1; });
