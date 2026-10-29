"""Controlled clocks, fictional network fixtures and isolated session roots."""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from glareshield.copilot.contract import builtin_profile
from glareshield.copilot.reminders import ReminderEngine, ReminderState
from glareshield.copilot.session import DeclarationInput
from test_copilot_session import demo
from test_aibridge_web import client_and_headers
from test_copilot_network import setup


class Flight:
    def __init__(self, phase='cruise'):
        self.engine, self.state, self.now = ReminderEngine(), ReminderState(), 1000.
        self.session = SimpleNamespace(universe='demo', declarations=[])
        self.phase = {'effective': {'value': phase}, 'substate': None}
        self.flight = {'connected': True, 'paused': False, 'stale': False, 'plan': {}, 'plan_current': True,
                       'telemetry': {}, 'derived': {'direct_distance_to_destination': {'value': 181}}}
        self.network = {'state': 'disabled', 'positions': None, 'atis': [],
                        'events': {'stream_id': 'fixture', 'latest_sequence': 0, 'events': [], 'gap': False}}

    def altitude(self, value):
        self.flight['telemetry']['altitude_msl'] = {'value': value, 'unit': 'ft', 'status': 'simulated', 'age_s': 0}

    def tick(self):
        self.state, self.view = self.engine.evaluate(self.state, builtin_profile().reminders,
            self.session, self.phase, self.flight, self.network, self.now)
        self.now += 1
        return self.view

    def hold(self, seconds):
        for _ in range(seconds+1): self.tick()
        return self.view


def test_arrival_threshold_continuity_and_maintenance():
    f = Flight()
    assert not f.hold(8)['active']
    f.flight['derived']['direct_distance_to_destination']['value'] = 180
    assert not f.hold(4)['active']
    assert f.tick()['active'][0]['rule'] == 'prepare_arrival'
    f.flight['derived']['direct_distance_to_destination']['value'] = 250
    f.hold(8)
    assert len(f.state.events) == 1
    assert f.view['pending_count'] == 1
    assert f.view['tod']['kind'] == 'unknown'
    assert 'ne calcule pas le TOD' in f.view['active'][0]['method']


@pytest.mark.parametrize('interruption', ['pause', 'stale', 'disconnected', 'gap', 'reverse'])
def test_interruptions_require_a_new_continuous_hold(interruption):
    f = Flight()
    f.flight['derived']['direct_distance_to_destination']['value'] = 170
    f.hold(4)
    if interruption == 'pause': f.flight['paused'] = True
    elif interruption == 'stale': f.flight['stale'] = True
    elif interruption == 'disconnected': f.flight['connected'] = False
    elif interruption == 'gap': f.now += 9
    elif interruption == 'reverse': f.now -= 20
    f.tick()
    assert not f.state.events
    f.flight.update(paused=False, stale=False, connected=True)
    assert not f.hold(3)['active']
    assert f.hold(2)['active']


def test_missing_or_old_plan_cannot_trigger_geometric_preparation():
    f = Flight()
    f.flight['plan_current'] = False
    f.flight['derived']['direct_distance_to_destination']['value'] = 100
    assert not f.hold(10)['active']
    assert f.view['upcoming'][0]['uncertainty']
    f.flight['derived'] = {}
    f.flight['plan_current'] = True
    assert not f.hold(10)['active']


def test_explicit_tod_is_declared_not_estimated_and_invalid_data_stays_unknown():
    f = Flight()
    f.flight['derived'] = {}
    declaration = SimpleNamespace(field='selection.tod_utc', value=datetime.fromtimestamp(f.now+600, UTC).isoformat(),
        revoked_at=None, invalidated_reason=None, recorded_at=f.now, reference='Relevé fictif du pilote')
    f.session.declarations.append(declaration)
    assert f.hold(5)['tod']['kind'] == 'supplied'
    assert f.view['active'][0]['rule'] == 'prepare_arrival'
    declaration.value = '2026-01-01T12:00:00'  # No time zone is not an explicit instant.
    assert f.tick()['tod']['kind'] == 'unknown'
    declaration.value = 'invalid'
    assert f.tick()['tod']['value'] is None


def test_altitude_crossing_requires_both_sides_and_ignores_oscillations():
    f = Flight('descent')
    f.altitude(9700)
    f.hold(4)
    assert 'altitude_10000_down' not in f.state.fired
    for altitude in (10100, 9900)*5:
        f.altitude(altitude); f.tick()
    assert 'altitude_10000_down' not in f.state.fired
    f.altitude(10300); f.hold(3)
    f.altitude(9700); f.hold(3)
    assert 'altitude_10000_down' in f.state.fired
    crossing = next(e for e in f.state.events.values() if e.rule == 'altitude_10000_down')
    assert 'MSL' in crossing.method and 'pas un franchissement de FL100' in crossing.method
    count = len(f.state.events)
    f.altitude(10300); f.hold(3); f.altitude(9700); f.hold(3)
    assert len(f.state.events) == count


def test_pause_does_not_infer_an_altitude_crossing_and_critical_display_is_limited():
    f = Flight('descent')
    f.altitude(10300); f.hold(3)
    f.flight['paused'] = True; f.tick()
    f.altitude(9700); f.flight['paused'] = False; f.hold(4)
    assert 'altitude_10000_down' not in f.state.fired
    assert f.view['critical'] and len(f.view['active']) <= 1


def test_acknowledgement_and_deduplication_survive_restart(tmp_path):
    now = [1000.]
    bridge = demo(tmp_path, lambda: now[0])
    service = bridge.sessions
    service.start(); service.force_phase('descent')
    now[0] += 3
    view = service.view()
    reminder = view['flight']['reminders'][0]
    assert reminder['rule'] == 'descent_started'
    before = service.path('demo').read_bytes()
    service.view(); service.view()
    assert service.path('demo').read_bytes() == before
    service.acknowledge_reminder(reminder['id'])
    assert not service.view()['flight']['reminders']
    restarted = demo(tmp_path, lambda: now[0])
    now[0] += 3
    assert not restarted.sessions.view()['flight']['reminders']
    assert restarted.sessions.view()['session']['reminder_state']['events'][reminder['id']]['acknowledged_at']
    with pytest.raises(ValueError): service.acknowledge_reminder('other-session')


@pytest.mark.asyncio
async def test_atis_acquisition_revision_text_outage_and_shared_notifications(tmp_path):
    bridge, clock, network = setup(tmp_path)
    bridge.sessions.force_phase('cruise')
    notices = []
    bridge.ivao.notifier = lambda *args: notices.append(args)
    bridge.ivao.settings.notifications = True
    await bridge.ivao.refresh()
    service = bridge.sessions
    first = service.view()
    events = list(first['session']['reminder_state']['events'].values())
    assert any(e['rule'] == 'atis_available' for e in events)
    assert not any(e['rule'] == 'atis_update' for e in events)
    assert notices == []
    before = network.requests.copy()
    service.view(); service.view()
    assert network.requests == before
    clock.now += 16
    network.payloads['whazzup']['clients']['atcs'][0]['atis']['revision'] = 'L'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    service.view()
    clock.now += 16
    network.payloads['whazzup']['clients']['atcs'][0]['atis']['lines'].append('Fictional text update')
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    result = service.view()
    updates = [e for e in result['session']['reminder_state']['events'].values() if e['rule'] == 'atis_update']
    assert len(updates) == 2
    assert any('lettre identique' in e['label'] for e in updates)
    count = len(result['session']['reminder_state']['events'])
    clock.now += 16
    network.failures['whazzup'] = 'offline'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    assert len(service.view()['session']['reminder_state']['events']) == count
    assert notices == []


def test_reminder_ack_api_requires_token_and_current_session(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    now = [1000.]
    runtime.ai = demo(tmp_path, lambda: now[0])
    service = runtime.ai.sessions
    service.start(); service.force_phase('descent'); now[0] += 3
    state = service.view()
    reminder_id = state['flight']['reminders'][0]['id']
    payload = {'session_id': state['session']['id'], 'universe': 'demo'}
    path = '/api/ai/session/reminders/'+reminder_id+'/acknowledge'
    assert client.post(path, json=payload).status_code == 403
    assert client.post(path, json={**payload, 'session_id':'old'}, headers=headers).status_code == 409
    assert client.post(path, json=payload, headers=headers).status_code == 200
    assert not service.view()['flight']['reminders']
