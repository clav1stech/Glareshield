"""Deterministic phase inference with fictional data and disposable roots only."""
import json

import pytest

from glareshield.aibridge.catalog import STANDARD
from glareshield.aibridge.scenario import values
from glareshield.aibridge.telemetry import TelemetryStore, qualify
from glareshield.copilot.contract import PHASE_IDS, QualifiedValue
from glareshield.copilot.phases import PhaseEngine, PhaseState
from test_copilot_session import demo, first_step, shown
from test_aibridge_web import client_and_headers


PLAN = {'cruise': {'initial_altitude_ft': 35000},
        'destination': {'latitude': 0, 'longitude': 0},
        'waypoints': [{'ident': 'FICTION', 'latitude': 0, 'longitude': 0}]}
UNITS = {'on_ground': None, 'ground_speed': 'kt', 'vertical_speed': 'ft/min',
         'altitude_msl': 'ft', 'altitude_agl': 'ft', 'latitude': 'deg', 'longitude': 'deg'}


def fields(**overrides):
    data = {'on_ground': False, 'ground_speed': 250, 'vertical_speed': 0,
            'altitude_msl': 35000, 'altitude_agl': 35000, 'latitude': 3, 'longitude': 0}
    data.update(overrides)
    return {key: {'value': value, 'unit': UNITS[key], 'status': 'simulated', 'age_s': 0}
            for key, value in data.items()}


class Flight:
    def __init__(self, state=None):
        self.engine, self.state, self.now = PhaseEngine(), state or PhaseState(), 1000.0

    def tick(self, data=None, plan=PLAN, **kwargs):
        self.state, self.view = self.engine.evaluate(
            self.state, data or fields(), plan, self.now,
            **{'connected': True, 'paused': False, 'last_message': self.now, **kwargs})
        QualifiedValue.model_validate(self.view['automatic'])
        QualifiedValue.model_validate(self.view['effective'])
        self.now += 1
        return self.view

    def hold(self, seconds, data=None, **kwargs):
        for _ in range(seconds+1):
            self.tick(data, **kwargs)
        return self.view


def test_full_scenario_without_phase_name_input(tmp_path):
    bridge = demo(tmp_path)
    plan = bridge.plan.plan
    flight, store, phases, substates = Flight(), TelemetryStore('scenario'), [], set()
    for elapsed in range(1500):
        now = flight.now
        # The input is exclusively the scenario's allowed numeric/bool telemetry.
        store.clock = lambda: now
        store.update({'connected': True, 'telemetry': {
            key: (value, now) for key, value in values(elapsed).items() if key in UNITS}})
        data = {entry.key: qualify(entry, store, now) for entry in STANDARD if entry.key in UNITS}
        view = flight.tick(data, plan)
        if not phases or phases[-1] != flight.state.phase:
            phases.append(flight.state.phase)
        substates.add(view['substate'])
    assert tuple(phases) == PHASE_IDS
    assert {'parking', 'taxi', 'takeoff', 'approach', 'landing'} <= substates
    assert view['automatic']['status'] == 'derived'


def test_airborne_start_cruise_needs_thirty_continuous_seconds():
    flight = Flight()
    flight.hold(29)
    assert not flight.state.confirmed
    flight.tick()
    assert flight.state.phase == 'cruise' and flight.state.cruise_seen
    assert flight.view['geometry']['route_progress']['status'] == 'derived'


def test_climb_and_descent_plateaus_keep_phase():
    flight = Flight()
    flight.hold(8, fields(vertical_speed=1000, altitude_msl=12000))
    assert flight.state.phase == 'climb'
    flight.hold(60, fields(altitude_msl=12000))
    assert flight.state.phase == 'climb'
    flight.hold(30)
    assert flight.state.phase == 'cruise'
    flight.hold(15, fields(vertical_speed=-1000))
    assert flight.state.phase == 'descent'
    flight.hold(40, fields(altitude_msl=22000))
    assert flight.state.phase == 'descent'


def test_noise_around_threshold_resets_confirmation_and_never_regresses():
    flight = Flight(PhaseState(phase='climb', confirmed=True))
    for vertical in (299, 301)*40:
        flight.tick(fields(vertical_speed=vertical))
    assert flight.state.phase == 'climb'
    flight.hold(30)
    for vertical in (-301, -299)*40:
        flight.tick(fields(vertical_speed=vertical))
    assert flight.state.phase == 'cruise'
    flight.hold(15, fields(vertical_speed=-301))
    flight.hold(50)
    assert flight.state.phase == 'descent'


@pytest.mark.parametrize('interruption', ['paused', 'disconnected', 'stale', 'missing', 'gap', 'clock', 'unit', 'inactive'])
def test_interruption_discards_pending_hold(interruption):
    flight = Flight(PhaseState(phase='climb', confirmed=True))
    flight.hold(25)
    data, kwargs = fields(), {}
    if interruption == 'paused': kwargs['paused'] = True
    if interruption == 'disconnected': kwargs['connected'] = False
    if interruption == 'stale': data['on_ground'].update(status='stale', age_s=9)
    if interruption == 'missing': data.pop('on_ground')
    if interruption == 'gap': flight.now += 10
    if interruption == 'clock': flight.now -= 50
    if interruption == 'unit': data['vertical_speed']['unit'] = 'm/s'
    if interruption == 'inactive': kwargs['active'] = False
    view = flight.tick(data, **kwargs)
    assert flight.state.phase == 'climb'
    if interruption not in ('gap', 'clock'):
        assert view['automatic']['status'] == 'stale'
    flight.hold(28)
    assert flight.state.phase == 'climb'
    flight.hold(2)
    assert flight.state.phase == 'cruise'


def test_arrival_highest_confirmed_phase_and_go_around():
    flight = Flight(PhaseState(phase='cruise', confirmed=True, cruise_seen=True, airborne_seen=True))
    close = fields(latitude=.1, altitude_agl=8000, altitude_msl=9000, vertical_speed=-1000)
    flight.hold(8, close)
    assert flight.state.phase == 'arrival'
    flight.hold(8, fields(latitude=.1, altitude_agl=3000, vertical_speed=1500))
    assert flight.state.phase == 'arrival' and flight.state.substate == 'go_around'
    flight.hold(8, close)
    assert flight.state.substate == 'approach'
    for ground in (True, False)*8:
        flight.tick(fields(on_ground=ground, ground_speed=130, vertical_speed=-600))
    assert flight.state.substate == 'approach'
    flight.hold(5, fields(on_ground=True, ground_speed=130))
    assert flight.state.substate == 'landing'
    flight.hold(5, fields(on_ground=True, ground_speed=15))
    assert flight.state.substate == 'taxi'
    flight.hold(10, fields(on_ground=True, ground_speed=0))
    assert flight.state.substate == 'parking'


def test_return_to_ground_after_aborted_climb_does_not_require_destination():
    flight = Flight()
    flight.hold(8, fields(vertical_speed=1000), plan=None)
    assert flight.state.phase == 'climb'
    flight.hold(4, fields(on_ground=True, ground_speed=80), plan=None)
    assert flight.state.phase == 'climb'
    flight.tick(fields(on_ground=True, ground_speed=80), plan=None)
    assert flight.state.phase == 'arrival' and flight.state.substate == 'landing'


def test_insufficient_plan_or_start_in_descent_is_explicit():
    flight = Flight()
    view = flight.hold(40, fields(vertical_speed=-1000), plan=None)
    assert view['automatic']['value'] is None and view['uncertainty']
    assert not view['geometry']
    flight.hold(8, fields(vertical_speed=1000), plan=None)
    view = flight.hold(40, plan=None)
    assert flight.state.phase == 'climb' and view['uncertainty']
    assert not any(name in json.dumps(view) for name in ('FMA', 'ECAM', 'TOD'))


@pytest.mark.parametrize('key', ['altitude_msl', 'latitude', 'longitude', 'altitude_agl'])
def test_stale_complementary_inputs_do_not_allow_their_transition(key):
    flight = Flight(PhaseState(phase='climb', confirmed=True, cruise_seen=True))
    data = fields(latitude=.1, altitude_agl=8000)
    data[key].update(status='stale', age_s=9)
    view = flight.hold(40, data)
    if key == 'altitude_msl':
        assert flight.state.phase == 'arrival'  # Arrival does not depend on MSL altitude.
    else:
        assert flight.state.phase == 'cruise'  # Cruise does not depend on position or AGL.
    assert view['uncertainty']


def test_old_plan_and_corrected_plan_reset_confirmation(tmp_path):
    flight = Flight(PhaseState(phase='climb', confirmed=True, cruise_seen=True))
    view = flight.hold(40, fields(latitude=.1, altitude_agl=8000), plan_current=False)
    assert flight.state.phase == 'climb' and view['uncertainty']
    now = [1000.0]
    bridge = demo(tmp_path, lambda: now[0])
    service = bridge.sessions
    service.start()
    service.documents['demo'].sessions[-1].phase_state = PhaseState(phase='climb', confirmed=True)
    # A changed OFP cannot inherit timers from the previous plan revision.
    engine = service.phase_engines[service.documents['demo'].sessions[-1].id]
    engine.holds['phase_cruise'] = now[0]-25
    bridge.plan.plan['cruise']['initial_altitude_ft'] = 34000
    service.synchronize()
    assert not service.phase_engines


def test_ground_noise_and_substate_speed_hysteresis():
    flight = Flight(PhaseState(phase='departure', confirmed=True))
    ground = fields(on_ground=True, ground_speed=90)
    flight.hold(3, ground)
    assert flight.state.substate == 'takeoff'
    for speed in (79, 81)*10:
        flight.tick(fields(on_ground=True, ground_speed=speed))
        assert flight.state.substate == 'takeoff'
    flight.tick(fields(vertical_speed=0))  # One airborne glitch cannot prove a flight.
    flight.hold(10, ground)
    assert flight.state.phase == 'departure' and not flight.state.airborne_seen
    flight = Flight(PhaseState(phase='arrival', confirmed=True, airborne_seen=True, substate='landing'))
    for speed in (39, 41)*20:
        flight.tick(fields(on_ground=True, ground_speed=speed))
        assert flight.state.substate == 'landing'
    flight.hold(5, fields(on_ground=True, ground_speed=20))
    assert flight.state.substate == 'taxi'


def test_manual_choice_freezes_automatic_then_requires_new_confirmation():
    flight = Flight(PhaseState(phase='climb', confirmed=True))
    flight.hold(25)
    view = flight.hold(40, forced='arrival', forced_at=1000)
    assert view['effective']['value'] == 'arrival' and view['effective']['nature'] == 'declared'
    assert flight.state.phase == 'climb'
    assert view['effective']['age_s'] > 0
    flight.hold(29)
    assert flight.state.phase == 'climb'
    flight.tick()
    assert flight.state.phase == 'cruise'


def test_manual_command_restart_and_auto_resume_preserve_actions(tmp_path):
    now = [1000.0]
    bridge = demo(tmp_path, lambda: now[0])
    service = bridge.sessions
    service.start()
    step = first_step(service)
    service.set_step(step, True)
    service.remember('fictional_reminder', 'fictional-reference')
    service.force_phase('descent')
    for _ in range(20):
        now[0] += 1
        assert service.view()['phase']['effective']['value'] == 'descent'
    restarted = demo(tmp_path, lambda: now[0])
    view = restarted.sessions.view()
    assert view['phase']['mode'] == 'manual'
    assert view['phase']['effective']['value'] == 'descent'
    view = restarted.sessions.force_phase(None)
    assert view['phase']['mode'] == 'automatic'
    assert shown(restarted.sessions, step)['checked']
    assert view['session']['reminders']['fictional_reminder']['checked']


def test_live_updates_advance_without_an_open_page_and_errors_freeze(tmp_path):
    from glareshield.aibridge.service import AIBridge
    now = [1000.0]
    bridge = AIBridge(tmp_path, clock=lambda: now[0])
    bridge.settings.enabled = True
    def message(**changes):
        data = {'on_ground': True, 'ground_speed': 0, **changes}
        bridge.on_simulator_message({'connected': True, 'paused': False,
                                     'telemetry': {key: (value, now[0]) for key, value in data.items()}})
    message()
    bridge.sessions.start()
    for _ in range(9):
        now[0] += 1
        message(on_ground=False, vertical_speed=1000)
    assert bridge.sessions.documents['simconnect'].sessions[-1].phase_state.phase == 'climb'
    now[0] += 1
    bridge.on_simulator_message({'connected': False})
    assert bridge.sessions.view()['phase']['automatic']['status'] == 'stale'
    message(on_ground=False, vertical_speed=0)
    bridge.live.errors['vertical_speed'] = 'fictional-invalid'
    assert bridge.sessions.view()['phase']['suspended']


def test_phase_route_manual_and_explicit_auto(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    runtime.ai.set_scenario(True)
    with client:
        view = runtime.ai.sessions.start()
        target = {'session_id': view['session']['id'], 'universe': 'demo'}
        for selected in ('cruise', 'arrival', None):
            view = client.put('/api/ai/session/phase', json={**target, 'phase': selected}, headers=headers).json()
            assert view['phase']['mode'] == ('manual' if selected else 'automatic')
            if selected:
                assert view['phase']['effective']['value'] == selected
        assert client.put('/api/ai/session/phase', json={**target, 'phase': 'FMA'}, headers=headers).status_code == 422


def test_failed_phase_write_keeps_last_phase_visible_and_actions(tmp_path, monkeypatch):
    now = [1000.0]
    bridge = demo(tmp_path, lambda: now[0])
    service = bridge.sessions
    service.start()
    step = first_step(service)
    service.set_step(step, True)
    before = service.path('demo').read_bytes()
    def fail(*args):
        raise OSError('fictional disk failure')
    monkeypatch.setattr('glareshield.copilot.session.atomic_write', fail)
    # Scenario starts moving at t=90; confirmation at t=95 requires a write.
    for elapsed in range(1, 96):
        now[0] = 1000+elapsed
        view = service.view()
    assert view['warnings']
    assert view['phase']['effective']['value'] == 'preflight'
    assert view['phase']['effective']['status'] == 'stale'
    assert view['phase']['suspended']
    assert service.path('demo').read_bytes() == before
    assert shown(service, step)['checked']
