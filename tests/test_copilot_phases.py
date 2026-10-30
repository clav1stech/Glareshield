"""Deterministic stage detection with fictional data and disposable roots only."""
import pytest

from glareshield.aibridge.catalog import STANDARD
from glareshield.aibridge.scenario import values
from glareshield.aibridge.telemetry import TelemetryStore, qualify
from glareshield.copilot.contract import PHASE_IDS
from glareshield.copilot.phases import STAGE_IDS, PhaseEngine, PhaseState, read_sample
from test_copilot_session import demo, first_step, shown
from test_aibridge_web import client_and_headers


PLAN = {'cruise': {'initial_altitude_ft': 35000}, 'destination': {'latitude': 0, 'longitude': 0}}
UNITS = {'on_ground': None, 'ground_speed': 'kt', 'vertical_speed': 'ft/min', 'altitude_msl': 'ft',
         'altitude_indicated': 'ft', 'altitude_agl': 'ft', 'latitude': 'deg', 'longitude': 'deg',
         'engine_1_running': None, 'engine_2_running': None}
CRUISE = {'on_ground': False, 'ground_speed': 450, 'vertical_speed': 0, 'altitude_indicated': 35000,
          'altitude_agl': 35000, 'latitude': 3, 'longitude': 0}
GROUND = {'on_ground': True, 'ground_speed': 0, 'vertical_speed': 0, 'altitude_indicated': 300,
          'altitude_agl': 0, 'latitude': 5, 'longitude': 0}


def fields(base=CRUISE, **overrides):
    data = {**base, **overrides}
    return {key: {'value': value, 'unit': UNITS[key], 'status': 'simulated', 'age_s': 0}
            for key, value in data.items() if value is not None}


class Flight:
    def __init__(self, state=None, stage=None):
        self.engine, self.now = PhaseEngine(), 1000.0
        self.state = state or PhaseState(stage=stage, airborne_seen=stage not in (None, 'parked', 'taxi_out'))

    def tick(self, data=None, plan=PLAN, live=True, active=True):
        self.state, self.view = self.engine.evaluate(self.state, read_sample(data or fields(), plan), plan,
                                                     self.now, live=live, active=active)
        self.now += 1
        return self.view

    def hold(self, seconds, data=None, **kwargs):
        for _ in range(seconds+1):
            self.tick(data, **kwargs)
        return self.view


def test_full_scenario_visits_every_stage_in_order_from_telemetry_only(tmp_path):
    bridge = demo(tmp_path)
    plan = bridge.plan.plan
    flight, store, stages = Flight(), TelemetryStore('scenario'), []
    for elapsed in range(1560):
        now = flight.now
        # The input is exclusively the scenario's allowed numeric/bool telemetry, never its phase name.
        store.clock = lambda: now
        store.update({'connected': True, 'telemetry': {
            key: (value, now) for key, value in values(elapsed).items() if key in UNITS}})
        data = {entry.key: qualify(entry, store, now) for entry in STANDARD if entry.key in UNITS}
        view = flight.tick(data, plan)
        if view['stage'] and (not stages or stages[-1] != view['stage']):
            stages.append(view['stage'])
    assert stages == [s for s in STAGE_IDS if s != 'go_around']
    assert view['effective'] == {'value': 'arrival', 'status': 'derived'}


def test_starting_in_flight_places_the_aircraft_without_waiting_for_cruise():
    flight = Flight()
    assert flight.tick()['stage'] is None
    view = flight.hold(3)
    assert view['stage'] == 'cruise' and flight.state.airborne_seen
    climbing = Flight()
    assert climbing.hold(3, fields(vertical_speed=1800, altitude_indicated=21000))['stage'] == 'climb'
    descending = Flight()
    assert descending.hold(3, fields(vertical_speed=-2000, altitude_indicated=21000))['stage'] == 'descent'
    near = Flight()
    assert near.hold(3, fields(latitude=0.2, altitude_agl=4000, vertical_speed=-800))['stage'] == 'approach'
    parked = Flight()
    assert parked.hold(3, fields(GROUND))['stage'] == 'parked'


def test_cruise_is_found_when_true_altitude_differs_from_the_planned_level():
    """1.2.x compared true MSL altitude to the OFP level at ±1000 ft and missed whole cruises."""
    flight = Flight(stage='climb')
    level = fields(altitude_indicated=None, altitude_msl=33600)
    assert flight.hold(59, level)['stage'] == 'climb'
    assert flight.tick(level)['stage'] == 'cruise'
    stepped = Flight(stage='climb')
    assert stepped.hold(60, fields(altitude_indicated=31000))['stage'] == 'cruise'


def test_low_level_off_in_climb_is_not_cruise_and_descent_needs_no_cruise():
    flight = Flight(stage='climb')
    flight.hold(5, fields(altitude_indicated=24000, vertical_speed=2000))
    assert flight.hold(120, fields(altitude_indicated=24000))['stage'] == 'climb'
    # Short hop: never level near the planned level, descent is still recognised.
    flight.hold(5, fields(altitude_indicated=22500, vertical_speed=-1500))
    flight.hold(20, fields(altitude_indicated=20500, vertical_speed=-1500))
    assert flight.view['stage'] == 'descent'


def test_cruise_step_descent_is_not_a_descent():
    flight = Flight(stage='cruise')
    flight.hold(2, fields())
    assert flight.hold(60, fields(altitude_indicated=34000, vertical_speed=-1000))['stage'] == 'cruise'
    assert flight.hold(25, fields(altitude_indicated=31500, vertical_speed=-1500))['stage'] == 'descent'


def test_noise_resets_holds_and_pending_progress_is_reported():
    flight = Flight(stage='cruise')
    flight.hold(2, fields())
    flight.hold(5, fields(altitude_indicated=31000, vertical_speed=-1500))
    assert flight.view['next']['stage'] == 'descent' and flight.view['next']['elapsed_s'] >= 5
    flight.tick(fields(altitude_indicated=31000, vertical_speed=-100))
    flight.hold(19, fields(altitude_indicated=31000, vertical_speed=-1500))
    assert flight.view['stage'] == 'cruise'
    flight.tick(fields(altitude_indicated=31000, vertical_speed=-1500))
    assert flight.view['stage'] == 'descent'


@pytest.mark.parametrize('case', ['paused', 'inactive', 'gap', 'missing', 'stale', 'unit'])
def test_interruptions_keep_the_stage_and_discard_pending_holds(case):
    flight = Flight(stage='cruise')
    flight.hold(2, fields())
    descending = fields(altitude_indicated=31000, vertical_speed=-1500)
    flight.hold(15, descending)
    if case == 'paused':
        flight.tick(descending, live=False)
        assert flight.view['effective']['status'] == 'stale'
    elif case == 'inactive':
        flight.tick(descending, active=False)
    elif case == 'gap':
        flight.now += 20
    elif case == 'missing':
        flight.tick(fields(altitude_indicated=31000, vertical_speed=None))
    elif case == 'stale':
        bad = fields(altitude_indicated=31000, vertical_speed=-1500)
        bad['vertical_speed']['age_s'] = 9
        flight.tick(bad)
    elif case == 'unit':
        bad = fields(altitude_indicated=31000, vertical_speed=-1500)
        bad['vertical_speed']['unit'] = 'm/s'
        flight.tick(bad)
    assert flight.view['stage'] == 'cruise'
    flight.hold(10, descending)
    assert flight.view['stage'] == 'cruise'


def test_ground_sequence_rejected_takeoff_and_parking_after_landing():
    flight = Flight()
    flight.hold(3, fields(GROUND))
    assert flight.hold(3, fields(GROUND, engine_1_running=True))['stage'] == 'pushback'
    assert flight.hold(5, fields(GROUND, ground_speed=15))['stage'] == 'taxi_out'
    assert flight.hold(2, fields(GROUND, ground_speed=90))['stage'] == 'takeoff'
    assert flight.hold(5, fields(GROUND, ground_speed=20))['stage'] == 'taxi_out'
    flight.hold(2, fields(GROUND, ground_speed=150))
    flight.hold(3, fields(GROUND, on_ground=False, ground_speed=170, altitude_agl=600, vertical_speed=2000))
    assert flight.view['stage'] == 'takeoff'
    assert flight.hold(3, fields(GROUND, on_ground=False, ground_speed=180, altitude_agl=1600,
                                 vertical_speed=2000))['stage'] == 'climb'
    # Aborted flight: back on the ground without cruise or destination.
    assert flight.hold(2, fields(GROUND, ground_speed=120))['stage'] == 'rollout'
    assert flight.hold(5, fields(GROUND, ground_speed=20))['stage'] == 'taxi_in'
    assert flight.hold(19, fields(GROUND))['stage'] == 'taxi_in'
    assert flight.tick(fields(GROUND))['stage'] == 'parked_in'


def test_approach_final_go_around_and_new_approach():
    flight = Flight(stage='descent')
    flight.hold(2, fields(latitude=1, altitude_agl=9000, vertical_speed=-1500))
    assert flight.view['stage'] == 'descent'
    assert flight.hold(5, fields(latitude=0.3, altitude_agl=6000, vertical_speed=-1000))['stage'] == 'approach'
    assert flight.hold(2, fields(latitude=0.1, altitude_agl=1200, vertical_speed=-700))['stage'] == 'final'
    view = flight.hold(5, fields(latitude=0.05, altitude_agl=900, vertical_speed=1500))
    assert view['stage'] == 'go_around' and view['phase'] == 'arrival'
    assert flight.hold(15, fields(latitude=0.2, altitude_agl=3000, vertical_speed=-800))['stage'] == 'approach'
    assert flight.hold(2, fields(latitude=0.1, altitude_agl=1000, vertical_speed=-700))['stage'] == 'final'


def test_without_plan_approach_needs_low_height_in_descent():
    flight = Flight(stage='descent')
    assert flight.hold(10, fields(altitude_agl=5000, vertical_speed=-1000), plan=None)['stage'] == 'descent'
    assert flight.hold(5, fields(altitude_agl=2500, vertical_speed=-800), plan=None)['stage'] == 'approach'


def test_pilot_correction_reanchors_and_automatic_tracking_continues():
    flight = Flight(stage='climb')
    flight.state = flight.engine.correct(flight.state, 'cruise', flight.now)
    assert (flight.state.stage, flight.state.manual) == ('cruise', True)
    assert flight.tick()['mode'] == 'manual'
    flight.hold(20, fields(altitude_indicated=29000, vertical_speed=-1500))
    assert flight.view['stage'] == 'descent' and flight.view['mode'] == 'automatic'
    back = flight.engine.correct(flight.state, 'preflight', flight.now)
    assert back.stage == 'parked' and back.airborne_seen is False


def test_legacy_phase_state_maps_to_a_stage():
    assert PhaseState.model_validate({'phase': 'cruise', 'confirmed': True, 'cruise_seen': True,
                                      'airborne_seen': True, 'substate': None}).stage == 'cruise'
    assert PhaseState.model_validate({'phase': 'arrival', 'confirmed': True, 'cruise_seen': False,
                                      'airborne_seen': True, 'substate': 'parking'}).stage == 'parked_in'
    assert PhaseState.model_validate({'phase': 'preflight', 'confirmed': False}).stage is None
    # A new session is placed by measurements, never assumed parked.
    assert PhaseState().stage is None and PhaseState.model_validate({}).stage is None


def test_new_session_started_in_flight_is_placed_from_measurements(tmp_path):
    clock = [2_000_000_000.]
    bridge = demo(tmp_path, lambda: clock[0])
    store = TelemetryStore('scenario', lambda: clock[0])
    bridge.store = lambda: store
    service = bridge.sessions
    service.start()
    for _ in range(5):
        clock[0] += 1
        store.update({'connected': True, 'telemetry': {k: (float(v) if not isinstance(v, bool) else v, clock[0])
                                                        for k, v in CRUISE.items()}})
        view = service.view()
    assert view['phase']['stage'] == 'cruise'


def test_session_persists_stage_changes_not_every_peak(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start()
    clock = [2_000_000_000.]
    store = TelemetryStore('scenario', lambda: clock[0])
    bridge.store, service.clock = (lambda: store), (lambda: clock[0])
    writes = []
    original = service._save
    service._save = lambda document: (writes.append(1), original(document))
    for second in range(40):
        clock[0] += 1
        store.update({'connected': True, 'telemetry': {k: (v, clock[0]) for k, v in {
            **CRUISE, 'vertical_speed': 2000., 'altitude_indicated': 20000.+second*30,
            'altitude_msl': 20000.+second*30}.items()}})
        view = service.view()
    assert view['phase']['stage'] == 'climb'
    assert view['cockpit']['stage'] == 'climb'
    # Placed directly in climb, then a few peak writes: never one write per second of climb.
    history = [e for e in service.documents['demo'].sessions[-1].history if e['event'] == 'stage']
    assert [e['stage'] for e in history] == ['climb']
    assert len(writes) <= 4


def test_correction_keeps_steps_and_api_requires_token(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    runtime.ai.set_scenario(True)
    runtime.ai.load_demo_plan()
    service = runtime.ai.sessions
    session = service.start()['session']
    step = first_step(service)
    service.set_step(step, True)
    payload = {'session_id': session['id'], 'universe': 'demo', 'phase': 'descent'}
    assert client.put('/api/ai/session/phase', json=payload).status_code == 403
    view = client.put('/api/ai/session/phase', json=payload, headers=headers).json()
    assert view['phase']['phase'] == 'descent' and view['phase']['mode'] == 'manual'
    assert view['cockpit']['track'][PHASE_IDS.index('descent')]['state'] == 'current'
    assert shown(service, step)['checked'] is True
    value = client.put('/api/ai/session/values/stand', headers=headers,
                       json={'session_id': session['id'], 'universe': 'demo', 'value': 'K21'})
    assert value.status_code == 200 and value.json()['flight']['values']['stand']['value'] == 'K21'
    bad = client.put('/api/ai/session/values/completed', headers=headers,
                     json={'session_id': session['id'], 'universe': 'demo', 'value': 'x'})
    assert bad.status_code == 400
