"""Contract acceptance checks, entirely offline with independent private roots."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from glareshield.copilot.contract import (
    MAX_PROFILE_BYTES, PHASE_IDS, Profile, QualifiedValue, builtin_profile, load_profile,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def profile_data():
    return builtin_profile().model_dump(mode='json')


def write_custom(root, data):
    path = root/'local/copilot/profile.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


def test_a320_is_consumable_by_a_generic_renderer_without_aircraft_branches():
    profile = builtin_profile()
    rendered = []
    for phase in profile.phases:
        groups = []
        for group in phase.groups:
            rows = [(step.id, step.label, [profile.values[key].placeholder for key in step.expected])
                    for step in group.steps]
            groups.append((group.kind, rows))
        rendered.append((phase.id, groups))
    assert tuple(item[0] for item in rendered) == PHASE_IDS
    assert {kind for _, groups in rendered for kind, _ in groups} == {'mcdu', 'fcu', 'checklist'}
    assert all(rows for _, groups in rendered for _, rows in groups)
    assert Profile.model_validate_json(profile.model_dump_json()) == profile
    assert 'phases' in Profile.model_json_schema()['required']


def test_six_fictitious_phase_outputs_preserve_qualification_and_unknowns():
    data = json.loads((ROOT/'examples/copilot-six-phases.json').read_text(encoding='utf-8'))
    profile = builtin_profile()
    assert tuple(example['phase'] for example in data['examples']) == PHASE_IDS
    for phase, example in zip(profile.phases, data['examples']):
        assert example['data_origin'] == 'simulation_scenario'
        facts = {key: QualifiedValue.model_validate(value) for key, value in example['values'].items()}
        assert facts['phase'].value == phase.id and facts['phase'].status == 'derived'
        assert facts['altitude_msl'].status == 'simulated'
        assert example['now_step'] in {step.id for group in phase.groups for step in group.steps}
        clearance = facts['cleared_altitude']
        if clearance.value is None:
            assert clearance.status == 'unavailable'
            assert profile.values['cleared_altitude'].placeholder == '<altitude autorisée>'
    assert data['examples'][-1]['conflicts'][0]['heard'] != data['examples'][-1]['conflicts'][0]['published']


@pytest.mark.parametrize('change', [
    lambda p: p.update(schema_version='glareshield.copilot_profile/99'),
    lambda p: p['phases'].reverse(),
    lambda p: p['phases'].pop(),
    lambda p: p['phases'][1]['groups'][0]['steps'][0].update(id='init_a'),
    lambda p: p['phases'][0]['groups'][0]['steps'][0].update(expected=['missing']),
    lambda p: p['values']['zfw'].update(unit='lb'),
    lambda p: p['values']['cleared_altitude'].update(sources=['plan_cruise_altitude']),
    lambda p: p['values']['v1'].update(sources=['plan_cruise_altitude'], unit='ft'),
    lambda p: p['values']['qnh'].update(sources=['missing']),
    lambda p: p['sources']['on_ground'].update(max_age_s=None),
    lambda p: p['phases'][0]['trigger']['any_of'][0][0].update(source='missing'),
    lambda p: p['phases'][0]['trigger']['any_of'][0][0].update(op='eval'),
    lambda p: p['phases'][0]['trigger']['any_of'][0][0].update(value='true'),
    lambda p: p['phases'][0]['groups'][0]['steps'][0].update(priority=101),
    lambda p: p['phases'][0]['radio'][0]['voice_fr'].update(pilot='{callsign.__class__}'),
    lambda p: p['phases'][0]['radio'][0]['voice_fr'].update(pilot='{callsign!r}'),
    lambda p: p['phases'][0]['radio'][0]['voice_fr'].update(pilot='{callsign:>100}'),
    lambda p: p['phases'][0]['radio'][0]['voice_fr'].update(pilot='{'),
    lambda p: p['phases'][-1]['groups'][1]['steps'][0].update(
        validation={'mode':'observed','automatic':{'signal':'fma_appr_armed','equals':True}}),
    lambda p: p['phases'][-1]['groups'][1]['steps'][0].update(
        validation={'mode':'observed','automatic':{'signal':'appr_button_lit','equals':True}}),
    lambda p: p['phases'][2]['groups'][1]['steps'][0]['validation']['automatic'].update(equals=1),
    lambda p: p.update(unknown_option=True),
])
def test_invalid_customization_is_rejected_atomically_with_builtin_fallback(tmp_path, profile_data, change):
    change(profile_data)
    write_custom(tmp_path, profile_data)
    result = load_profile(tmp_path)
    assert result.origin == 'builtin' and result.errors
    assert result.profile == builtin_profile()


def test_last_valid_custom_profile_survives_bad_reload_and_removal_resets(tmp_path, profile_data):
    assert load_profile(tmp_path).origin == 'builtin'
    profile_data['aircraft'] = 'A320 — checklist fictive adaptée'
    profile_data['revision'] = 2
    path = write_custom(tmp_path, profile_data)
    loaded = load_profile(tmp_path)
    assert loaded.origin == 'custom' and not loaded.errors
    original = path.read_bytes()
    assert load_profile(tmp_path).profile == loaded.profile
    assert path.read_bytes() == original  # Loading never saves or repairs a user file.
    path.write_text('{broken', encoding='utf-8')
    failed = load_profile(tmp_path, loaded.profile)
    assert failed.origin == 'last_valid' and failed.profile is loaded.profile and failed.errors
    path.unlink()
    assert load_profile(tmp_path, loaded.profile).origin == 'builtin'


@pytest.mark.parametrize('content', [
    b'{"schema_version": "one", "schema_version": "two"}', b'\xff',
    b'x'*(MAX_PROFILE_BYTES+1), b'['*2000+b']'*2000,
], ids=['duplicate_keys', 'invalid_utf8', 'oversized', 'too_deep'])
def test_unreadable_oversized_or_duplicate_json_does_not_break_loading(tmp_path, content):
    path = write_custom(tmp_path, {})
    path.write_bytes(content)
    result = load_profile(tmp_path)
    assert result.origin == 'builtin' and result.errors


def test_errors_never_echo_custom_values_or_unknown_keys(tmp_path, profile_data):
    secret = 'fixture-private-text-not-to-echo'
    profile_data['values'][secret] = {'label': secret}
    write_custom(tmp_path, profile_data)
    result = load_profile(tmp_path)
    assert result.errors and secret not in str(result.errors)


def test_no_fma_or_planned_value_can_supply_automatic_confirmation():
    profile = builtin_profile()
    for phase in profile.phases:
        for group in phase.groups:
            for step in group.steps:
                if step.validation.automatic:
                    assert step.validation.automatic.signal in {'gear_handle_down', 'baro_std'}
                if step.id == 'appr_button' or step.id == 'check_cleared_route':
                    assert step.validation.mode == 'manual'
    for value in profile.values.values():
        if value.purpose in ('clearance', 'performance'):
            assert value.literal is None
            assert all(profile.sources[key].nature == 'declared' for key in value.sources)


def test_voice_and_unicom_templates_resolve_only_declared_parameters():
    profile = builtin_profile()
    placeholders = {key: item.placeholder for key, item in profile.values.items()}
    placeholders.update(callsign='DEMO123', origin='ZZAA', destination='ZZBB')
    for phase in profile.phases:
        for radio in phase.radio:
            assert 'DEMO123' in radio.voice_fr.pilot.format_map(placeholders)
            assert 'DEMO123' in radio.voice_en.pilot.format_map(placeholders)
            if radio.unicom_en:
                assert 'DEMO123' not in radio.unicom_en.format_map(placeholders)


def fact(**changes):
    value = dict(value=123, unit='ft', nature='observed', status='observed', source='simconnect',
                 reference='fixture-reading', age_s=2, max_age_s=8, verification='unverified')
    value.update(changes)
    return value


@pytest.mark.parametrize('changes', [
    {'value':None}, {'status':'unavailable'}, {'age_s':None}, {'age_s':9}, {'age_s':-1}, {'max_age_s':None},
    {'value':float('nan')}, {'nature':'planned'}, {'status':'available'},
    {'status':'derived'}, {'nature':'calculated', 'status':'derived'},
    {'nature':'calculated','status':'observed','method':'fixture','inputs':['altitude']},
])
def test_invalid_qualifications_cannot_be_presented_as_current_or_derived(changes):
    with pytest.raises(ValidationError):
        QualifiedValue.model_validate(fact(**changes))


def test_zero_false_stale_and_unknown_are_distinct():
    assert QualifiedValue.model_validate(fact(value=0)).value == 0
    assert QualifiedValue.model_validate(fact(value=False, unit=None)).value is False
    assert QualifiedValue.model_validate(fact(value=123, status='stale', age_s=9)).value == 123
    assert QualifiedValue.model_validate(fact(value=None, status='unavailable', age_s=None)).value is None
    calculated = QualifiedValue.model_validate(fact(nature='calculated',status='derived',
        method='Difference from planned altitude.',inputs=['telemetry.altitude','plan.cruise']))
    assert calculated.method and calculated.inputs
