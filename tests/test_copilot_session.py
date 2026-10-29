"""Fictional plans and isolated roots only; no simulator or lighting commands."""
import json

import pytest

from glareshield.aibridge.service import AIBridge
from glareshield.copilot.session import DeclarationInput
from test_aibridge_web import client_and_headers


def demo(root, clock=None):
    bridge = AIBridge(root, **({'clock': clock} if clock else {}))
    bridge.set_scenario(True)
    bridge.load_demo_plan()
    return bridge


def first_step(service, observed=False):
    return next(s.id for p in service.profile.phases for g in p.groups for s in g.steps
                if (s.validation.mode == 'observed') == observed)


def shown(service, step_id):
    return next(s for g in service.view()['groups'] for s in g['steps'] if s['id'] == step_id)


def declaration(kind='selection', **overrides):
    examples = {
        'selection': dict(field='selection.runway', value='27', unit=None,
                          context={'stage': 'departure'}),
        'clearance': dict(field='clearance.altitude', value=5000, unit='ft',
                          context={'type': 'departure', 'station': 'XXAA_TWR'}),
        'atis': dict(field='atis.heard_letter', value='A', unit=None,
                     context={'airport': 'XXAA', 'version': 'ATIS-A-1200Z'}),
        'performance': dict(field='performance.v1', value=130, unit='kt',
                            context={'aircraft': 'A320 fictif', 'runway': '27', 'mass': '60000 kg',
                                     'configuration': '1+F', 'weather': 'vent calme 15 C'}),
    }
    return DeclarationInput(kind=kind, reference='Référence fictive', **{**examples[kind], **overrides})


def test_restart_keeps_manual_steps_phase_declarations_and_reminders(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    session_id = service.start()['session']['id']
    step = first_step(service)
    service.set_step(step, True)
    service.force_phase('cruise')
    for kind in ('selection', 'clearance', 'atis', 'performance'):
        service.declare(declaration(kind))
    service.remember('arrival_notice', 'fictional-reference')
    bridge.set_notes('Clairance FL999 : texte libre fictif, sans effet structuré.')
    restarted = AIBridge(tmp_path)
    restarted.set_scenario(True)
    view = restarted.sessions.view()
    assert view['session']['id'] == session_id
    assert shown(restarted.sessions, step)['checked'] is True
    assert view['session']['forced_phase'] == 'cruise'
    assert len(view['session']['declarations']) == 4
    assert view['session']['declarations'][1]['value'] == 5000
    assert view['session']['reminders']['arrival_notice']['checked']
    assert restarted.notes == bridge.notes
    assert restarted.sessions.start()['session']['id'] == session_id


def test_same_corrected_and_new_plan_have_deterministic_progress(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    old_id = service.start()['session']['id']
    step = first_step(service)
    service.set_step(step, True)
    service.declare(declaration())
    plan = json.loads(json.dumps(bridge.plan.plan))
    bridge.plan.store(plan, 'demo')
    assert service.view()['session']['plan_revision'] == 1
    assert shown(service, step)['checked']
    plan['route'] = 'DCT FICTION DCT'
    bridge.plan.store(plan, 'demo')
    view = service.view()
    assert view['session']['id'] == old_id
    assert view['session']['plan_revision'] == 2
    assert view['session']['declarations'][0]['invalidated_reason']
    assert shown(service, step)['checked']
    bridge.plan.clear()
    assert service.view()['session']['id'] == old_id
    plan['ofp_id'] = 'fictional-new-ofp'
    bridge.plan.store(plan, 'demo')
    new = service.view()
    assert new['session']['id'] != old_id
    assert new['session']['steps'] == {}
    assert new['session']['declarations'] == []
    assert new['archived_count'] == 1 and new['warnings']
    archived = service.documents['demo'].sessions[0]
    assert archived.steps[step].manual.checked
    assert archived.end_reason == 'new_plan'


def test_fallback_identity_and_first_plan_attachment(tmp_path):
    bridge = demo(tmp_path)
    plan = bridge.plan.plan.copy()
    plan.pop('ofp_id', None)
    bridge.plan.clear()
    session_id = bridge.sessions.start()['session']['id']
    bridge.sessions.set_step(first_step(bridge.sessions), True)
    bridge.plan.store(plan, 'demo')
    assert bridge.sessions.view()['session']['id'] == session_id
    plan['generated_utc'] = '2026-01-01T13:00:00Z'
    bridge.plan.store(plan, 'demo')
    assert bridge.sessions.view()['session']['id'] == session_id
    plan = json.loads(json.dumps(plan))
    plan.setdefault('times', {})['scheduled_out_utc'] = '2026-01-02T12:00:00Z'
    bridge.plan.store(plan, 'demo')
    assert bridge.sessions.view()['session']['id'] != session_id


def test_manual_uncheck_overrides_detection_and_preserves_conflict(tmp_path):
    now = [1000.0]
    bridge = demo(tmp_path, lambda: now[0])
    service = bridge.sessions
    service.start()
    step = first_step(service, observed=True)
    service.record_detection(step, True, 'fictional-measurement', 'demo')
    assert shown(service, step)['provenance'] == 'detected'
    service.set_step(step, False)
    service.force_phase('arrival')
    service.record_detection(step, True, 'fictional-measurement-2', 'demo')
    result = shown(service, step)
    assert not result['checked'] and result['provenance'] == 'manual' and result['conflict']
    assert result['detected']['checked']
    with pytest.raises(ValueError):
        service.record_detection(step, True, 'foreign-universe', 'simconnect')
    with pytest.raises(ValueError):
        service.record_detection(first_step(service), True, 'manual-only', 'demo')
    restarted = AIBridge(tmp_path, clock=lambda: now[0])
    restarted.set_scenario(True)
    result = shown(restarted.sessions, step)
    assert not result['checked'] and result['manual'] and result['detected']
    assert not result['detection_current']


def test_detection_is_history_after_restart_or_loss_of_fresh_data(tmp_path):
    now = [1000.0]
    bridge = demo(tmp_path, lambda: now[0])
    service = bridge.sessions
    service.start()
    step = first_step(service, observed=True)
    service.record_detection(step, True, 'fictional-measurement', 'demo')
    now[0] += 9
    assert not shown(service, step)['checked']
    assert shown(service, step)['detected']['checked']
    restarted = AIBridge(tmp_path, clock=lambda: now[0])
    restarted.set_scenario(True)
    assert not shown(restarted.sessions, step)['checked']


def test_demo_and_live_are_isolated_and_share_existing_bridge(tmp_path):
    bridge = demo(tmp_path)
    demo_id = bridge.sessions.start()['session']['id']
    bridge.sessions.set_step(first_step(bridge.sessions), True)
    bridge.set_scenario(False)
    assert bridge.sessions.view()['session'] is None
    with pytest.raises(ValueError):
        bridge.sessions.start()
    bridge.settings.enabled = True
    bridge.on_simulator_message({'connected': True, 'paused': False})
    live_id = bridge.sessions.start()['session']['id']
    assert live_id != demo_id
    assert bridge.sessions.view()['session']['plan_key'] is None
    assert bridge.sessions.view()['session']['steps'] == {}
    bridge.sessions.end()
    assert bridge.sessions.resume()['session']['id'] == live_id
    bridge.set_scenario(True)
    assert bridge.sessions.view()['session']['id'] == demo_id
    assert (tmp_path/'local/copilot/sessions-demo.json').is_file()
    assert (tmp_path/'local/copilot/sessions-simconnect.json').is_file()


@pytest.mark.parametrize('raw', ['{invalid', '{"schema_version":"glareshield.copilot_session/0"}', '[]'])
def test_invalid_or_old_file_is_preserved_until_explicit_reset(tmp_path, raw):
    path = tmp_path/'local/copilot/sessions-demo.json'
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding='utf-8')
    bridge = demo(tmp_path)
    service = bridge.sessions
    assert service.view()['storage_blocked'] and service.view()['warnings']
    assert path.read_text(encoding='utf-8') == raw
    with pytest.raises(ValueError):
        service.start()
    assert service.reset()['session']['steps'] == {}
    assert not service.view()['storage_blocked']
    backups = list(path.parent.glob('sessions-demo-preserved-*.json'))
    assert len(backups) == 1 and backups[0].read_text(encoding='utf-8') == raw


def test_reset_archives_and_profile_revision_never_silently_migrates(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    old_id = service.start()['session']['id']
    service.set_step(first_step(service), True)
    service.profile = service.profile.model_copy(update={'revision': service.profile.revision+1})
    assert service.view()['warnings']
    with pytest.raises(ValueError):
        service.set_step(first_step(service), False)
    view = service.reset()
    assert view['session']['id'] != old_id and view['session']['steps'] == {}
    assert service.documents['demo'].sessions[0].steps


def test_failed_write_does_not_change_memory_or_disk(tmp_path, monkeypatch):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start()
    path = service.path('demo')
    before = path.read_bytes()
    def fail(*args):
        raise OSError('fictional disk failure')
    monkeypatch.setattr('glareshield.copilot.session.atomic_write', fail)
    with pytest.raises(OSError):
        service.set_step(first_step(service), True)
    assert service.view()['session']['steps'] == {}
    assert path.read_bytes() == before
    bridge.plan.plan['route'] = 'DCT CHANGED'
    assert service.view()['warnings']
    assert path.read_bytes() == before


def test_declaration_validation_revisions_invalidation_and_revoke(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start()
    for kind in ('clearance', 'selection', 'atis', 'performance'):
        with pytest.raises(ValueError):
            declaration(kind, context={})
        service.declare(declaration(kind))
    service.declare(declaration('atis', value='B', context={'airport':'XXAA', 'version':'B-1230Z'}))
    declarations = service.view()['session']['declarations']
    assert declarations[2]['value'] == 'A' and declarations[2]['revoked_at']
    assert declarations[-1]['revision'] == 2
    assert declarations[3]['invalidated_reason']
    service.revoke(declarations[-1]['id'])
    assert service.view()['session']['declarations'][-1]['revoked_at']
    with pytest.raises(ValueError):
        declaration('performance', unit=None)
    bridge.set_notes('ATIS Z, piste 09, V1 999 : note fictive')
    assert len(service.view()['session']['declarations']) == 5


def test_declaration_scopes_and_performance_context_changes(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start()
    service.declare(declaration('selection'))
    service.declare(declaration('selection', value='09', context={'stage': 'arrival'}))
    service.declare(declaration('atis', occurred_at=bridge.clock()-600))
    service.declare(declaration('atis', context={'airport':'XXBB', 'version':'B-1300Z'}))
    state = service.view()['session']['declarations']
    assert all(d['revoked_at'] is None for d in state)
    assert all(d['revision'] == 1 for d in state)
    assert state[2]['occurred_at'] < state[2]['recorded_at']
    service.declare(declaration('performance'))
    changed = declaration('performance', field='performance.v2')
    changed.context['mass'] = '62000 kg'
    service.declare(changed)
    assert service.view()['session']['declarations'][-2]['invalidated_reason']
    with pytest.raises(ValueError):
        service.declare(declaration('atis', occurred_at=bridge.clock()+3600))


def test_plan_change_rejects_gesture_from_previous_flight(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    runtime.ai.set_scenario(True)
    runtime.ai.load_demo_plan()
    state = runtime.ai.sessions.start()
    target = {'session_id':state['session']['id'], 'universe':'demo', 'checked':True}
    plan = runtime.ai.plan.plan.copy()
    plan['ofp_id'] = 'fictional-next-flight'
    runtime.ai.plan.store(plan, 'demo')
    step_id = first_step(runtime.ai.sessions)
    response = client.put('/api/ai/session/steps/'+step_id, json=target, headers=headers)
    assert response.status_code == 409
    assert runtime.ai.sessions.view()['session']['steps'] == {}


def test_routes_protected_stale_gestures_and_no_runtime_reconfigure(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    runtime.ai.set_scenario(True)
    with client:
        assert client.get('/api/ai/session').status_code == 403
        state = client.get('/api/ai/session', headers=headers).json()
        target = {'session_id': None, 'universe': 'demo'}
        assert client.post('/api/ai/session/start', json=target).status_code == 403
        state = client.post('/api/ai/session/start', json=target, headers=headers).json()
        target['session_id'] = state['session']['id']
        step_id = state['groups'][0]['steps'][0]['id']
        path = '/api/ai/session/steps/'+step_id
        assert client.put(path, json={**target, 'checked': True}).status_code == 403
        assert client.put(path, json={**target, 'checked': True}, headers=headers).status_code == 200
        assert client.put(path, json={**target, 'checked': 'yes'}, headers=headers).status_code == 422
        assert client.put('/api/ai/session/phase', json={**target, 'phase':'invalid'}, headers=headers).status_code == 422
        assert client.put('/api/ai/session/declarations', json={**target, 'declaration':declaration().model_dump()}, headers=headers).status_code == 200
        assert client.post('/api/ai/session/reset', json=target, headers=headers).status_code == 200
        assert client.put(path, json={**target, 'checked': True}, headers=headers).status_code == 409
        assert client.get('/api/ai/session', headers=headers).json()['session']['steps'] == {}
        state = client.get('/api/ai/session', headers=headers).json()
        target['session_id'] = state['session']['id']
        runtime.ai.set_scenario(False)
        assert client.put(path, json={**target, 'checked': True}, headers=headers).status_code == 409
        assert runtime.changes == 0
