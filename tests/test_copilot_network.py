"""Copilot network contract: fictional fixtures, disposable roots, no real HTTP or cockpit."""
from copy import deepcopy

import pytest

from glareshield.aibridge.config import IVAOSettings
from glareshield.aibridge.service import AIBridge
from glareshield.copilot.contract import QualifiedValue
from glareshield.copilot.session import DeclarationInput
from test_aibridge_web import client_and_headers
from test_ivao import Clock, Network, atc, bridge_with_network, stamp, whazzup


def setup(root):
    clock, network = Clock(), Network()
    network.payloads = deepcopy(network.payloads)
    # Keep the observation fresh; the older integration fixtures intentionally include old bulletins.
    for item in network.payloads['metar']:
        if 'metar' in item:
            item['metar'] = item['metar'].replace('260600Z', '260730Z')
    bridge = bridge_with_network(root, clock, network)
    bridge.set_scenario(True)
    bridge.sessions.start()
    return bridge, clock, network


def view(bridge):
    return bridge.sessions.view()['network']


def station(bridge, callsign='XXNC_TWR'):
    return bridge.sessions.declare(DeclarationInput(
        kind='station', field='station.callsign', value=callsign,
        reference='Contact radio déclaré fictif', context={'stage': 'arrival'}))


def heard(bridge, letter='K', field='heard_letter'):
    return bridge.sessions.declare(DeclarationInput(
        kind='atis', field='atis.'+field, value=letter, reference='Écoute fictive',
        context={'airport': 'XXNC', 'version': 'Référence pilote fictive'}))


@pytest.mark.asyncio
async def test_disabled_unknown_empty_and_stale_remain_distinct(tmp_path):
    bridge = AIBridge(tmp_path)
    assert view(bridge)['state'] == 'disabled'
    bridge, clock, network = setup(tmp_path)
    assert view(bridge)['state'] == 'unknown'
    assert view(bridge)['positions'] is None
    network.payloads['whazzup'] = whazzup([])
    await bridge.ivao.refresh()
    data = view(bridge)
    assert data['state'] == 'empty' and data['positions'] == []
    clock.now += 16
    network.failures['whazzup'] = 'offline'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    data = view(bridge)
    assert data['state'] == 'stale' and data['positions'] == []
    assert data['feeds']['whazzup']['last_error']
    assert data['events']['events'] == [], 'A failed poll never invents disconnections'
    bridge.ivao.configure(IVAOSettings(enabled=False))
    assert view(bridge)['state'] == 'disabled' and view(bridge)['positions'] is None


@pytest.mark.asyncio
async def test_all_readers_share_cache_and_page_renders_never_fetch(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    runtime, client, headers = client_and_headers(tmp_path)
    runtime.ai = bridge
    before = network.requests.copy()
    with client:
        for _ in range(3):
            for endpoint in ('session', 'ivao', 'status', 'context'):
                assert client.get('/api/ai/'+endpoint, headers=headers).status_code == 200
            data = bridge.sessions.view()
            # Future reminder/radio consumers use this same adapter and stream, not another collector.
            assert data['network'] == bridge.flight_network.view(
                data['phase'], bridge.sessions.documents['demo'].sessions[-1])
        assert client.get('/api/ai/session').status_code == 403
    assert network.requests == before == ['whazzup', 'metar', 'taf']


@pytest.mark.asyncio
async def test_current_and_next_phase_positions_keep_matching_and_published_frequencies(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    assert view(bridge)['phase'] is None  # Placed only after a few stable seconds of measurements.
    for _ in range(4):
        clock.now += 1
        data = view(bridge)
    assert data['phase'] == 'preflight' and data['next_phase'] == 'departure'
    ground = next(p for p in data['positions'] if p['callsign'] == 'XXPO_GND')
    assert 'current' in ground['useful_for'] or 'next' in ground['useful_for']
    assert ground['frequency_mhz'] == 121.8
    assert ground['provenance']['source'] == 'ivao.whazzup'
    assert ground['matched_by'][0]['basis'] == 'callsign_prefix'
    tower = next(p for p in data['positions'] if p['callsign'] == 'XXNC_TWR')
    assert tower['useful_for'] == []
    bridge.sessions.force_phase('cruise')
    data = view(bridge)
    assert data['next_phase'] == 'descent'
    assert 'next' in next(p for p in data['positions'] if p['callsign'] == 'XXNC_APP')['useful_for']
    assert all(p['coverage'] == 'unconfirmed' for p in data['positions'])
    assert not any(p['callsign'].endswith('OBS') for p in data['positions'])


@pytest.mark.asyncio
async def test_geographical_match_never_becomes_confirmed_coverage(tmp_path):
    bridge, clock, network = setup(tmp_path)
    network.payloads['whazzup']['clients']['atcs'].append(atc('XXAB_APP', 'APP', 43.60, 7.10))
    await bridge.ivao.refresh()
    bridge.sessions.force_phase('arrival')
    data = view(bridge)
    nearby = next(p for p in data['positions'] if p['callsign'] == 'XXAB_APP')
    assert nearby['coverage'] == 'unconfirmed'
    assert nearby['useful_for'] == ['current']
    assert all(m['basis'] != 'callsign_prefix' for m in nearby['matched_by'])
    assert any(m['basis'] == 'distance_to_airport' for m in nearby['matched_by'])
    station(bridge, 'XXAB_APP')
    nearby = next(p for p in view(bridge)['positions'] if p['callsign'] == 'XXAB_APP')
    assert nearby['pilot_selected'] and nearby['coverage'] == 'unconfirmed'


@pytest.mark.asyncio
async def test_station_declaration_can_select_distant_station_and_survives_restart(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    station(bridge, 'YYYY_TWR')
    data = view(bridge)
    far = next(p for p in data['positions'] if p['callsign'] == 'YYYY_TWR')
    assert far['pilot_selected'] and far['matched_by'] == []
    QualifiedValue.model_validate(data['used_station'])
    restarted = AIBridge(tmp_path, clock)
    restarted.set_scenario(True)
    assert view(restarted)['used_station']['value'] == 'YYYY_TWR'
    assert view(restarted)['state'] == 'unknown', 'Restart retains settings, but has not fetched anything'
    restarted.ivao.configure(IVAOSettings(enabled=False))
    assert view(restarted)['state'] == 'disabled'
    assert view(restarted)['used_station']['value'] == 'YYYY_TWR'
    declaration_id = data['used_station']['reference']
    bridge.sessions.revoke(declaration_id)
    assert view(bridge)['used_station'] is None


@pytest.mark.asyncio
async def test_published_consulted_and_announced_atis_stay_separate(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    data = view(bridge)
    assert data['atis'] and data['pilot_atis'] == []
    heard(bridge)
    heard(bridge, 'J', 'announced_letter')
    data = view(bridge)
    assert len(data['pilot_atis']) == 2
    assert data['pilot_atis'][0]['comparison'] == 'same_letter'
    assert data['pilot_atis'][1]['comparison'] == 'different_letter'
    assert data['atis'][0]['reading_status'] == 'not_interpreted'
    clock.now += 16
    tower = network.payloads['whazzup']['clients']['atcs'][0]
    tower['atis']['revision'] = 'L'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    data = view(bridge)
    assert [a['value'] for a in data['pilot_atis']] == ['K', 'J']
    assert all(a['comparison'] == 'different_letter' for a in data['pilot_atis'])
    assert any(e['kind'] == 'atis_changed' for e in data['events']['events'])
    assert len(data['atis'][0]['reference']) < 100
    assert data['atis'][0]['provenance']['publication_age_s'] > 600


@pytest.mark.asyncio
async def test_cutoff_old_source_and_old_bulletin_propagate_independently(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    heard(bridge)
    clock.now += 16
    network.failures['whazzup'] = 'offline'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    data = view(bridge)
    assert data['state'] == 'stale' and data['positions']
    assert data['pilot_atis'][0]['comparison'] == 'unknown'
    assert data['publications']['arrival']['qnh']['status'] == 'available'
    network.failures.clear()
    clock.now += 16
    network.payloads['whazzup']['updatedAt'] = stamp(-3600)
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    data = view(bridge)
    assert data['state'] == 'stale'
    assert data['feeds']['whazzup']['fetched_age_s'] == 0
    assert data['feeds']['whazzup']['source_age_s'] > 3600
    clock.now += 1300
    data = view(bridge)
    assert data['atis'][0]['provenance']['status'] == 'stale'
    assert data['publications']['arrival']['qnh']['status'] == 'stale'
    assert data['publications']['arrival']['qnh']['value'] == 1015
    assert data['publications']['arrival']['qnh']['source_text'].startswith('XXNC')


@pytest.mark.asyncio
async def test_event_stream_reuses_collection_is_non_consuming_and_does_not_duplicate_notices(tmp_path):
    bridge, clock, network = setup(tmp_path)
    notices = []
    bridge.ivao.settings.notifications = True
    bridge.ivao.notifier = lambda lines, seconds: notices.append(lines)
    await bridge.ivao.refresh()
    assert view(bridge)['events']['events'] == [] and notices == []
    clock.now += 16
    atcs = network.payloads['whazzup']['clients']['atcs']
    atcs[:] = [a for a in atcs if a['callsign'] != 'XXPO_GND']
    atcs.append(atc('XXNC_DEL', 'DEL', 43.66, 7.22))
    atcs[0]['atis']['revision'] = 'L'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    data = view(bridge)['events']
    assert {e['kind'] for e in data['events']} == {'connected', 'disconnected', 'atis_changed'}
    assert len(notices) == 1
    assert data == view(bridge)['events']
    assert len(notices) == 1
    last = data['latest_sequence']
    assert bridge.ivao.event_view(last)['events'] == []
    data['events'][0]['kind'] = 'mutated by reader'
    assert view(bridge)['events']['events'][0]['kind'] != 'mutated by reader'
    clock.now += 16
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    assert bridge.ivao.event_view(last)['events'] == [] and len(notices) == 1
    for _ in range(300):
        bridge.ivao.record_event('atis_changed', 'XXNC_TWR', clock.now)
    assert len(bridge.ivao.event_view()['events']) == 256
    assert bridge.ivao.event_view(last)['gap']


@pytest.mark.asyncio
@pytest.mark.parametrize('raw,field,expected,reading', [
    ('XXNC 260600Z 09006KT CAVOK 20/12 Q1015', 'qnh', 1015, 'parsed'),
    ('XXNC 260600Z VRB03KT CAVOK M05/M10 Q1015', 'temperature', -5, 'parsed'),
    ('XXNC 260600Z 09006G15KT CAVOK 20/12 Q1015', 'wind', '09006G15KT', 'parsed'),
    ('XXNC 260600Z 09006KT CAVOK 20/12 Q1015 Q1016', 'qnh', None, 'ambiguous'),
    ('XXNC 260600Z 09006KT CAVOK 20/12 Q1015 A2992', 'qnh', None, 'ambiguous'),
    ('XXNC 260600Z 09006KT CAVOK 20/12 Q0000', 'qnh', None, 'ambiguous'),
    ('XXNC 260600Z 09006KT CAVOK 20/12 A2992', 'qnh', None, 'missing'),
    ('XXNC 260600Z 09006KT CAVOK 20/12 Q1015 TEMPO Q0999', 'qnh', 1015, 'parsed'),
    ('Airport info QNH 1015', 'qnh', None, 'unsupported'),
    ('XXZZ 260600Z 09006KT CAVOK 20/12 Q1015', 'qnh', None, 'unsupported'),
])
async def test_publication_values_keep_source_reading_and_qualification(tmp_path, raw, field, expected, reading):
    bridge, clock, network = setup(tmp_path)
    network.payloads['metar'][0]['metar'] = raw
    await bridge.ivao.refresh()
    value = view(bridge)['publications']['arrival'][field]
    assert value['value'] == expected and value['reading_status'] == reading
    assert value['source_text'] == raw and value['nature'] == 'published'
    assert value['source'] == 'ivao.metar'
    QualifiedValue.model_validate({key: value[key] for key in QualifiedValue.model_fields})


@pytest.mark.asyncio
async def test_other_universe_plan_and_invalidated_declarations_are_excluded(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    station(bridge)
    plan = deepcopy(bridge.plan.plan)
    plan['route'] = 'DCT FICTION DCT'
    bridge.plan.store(plan, 'demo')
    assert view(bridge)['used_station'] is None
    bridge.set_scenario(False)
    data = view(bridge)
    assert data['publications'] == {} and data['weather'] == []
    assert data['used_station'] is None


def test_station_declaration_api_is_protected_and_rejects_invalid_fields(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    runtime.ai.set_scenario(True)
    runtime.ai.load_demo_plan()
    data = runtime.ai.sessions.start()
    payload = {'session_id': data['session']['id'], 'universe': 'demo', 'declaration': {
        'kind': 'station', 'field': 'station.callsign', 'value': 'XXNC_TWR',
        'reference': 'Contact fictif', 'context': {'stage': 'arrival'}}}
    with client:
        assert client.put('/api/ai/session/declarations', json=payload).status_code == 403
        response = client.put('/api/ai/session/declarations', json=payload, headers=headers)
        assert response.status_code == 200
        assert response.json()['network']['used_station']['value'] == 'XXNC_TWR'
        payload['declaration']['field'] = 'station.anything'
        assert client.put('/api/ai/session/declarations', json=payload, headers=headers).status_code == 422


@pytest.mark.asyncio
async def test_atis_text_change_same_letter_is_an_event_without_confirming_pilot_reading(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    heard(bridge)
    previous = next(a for a in view(bridge)['atis'] if a['station'] == 'XXNC_TWR')['reference']
    clock.now += 16
    network.payloads['whazzup']['clients']['atcs'][0]['atis']['lines'].append('QNH 9999: unsupported free text')
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    data = view(bridge)
    event = data['events']['events'][0]
    assert event['kind'] == 'atis_changed' and event['change'] == 'text'
    assert next(a for a in data['atis'] if a['station'] == 'XXNC_TWR')['reference'] != previous
    assert data['pilot_atis'][0]['value'] == 'K' and data['pilot_atis'][0]['comparison'] == 'same_letter'
    assert data['publications']['arrival']['qnh']['value'] == 1015, 'ATIS free text does not override METAR'


@pytest.mark.asyncio
async def test_truncated_and_ambiguous_publications_stay_unknown_and_missing_station_is_explicit(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    station(bridge, 'XXNO_TWR')
    data = view(bridge)
    assert data['used_station']['value'] == 'XXNO_TWR' and data['used_station_state'] == 'offline'
    bridge.ivao.metar.data['XXNC']['truncated'] = True
    assert view(bridge)['publications']['arrival']['qnh']['value'] is None
    assert view(bridge)['publications']['arrival']['qnh']['reading_status'] == 'truncated'
    clock.now += 16
    # Two airport ATIS publications: a letter cannot be arbitrated without a station declaration.
    copy = deepcopy(network.payloads['whazzup']['clients']['atcs'][0]['atis'])
    network.payloads['whazzup']['clients']['atcs'].append(atc('XXNC_DEL', 'DEL', 43.66, 7.22, atis=copy))
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    heard(bridge)
    assert view(bridge)['pilot_atis'][0]['comparison'] == 'unknown'


@pytest.mark.asyncio
async def test_weather_feed_failure_does_not_hide_current_positions_or_replace_source_age(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    clock.now += 61
    network.failures['metar'] = 'offline'
    await bridge.ivao.fetch(bridge.ivao.metar)
    data = view(bridge)
    assert data['state'] == 'current'
    qnh = data['publications']['arrival']['qnh']
    assert qnh['status'] == 'stale' and qnh['value'] == 1015
    assert qnh['provenance']['fetched_age_s'] == 61
    assert qnh['provenance']['ivao_updated_age_s'] > qnh['provenance']['fetched_age_s']
    # The event stream remains available with overlay notifications disabled.
    assert bridge.ivao.settings.notifications is False
    clock.now += 16
    network.payloads['whazzup']['clients']['atcs'][0]['atis']['revision'] = 'L'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    assert any(e['kind'] == 'atis_changed' for e in view(bridge)['events']['events'])
