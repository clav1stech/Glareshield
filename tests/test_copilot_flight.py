"""Vol presentation rules against fictional plans, simulated telemetry and isolated roots."""
from glareshield.copilot.flight import priority_step
from test_copilot_session import demo, declaration


def test_priority_follows_phase_unchecked_priority_and_profile_order():
    groups = [{'phase': 'preflight', 'steps': [
        {'id': 'first', 'checked': False, 'priority': 50},
        {'id': 'urgent', 'checked': False, 'priority': 90},
        {'id': 'tie', 'checked': False, 'priority': 90}]},
        {'phase': 'arrival', 'steps': [{'id': 'later', 'checked': False, 'priority': 100}]}]
    assert priority_step(groups, 'preflight')['id'] == 'urgent'
    groups[0]['steps'][1]['checked'] = True
    assert priority_step(groups, 'preflight')['id'] == 'tie'
    groups[0]['steps'][2]['checked'] = True
    assert priority_step(groups, 'preflight')['id'] == 'first'
    assert priority_step(groups, None) is None
    assert priority_step(groups, 'arrival')['id'] == 'later'


def test_values_are_sourced_clearance_is_never_planned_and_revocation_is_visible(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start()
    def values():
        return service.view()['flight']['values']
    clearance = next(k for k, v in service.profile.values.items() if 'pilot_cleared_altitude' in v.sources)
    assert values()[clearance]['value'] is None
    service.declare(declaration('clearance', value='5000'))
    value = values()[clearance]
    assert value['value'] == 5000
    assert value['nature'] == 'declared'
    assert value['source'] == 'pilot.clearance.cleared_altitude'
    assert value['reference'] == 'Référence fictive'
    service.revoke(service.view()['session']['declarations'][-1]['id'])
    assert values()[clearance]['value'] is None
    for value in values().values():
        assert value['source']
        if value['status'] == 'unavailable':
            assert value['value'] is None
            assert value['placeholder'].startswith('<')


def test_live_state_priority_and_manual_progress_survive_navigation(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    view = service.start()
    now = view['flight']['now']
    assert now and not now['checked']
    view = service.set_step(now['id'], True)
    assert view['flight']['now']['id'] != now['id']
    view = service.force_phase('arrival')
    assert view['flight']['now']['id'] in [s['id'] for g in view['groups'] if g['phase'] == 'arrival' for s in g['steps']]
    assert service.view()['session']['steps'][now['id']]['manual']['checked']
    store = bridge.store()
    bridge.store = lambda: store
    store.paused = True
    assert service.view()['flight']['paused']
    assert service.view()['flight']['derived'] == {}
    store.connected = False
    assert service.view()['flight']['connected'] is False
    assert service.view()['flight']['derived'] == {}


def test_zero_remains_a_real_measurement_missing_and_stale_are_distinct(tmp_path):
    clock = [2000000000.0]
    bridge = demo(tmp_path, lambda: clock[0])
    bridge.sessions.start()
    store = bridge.store()
    bridge.store = lambda: store
    store.update({'telemetry': {'ground_speed': (0.0, clock[0])}, 'connected': True, 'paused': False})
    view = bridge.sessions.view()['flight']
    assert view['telemetry']['ground_speed']['value'] == 0
    assert view['telemetry']['ground_speed']['status'] == 'simulated'
    clock[0] += 20
    view = bridge.sessions.view()['flight']
    assert view['stale']
    assert view['telemetry']['ground_speed']['status'] == 'stale'
    assert view['derived'] == {}
