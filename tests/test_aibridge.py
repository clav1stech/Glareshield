import json
import math
from pathlib import Path

import httpx
import pytest

from glareshield.aibridge.catalog import STANDARD, STANDARD_KEYS
from glareshield.aibridge.config import AIBridgeSettings, LVarEntry, load_settings, save_settings
from glareshield.aibridge.context import LIMITS, build_context, chat_text, serialize
from glareshield.aibridge.scenario import DURATION_S, PHASES, values
from glareshield.aibridge.service import AIBridge
from glareshield.aibridge.simbrief import FlightPlanStore, OFPError, parse_ofp
from glareshield.aibridge.telemetry import TelemetryStore, qualify

DEMO = Path(__file__).resolve().parents[1]/'src/glareshield/aibridge/demo_ofp.json'


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def entry(key):
    return next(item for item in STANDARD if item.key == key)


def test_catalog_keys_are_unique_and_standard_simvars_have_units():
    assert len(STANDARD_KEYS) == len(STANDARD)
    for item in STANDARD:
        assert item.origin == 'simvar' and item.variable == item.variable.upper()
        assert item.sim_unit and item.interval_ms >= 250 and item.max_age_s*1000 > item.interval_ms


def test_field_statuses_distinguish_observed_stale_unavailable():
    clock = Clock()
    store = TelemetryStore('simconnect', clock)
    altitude = entry('altitude_msl')
    assert qualify(altitude, store)['status'] == 'unavailable'
    store.update({'connected': True, 'paused': False, 'telemetry': {'altitude_msl': (12345.6, clock.now)}})
    field = qualify(altitude, store)
    assert field['value'] == 12346 and field['unit'] == 'ft' and field['status'] == 'observed'
    clock.now += altitude.max_age_s+1
    assert qualify(altitude, store)['status'] == 'stale'
    store.update({'connected': False, 'paused': False, 'values': {}})
    field = qualify(altitude, store)
    assert field['status'] == 'stale' and field['reason'] == 'Simulateur déconnecté'


def test_invalid_or_missing_values_are_never_zero():
    clock = Clock()
    store = TelemetryStore('simconnect', clock)
    store.update({'connected': True, 'telemetry': {'ias': (math.nan, clock.now), 'mach': ('bad', clock.now),
                                                   'ground_speed': 'malformed'},
                  'telemetry_errors': {'vertical_speed': 'Aucune donnée reçue'}})
    assert qualify(entry('ias'), store)['value'] is None
    assert qualify(entry('mach'), store)['status'] == 'unavailable'
    assert qualify(entry('ground_speed'), store)['status'] == 'unavailable'
    assert qualify(entry('vertical_speed'), store)['reason'] == 'Aucune donnée reçue'


def test_lvar_meaning_and_verification_are_exported():
    settings = AIBridgeSettings(enabled=True, lvars=[LVarEntry(key='demo_switch', name='DEMO_SWITCH',
                                label='Interrupteur fictif', values={'1': 'ON'})], validated=['ias'])
    lvar = settings.lvars[0].entry()
    assert lvar.definition() == {'name': 'L:DEMO_SWITCH', 'unit': 'Number', 'interval_ms': 1000,
                                 'kind': 'number', 'origin': 'lvar'}
    clock = Clock()
    store = TelemetryStore('simconnect', clock)
    store.update({'connected': True, 'telemetry': {'demo_switch': (1.0, clock.now)}})
    document = build_context('detailed', [lvar], store, None, {}, clock.now)
    field = document['telemetry']['fenix']['demo_switch']
    assert field['meaning'] == 'ON' and field['verification'] == 'configured_unverified'
    assert field['source'] == 'LVar DEMO_SWITCH'


def test_settings_validation_and_private_round_trip(tmp_path):
    path = tmp_path/'local/ai-bridge.yaml'
    assert load_settings(path) == AIBridgeSettings()
    with pytest.raises(ValueError):
        AIBridgeSettings(disabled=['unknown'])
    with pytest.raises(ValueError):
        AIBridgeSettings(lvars=[LVarEntry(key='ias', name='X', label='X')])
    with pytest.raises(ValueError):
        AIBridgeSettings(simbrief_user='pilot', simbrief_kind='userid')
    saved = save_settings(path, AIBridgeSettings(enabled=True, simbrief_user='demo-pilot'))
    assert load_settings(path) == saved


def test_scenario_is_continuous_and_plausible():
    assert PHASES[0][1] == 0 and PHASES[-1][2] == DURATION_S
    for (_, _, end), (_, start, _) in zip(PHASES, PHASES[1:]):
        assert end == start
    previous = values(0)
    for t in range(1, DURATION_S):
        current = values(t)
        assert abs(current['altitude_msl']-previous['altitude_msl']) < 200
        assert current['ias'] >= 0 and 0 <= current['heading_magnetic'] < 360
        previous = current
    cruise = values(800)
    assert cruise['altitude_msl'] == 35000 and 0.7 < cruise['mach'] < 0.85 and not cruise['on_ground']


def test_demo_ofp_summary_is_planned_and_complete():
    plan = parse_ofp(json.loads(DEMO.read_text(encoding='utf-8')))
    assert plan['nature'] == 'planned'
    assert plan['origin']['icao'] == 'XXPO' and plan['destination']['runway'] == '04R'
    assert plan['alternates'][0]['icao'] == 'XXMA' and plan['weight_unit'] == 'kg'
    assert plan['fuel']['ramp'] == 6200 and plan['times']['enroute_min'] == 73
    assert plan['waypoints_total'] == len(plan['waypoints']) == 9
    assert 'iata' not in plan['origin']


def test_ofp_errors_are_explicit():
    with pytest.raises(OFPError):
        parse_ofp([])
    with pytest.raises(OFPError, match='Unknown'):
        parse_ofp({'fetch': {'status': 'Error: Unknown UserID'}})
    with pytest.raises(OFPError, match='incomplet'):
        parse_ofp({'fetch': {'status': 'Success'}, 'origin': {'icao_code': 'XXAA'}})


async def test_simbrief_refresh_failures_keep_previous_plan_flagged(tmp_path):
    data = json.loads(DEMO.read_text(encoding='utf-8'))
    responses = []

    def handler(request):
        assert request.url.params['json'] == 'v2' and request.url.params['username'] == 'demo-pilot'
        return responses.pop(0)

    clock = Clock(1791874800+3600)
    store = FlightPlanStore(tmp_path/'local/state/ofp.json', clock, httpx.MockTransport(handler))
    with pytest.raises(OFPError, match='identifiant'):
        await store.refresh(None)
    responses.append(httpx.Response(200, json=data))
    await store.refresh('demo-pilot')
    assert store.describe(12)['available'] and not store.describe(12)['warnings']
    clock.now += 5
    with pytest.raises(OFPError, match='Patienter'):
        await store.refresh('demo-pilot')
    clock.now += 60
    responses.append(httpx.Response(400, json={'fetch': {'status': 'Error: Unknown UserID'}}))
    with pytest.raises(OFPError, match='Unknown UserID'):
        await store.refresh('demo-pilot')
    described = store.describe(12)
    assert described['available'] and 'plan précédent conservé' in ' '.join(described['warnings'])
    clock.now += 60
    responses.append(httpx.Response(200, text='<html>'))
    with pytest.raises(OFPError):
        await store.refresh('demo-pilot')
    clock.now += 60

    def offline(request):
        raise httpx.ConnectError('offline')
    store.transport = httpx.MockTransport(offline)
    with pytest.raises(OFPError, match='Réseau'):
        await store.refresh('demo-pilot')
    clock.now += 24*3600
    assert any('OFP généré' in item for item in store.describe(12)['warnings'])
    reloaded = FlightPlanStore(tmp_path/'local/state/ofp.json', clock)
    assert reloaded.plan == store.plan


def test_context_levels_differ_and_stay_within_limits(tmp_path):
    clock = Clock()
    bridge = AIBridge(tmp_path, clock)
    bridge.set_scenario(True)
    bridge.scenario.started -= 800
    bridge.load_demo_plan()
    essential, detailed = bridge.snapshot('essential'), bridge.snapshot('detailed')
    assert essential['data_origin'] == 'simulation_scenario'
    assert all(field['status'] == 'simulated' for group in essential['telemetry'].values() for field in group.values())
    assert 'waypoints' not in essential['flight_plan'] and detailed['flight_plan']['waypoints']
    assert 'tas' in detailed['telemetry']['speed'] and 'tas' not in essential['telemetry']['speed']
    assert len(serialize(essential)) < len(serialize(detailed)) <= LIMITS['detailed']
    assert essential['derived']['direct_distance_to_destination']['status'] == 'derived'
    text = chat_text(essential)
    assert text.count('```') == 2 and json.loads(text.split('```json\n')[1].split('\n```')[0]) == essential


def test_waypoints_are_truncated_explicitly(tmp_path):
    clock = Clock()
    plan = parse_ofp(json.loads(DEMO.read_text(encoding='utf-8')))
    plan['waypoints'] = plan['waypoints']*20
    document = build_context('detailed', list(STANDARD), TelemetryStore('simconnect', clock), plan, {}, clock.now)
    from glareshield.aibridge import context
    trimmed = context.limit(document, 4000)
    assert trimmed['flight_plan']['waypoints_truncated'] is True


def test_disconnected_snapshot_has_no_fake_telemetry(tmp_path):
    bridge = AIBridge(tmp_path, Clock())
    document = bridge.snapshot('essential')
    assert document['telemetry'] == {} and document['simulator']['connected'] is False
    assert set(document['unavailable']) == {item.key for item in STANDARD if item.level == 'essential'}
    assert document['flight_plan'] is None
    assert any('non connecté' in check['message'] for check in document['checks'])


def test_disabled_bridge_requests_nothing_and_ignores_messages(tmp_path):
    bridge = AIBridge(tmp_path, Clock())
    assert bridge.definitions() == {}
    bridge.on_simulator_message({'connected': True, 'telemetry': {'ias': (250.0, 1)}})
    assert bridge.live.samples == {}
    calls = []
    bridge.listeners.append(lambda: calls.append(True))
    bridge.save(AIBridgeSettings(enabled=True, disabled=['tas']))
    assert calls and 'tas' not in bridge.definitions() and 'ias' in bridge.definitions()


def test_plan_mismatch_on_ground_is_reported(tmp_path):
    clock = Clock()
    bridge = AIBridge(tmp_path, clock)
    bridge.settings = AIBridgeSettings(enabled=True)
    bridge.load_demo_plan()
    bridge.on_simulator_message({'connected': True, 'telemetry': {
        'latitude': (10.0, clock.now), 'longitude': (10.0, clock.now), 'on_ground': (1.0, clock.now)}})
    assert any('30 NM' in check['message'] for check in bridge.snapshot()['checks'])


def test_export_file_stays_under_local(tmp_path):
    bridge = AIBridge(tmp_path, Clock())
    bridge.set_scenario(True)
    path = bridge.export('detailed')
    assert path.parent == tmp_path/'local/exports' and path.name.endswith('-detailed-simulation.json')
    assert json.loads(path.read_text(encoding='utf-8'))['level'] == 'detailed'


def test_invalid_private_settings_disable_module_without_raising(tmp_path):
    (tmp_path/'local').mkdir()
    (tmp_path/'local/ai-bridge.yaml').write_text('enabled: true\nunknown: 1\n', encoding='utf-8')
    bridge = AIBridge(tmp_path, Clock())
    assert bridge.definitions() == {} and bridge.status()['settings_error']
