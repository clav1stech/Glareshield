"""Reproducible complete flight: controlled clock, fictional fixtures, no external I/O."""
from copy import deepcopy

import httpx
import pytest

from glareshield.aibridge.scenario import DURATION_S, values
from glareshield.aibridge.service import AIBridge
from glareshield.aibridge.telemetry import TelemetryStore
from glareshield.copilot.contract import PHASE_IDS
from glareshield.copilot.phases import PhaseState
from glareshield.copilot.session import DeclarationInput
from test_copilot_session import first_step, shown
from test_aibridge_web import client_and_headers


class Clock:
    now = 2_000_000_000.
    def __call__(self): return self.now


def offline(root, clock):
    def reject(request): pytest.fail('No external request is permitted in the acceptance scenario')
    transport = httpx.MockTransport(reject)
    bridge = AIBridge(root, clock, transport=transport, network_transport=transport)
    bridge.set_scenario(True, offline_network=True)
    bridge.load_demo_plan()
    return bridge


def test_complete_flight_visits_six_phases_and_prepares_arrival_before_descent(tmp_path):
    clock = Clock()
    bridge = offline(tmp_path, clock)
    service = bridge.sessions
    service.start()
    manual = first_step(service)
    service.set_step(manual, True)
    phases, substates, first_reminders, radio_ids, network_kinds = [], set(), {}, set(), set()
    for elapsed in range(DURATION_S):
        clock.now = 2_000_000_000.+elapsed
        state = service.view()
        phase = state['phase']['effective']['value']
        if not phases or phases[-1] != phase: phases.append(phase)
        substates.add(state['phase']['substate'])
        radio_ids.update(r['id'] for r in state['flight']['radio'])
        for reminder in state['session']['reminder_state']['events'].values():
            first_reminders.setdefault(reminder['rule'], elapsed)
        network_kinds.update(e['kind'] for e in state['network']['events']['events'])
        assert state['network']['simulation'] is True
    assert tuple(phases) == PHASE_IDS
    assert {'taxi','takeoff','approach','landing','parking'} <= substates
    assert state['phase']['substate'] == 'parking'
    assert first_reminders['prepare_arrival'] < 1000
    assert {'descent_started','altitude_10000_up','altitude_10000_down','atis_update','atc_presence'} <= first_reminders.keys()
    assert {'atis_changed','connected','disconnected'} <= network_kinds
    assert {'radio_clearance','radio_takeoff','radio_descent_request','radio_go_around','radio_parked'} <= radio_ids
    assert shown(service, manual)['checked']
    assert bridge.definitions() == {}  # No simulator connection is needed.
    assert bridge.ivao.whazzup.data is None  # The real-network cache was never populated.
    assert bridge.settings.ivao.enabled is False
    assert bridge.snapshot('full')['ivao']['simulation'] is True
    assert all(p.relative_to(tmp_path).parts[0] == 'local' for p in tmp_path.rglob('*') if p.is_file())


@pytest.mark.asyncio
async def test_offline_network_outage_is_not_a_disconnect_and_real_cache_is_separate(tmp_path):
    clock = Clock()
    bridge = offline(tmp_path, clock)
    bridge.sessions.start()
    bridge.sessions.force_phase('cruise')
    clock.now += 1140
    before = bridge.sessions.view()
    assert before['network']['state'] == 'current'
    latest = before['network']['events']['latest_sequence']
    clock.now += 30
    outage = bridge.sessions.view()
    assert outage['network']['state'] == 'stale'
    assert outage['network']['events']['latest_sequence'] == latest
    assert all(r['station']['frequency_mhz'] is None for r in outage['flight']['radio'])
    clock.now += 60
    recovered = bridge.sessions.view()
    assert recovered['network']['state'] == 'current'
    assert recovered['network']['events']['latest_sequence'] == latest
    assert (await bridge.network_cache().refresh())['whazzup']['source'] == 'scenario'
    live_cache = bridge.ivao
    bridge.set_scenario(False)
    assert bridge.network_cache() is live_cache
    assert bridge.sessions.view()['network']['simulation'] is False
    assert bridge.sessions.view()['network']['state'] == 'disabled'


def test_restart_same_corrected_and_new_ofp_and_universe_separation(tmp_path):
    clock = Clock()
    bridge = offline(tmp_path, clock)
    service = bridge.sessions
    session_id = service.start()['session']['id']
    manual = first_step(service)
    service.set_step(manual, True)
    service.force_phase('arrival')
    assert shown(service, 'gear_down')['checked']
    service.set_step('gear_down', False)
    service.declare(DeclarationInput(kind='selection', field='selection.runway', value='27',
        reference='Piste fictive choisie', context={'stage':'arrival'}))
    restarted = AIBridge(tmp_path, clock)
    restarted.set_scenario(True, offline_network=True)
    view = restarted.sessions.view()
    assert view['session']['id'] == session_id
    assert shown(restarted.sessions, manual)['checked']
    assert not shown(restarted.sessions, 'gear_down')['checked']
    plan = deepcopy(restarted.plan.plan)
    restarted.plan.store(plan, 'demo')
    assert restarted.sessions.view()['session']['id'] == session_id
    plan['route'] = 'DCT FICTIONAL DCT'
    restarted.plan.store(plan, 'demo')
    assert restarted.sessions.view()['session']['declarations'][0]['invalidated_reason']
    plan['ofp_id'] = 'fictional-next-acceptance-flight'
    restarted.plan.store(plan, 'demo')
    new = restarted.sessions.view()
    assert new['session']['id'] != session_id and new['session']['steps'] == {}
    restarted.set_scenario(False)
    assert restarted.sessions.view()['session'] is None
    with pytest.raises(ValueError): restarted.sessions.start()


def test_pause_reconnect_forced_then_automatic_and_go_around_keep_manual_gestures(tmp_path):
    clock = Clock()
    bridge = offline(tmp_path, clock)
    service = bridge.sessions
    service.start()
    service.force_phase('arrival')
    service.set_step('gear_down', False)
    # Seed a resumed airborne phase, then use only numeric/bool telemetry as evidence.
    service.documents['demo'].sessions[-1].phase_state = PhaseState(
        phase='arrival', confirmed=True, cruise_seen=True, airborne_seen=True)
    store = TelemetryStore('scenario', clock)
    bridge.store = lambda: store
    def feed(paused=False, connected=True):
        data = {**values(1390), 'vertical_speed': 1500.}
        store.update({'connected':connected, 'paused':paused,
                      'telemetry':{k:(v,clock.now) for k,v in data.items()}})
    feed(); service.force_phase(None)
    for _ in range(12):
        clock.now += 1; feed(); view = service.view()
    assert view['phase']['effective']['value'] == 'arrival'
    assert view['phase']['substate'] == 'go_around'
    service.declare(DeclarationInput(kind='event', field='event.go_around', value=True,
        reference='Remise des gaz fictive', context={'stage':'arrival'}))
    assert service.view()['flight']['radio'][0]['id'] == 'radio_go_around'
    clock.now += 1; feed(paused=True)
    assert service.view()['phase']['suspended']
    assert not shown(service, 'gear_down')['detection_current']
    clock.now += 20; feed(connected=False)
    assert not shown(service, 'gear_down')['checked']
    clock.now += 1; feed()
    assert shown(service, 'gear_down')['provenance'] == 'manual'
    assert not shown(service, 'gear_down')['checked']
    assert shown(service, 'gear_down')['conflict']


def test_offline_scenario_api_keeps_configuration_and_requires_session_token(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    before = runtime.ai.settings.model_dump()
    assert client.post('/api/ai/scenario', json={'active':True, 'offline_network':True}).status_code == 403
    assert client.post('/api/ai/scenario', json={'active':True, 'offline_network':True}, headers=headers).status_code == 200
    assert client.post('/api/ai/simbrief/demo', headers=headers).status_code == 200
    assert client.get('/api/ai/ivao', headers=headers).json()['simulation']
    assert client.post('/api/ai/ivao/refresh', headers=headers).status_code == 200
    assert runtime.ai.settings.model_dump() == before
