"""Fictional aircraft, isolated roots and simulated stores; no cockpit commands."""
import pytest

from glareshield.aibridge.config import AIBridgeSettings
from glareshield.aibridge.service import AIBridge
from glareshield.aibridge.telemetry import Sample
from glareshield.copilot.observations import ObservationBinding
from test_copilot_session import demo, shown


def live(root, now):
    bridge = AIBridge(root, clock=lambda: now[0])
    bridge.settings = AIBridgeSettings(enabled=True, validated=['gear_handle_down'], copilot_bindings=[
        ObservationBinding(signal='gear_handle_down', key='gear_handle_down',
            variable='GEAR HANDLE POSITION', origin='simvar', aircraft_title='A320 fictif',
            values={'0': False, '1': True})])
    bridge.live.update({'connected': True, 'telemetry': {
        'title': ('A320 fictif', now[0]), 'gear_handle_down': (True, now[0])}})
    bridge.sessions.start()
    bridge.sessions.force_phase('arrival')
    return bridge


def test_transitions_manual_priority_and_no_history_on_refresh(tmp_path):
    now = [1000.]
    bridge = live(tmp_path, now)
    service = bridge.sessions
    detected = shown(service, 'gear_down')
    assert detected['checked'] and detected['provenance'] == 'detected'
    assert detected['observation']['origin'] == 'simconnect'
    before = service.path('simconnect').read_bytes()
    for _ in range(3):
        now[0] += 1
        bridge.live.update({'connected': True, 'telemetry': {'gear_handle_down': (True, now[0])}})
        assert shown(service, 'gear_down')['checked']
    assert service.path('simconnect').read_bytes() == before
    service.set_step('gear_down', False)
    assert shown(service, 'gear_down')['conflict']
    bridge.live.update({'connected': True, 'telemetry': {'gear_handle_down': (False, now[0])}})
    result = shown(service, 'gear_down')
    assert not result['checked'] and not result['conflict']
    service.set_step('gear_down', True)
    result = shown(service, 'gear_down')
    assert result['checked'] and result['conflict'] and not result['detected']['checked']
    now[0] += 9
    result = shown(service, 'gear_down')
    assert result['checked'] and not result['detection_current']
    assert not result['conflict'] and result['detected']
    history = service.view()['session']['history']
    assert len([e for e in history if e['event'] == 'manual_step']) == 2
    assert any(e.get('status') == 'unavailable' for e in history)


@pytest.mark.parametrize('fault', [
    'missing', 'unvalidated', 'no_binding', 'wrong_aircraft', 'wrong_variable', 'wrong_origin',
    'paused', 'disconnected', 'disabled', 'error', 'stale', 'future', 'nan_time', 'nan_value',
    'unknown_value', 'text_value', 'other_store', 'ambiguous', 'aircraft_changed', 'title_stale'])
def test_untrusted_data_cannot_confirm_and_old_evidence_is_kept(tmp_path, fault):
    now = [1000.]
    bridge = live(tmp_path, now)
    store = bridge.live
    binding = bridge.settings.copilot_bindings[0]
    if fault == 'missing': store.samples.pop('gear_handle_down')
    elif fault == 'unvalidated': bridge.settings.validated = []
    elif fault == 'no_binding': bridge.settings.copilot_bindings = []
    elif fault == 'wrong_aircraft': store.samples['title'] = Sample('Autre A320 fictif', now[0])
    elif fault == 'wrong_variable': binding.variable = 'OTHER VARIABLE'
    elif fault == 'wrong_origin': binding.origin = 'lvar'
    elif fault == 'paused': store.paused = True
    elif fault == 'disconnected': store.connected = False
    elif fault == 'disabled': bridge.settings.enabled = False
    elif fault == 'error': store.errors['gear_handle_down'] = 'Fictional error'
    elif fault == 'stale': store.samples['gear_handle_down'] = Sample(True, now[0]-9)
    elif fault == 'future': store.samples['gear_handle_down'] = Sample(True, now[0]+1)
    elif fault == 'nan_time': store.samples['gear_handle_down'] = Sample(True, float('nan'))
    elif fault == 'nan_value': store.samples['gear_handle_down'] = Sample(float('nan'), now[0])
    elif fault == 'unknown_value': store.samples['gear_handle_down'] = Sample(2., now[0])
    elif fault == 'text_value': store.samples['gear_handle_down'] = Sample('1', now[0])
    elif fault == 'other_store': store.origin = 'scenario'
    elif fault == 'ambiguous': bridge.settings.copilot_bindings.append(binding.model_copy())
    elif fault == 'aircraft_changed': store.samples['title'] = Sample('A320 fictif', now[0]+1); now[0] += 1
    elif fault == 'title_stale': store.samples['title'] = Sample('A320 fictif', now[0]-121)
    result = shown(bridge.sessions, 'gear_down')
    assert not result['checked'] and result['provenance'] == 'pending'
    assert not result['detection_current'] and result['detected']['checked']
    assert result['observation']['status'] == 'unavailable'


def test_phase_scope_end_resume_and_restart_require_current_evidence(tmp_path):
    now = [1000.]
    bridge = live(tmp_path, now)
    service = bridge.sessions
    service.force_phase('climb')
    assert not shown(service, 'gear_down')['checked']
    assert shown(service, 'gear_down')['observation']['status'] == 'out_of_phase'
    assert not shown(service, 'gear_up')['checked']
    service.force_phase('arrival')
    assert shown(service, 'gear_down')['checked']
    service.end()
    assert not shown(service, 'gear_down')['checked']
    service.resume()
    assert shown(service, 'gear_down')['checked']
    restarted = AIBridge(tmp_path, clock=lambda: now[0])
    assert not shown(restarted.sessions, 'gear_down')['checked']
    restarted.settings = bridge.settings
    restarted.live.update({'connected': True, 'telemetry': {
        'title': ('A320 fictif', now[0]), 'gear_handle_down': (True, now[0])}})
    assert shown(restarted.sessions, 'gear_down')['checked']


def test_demo_never_confirms_live_and_lighting_values_are_not_read(tmp_path):
    now = [1000.]
    bridge = demo(tmp_path, lambda: now[0])
    bridge.sessions.start()
    bridge.sessions.force_phase('arrival')
    assert shown(bridge.sessions, 'gear_down')['observation']['origin'] == 'scenario'
    bridge.set_scenario(False)
    bridge.settings.enabled = True
    bridge.live.update({'connected': True})
    bridge.sessions.start()
    bridge.sessions.force_phase('arrival')
    assert not shown(bridge.sessions, 'gear_down')['checked']
    assert bridge.sessions.view()['session']['steps'] == {}


def test_demo_takes_time_after_the_store_has_generated_its_samples(tmp_path):
    now = [1000.]
    def clock():
        now[0] += .001
        return now[0]
    bridge = demo(tmp_path, clock)
    bridge.sessions.start()
    bridge.sessions.force_phase('arrival')
    assert shown(bridge.sessions, 'gear_down')['checked']


async def test_real_lighting_test_path_cannot_supply_a_procedure_observation(tmp_path, monkeypatch):
    import time
    import glareshield.runtime as runtime_module
    from glareshield.aibridge.config import LVarEntry
    from test_preparation import FakeSimulator, fixture_runtime
    monkeypatch.setattr(runtime_module, 'SimulatorSource', FakeSimulator)
    runtime = fixture_runtime(tmp_path)
    runtime.ai.settings.lvars = [LVarEntry(key='warning', name='FICTIONAL_GEAR', label='Levier fictif', validated=True)]
    runtime.ai.settings.copilot_bindings = [ObservationBinding(signal='gear_handle_down', key='warning',
        variable='FICTIONAL_GEAR', origin='lvar', aircraft_title='A320 fictif', values={'1': True, '0': False})]
    await runtime.start()
    try:
        runtime.ai.live.update({'connected': True, 'telemetry': {'title': ('A320 fictif', time.time())}})
        runtime.ai.sessions.start()
        runtime.ai.sessions.force_phase('arrival')
        await runtime.test_source('warning', 1, 2)
        assert runtime.engine.values['warning'] == 1
        assert 'warning' not in runtime.ai.live.samples
        assert not shown(runtime.ai.sessions, 'gear_down')['checked']
    finally:
        await runtime.stop()


def test_validated_baro_mapping_measures_std_only_and_appr_stays_manual(tmp_path):
    now = [1000.]
    bridge = live(tmp_path, now)
    bridge.settings.lvars = []
    from glareshield.aibridge.config import LVarEntry
    bridge.settings.lvars.append(LVarEntry(key='fictional_std', name='FICTIONAL_STD', label='STD fictif', validated=True))
    bridge.settings.copilot_bindings.append(ObservationBinding(signal='baro_std', key='fictional_std',
        variable='FICTIONAL_STD', origin='lvar', aircraft_title='A320 fictif', values={'4': True, '2': False}))
    bridge.live.update({'connected': True, 'telemetry': {'fictional_std': (4., now[0])}})
    bridge.sessions.force_phase('climb')
    assert shown(bridge.sessions, 'climb_std')['checked']
    assert 'STD' in shown(bridge.sessions, 'climb_std')['label']
    assert not shown(bridge.sessions, 'appr_button')['checked']
    bridge.live.update({'connected': True, 'telemetry': {'fictional_std': (2., now[0])}})
    assert not shown(bridge.sessions, 'climb_std')['checked']


def test_unknown_trigger_and_known_bad_flap_simvar_stay_manual(tmp_path):
    now = [1000.]
    bridge = live(tmp_path, now)
    step = next(s for p in bridge.sessions.profile.phases for g in p.groups for s in g.steps if s.id == 'gear_down')
    step.trigger.any_of[0][0].source = 'event_transition_up'
    assert not shown(bridge.sessions, 'gear_down')['checked']
    step.trigger.any_of[0][0].source = 'phase_arrival'
    step.validation.automatic.signal = 'flaps_handle_index'
    step.validation.automatic.equals = 1
    bridge.settings.validated.append('flaps_handle_index')
    bridge.settings.copilot_bindings.append(ObservationBinding(signal='flaps_handle_index', key='flaps_handle_index',
        variable='FLAPS HANDLE INDEX', origin='simvar', aircraft_title='A320 fictif', values={'1': 1}))
    bridge.live.update({'connected': True, 'telemetry': {'flaps_handle_index': (1., now[0])}})
    assert not shown(bridge.sessions, 'gear_down')['checked']


def test_failed_write_does_not_publish_unpersisted_detection(tmp_path, monkeypatch):
    now = [1000.]
    bridge = live(tmp_path, now)
    before = bridge.sessions.path('simconnect').read_bytes()
    bridge.live.update({'connected': True, 'telemetry': {'gear_handle_down': (False, now[0])}})
    def fail(*args): raise OSError('Fictional failure')
    monkeypatch.setattr('glareshield.copilot.session.atomic_write', fail)
    result = shown(bridge.sessions, 'gear_down')
    assert not result['checked'] and not result['detection_current']
    assert bridge.sessions.view()['warnings']
    assert bridge.sessions.path('simconnect').read_bytes() == before


def test_reconfigured_source_discards_cached_sample(tmp_path):
    now = [1000.]
    bridge = live(tmp_path, now)
    settings = bridge.settings.model_copy(deep=True)
    settings.disabled.append('gear_handle_down')
    bridge.save(settings)
    assert 'gear_handle_down' not in bridge.live.samples
    assert not shown(bridge.sessions, 'gear_down')['checked']
