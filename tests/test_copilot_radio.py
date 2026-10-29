"""Fictional radio declarations and offline IVAO fixtures; never transmits."""
import pytest

from glareshield.copilot.radio import french_position
from glareshield.copilot.session import DeclarationInput
from test_copilot_session import demo, declaration
from test_copilot_network import setup


def messages(service):
    return service.view()['flight']['radio']


def station(service, callsign='LFXX_TWR', stage='arrival'):
    return service.declare(DeclarationInput(kind='station', field='station.callsign', value=callsign,
        reference='Station fictive déclarée', context={'stage': stage}))


def event(service, name, phase, value=True):
    return service.declare(DeclarationInput(kind='event', field='event.'+name, value=value,
        reference='Action fictive du pilote', context={'stage': phase}))


@pytest.mark.parametrize('callsign,expected', [
    ('LFXX_TWR', True), ('TFFX_APP', True), ('FMEE_APP', True), ('FMCZ_TWR', True),
    ('NWWX_CTR', True), ('NTXX_TWR', True), ('SOCA_APP', True),
    ('FMXX_TWR', False), ('XXXX_TWR', False), ('EGXX_CTR', False), (None, False)])
def test_language_uses_explicit_french_prefixes(callsign, expected):
    assert french_position(callsign) is expected


def test_sequences_cover_six_phases_and_parking_without_invented_clearances(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    expected = {
        'preflight': ['radio_clearance'],
        'departure': ['radio_pushback','radio_taxi','radio_takeoff'],
        'climb': ['radio_departure_contact'],
        'cruise': ['radio_descent_request','radio_enroute'],
        'descent': ['radio_approach_contact'],
        'arrival': ['radio_landing','radio_go_around','radio_vacated','radio_parked'],
    }
    for phase, ids in expected.items():
        service.force_phase(phase)
        result = messages(service)
        assert [m['id'] for m in result] == ids
        assert all(m['mode'] == 'choice' for m in result)
        assert all(m['station']['frequency_mhz'] is None for m in result)
        assert all(m['station']['coverage'] == 'unconfirmed' for m in result)
        assert all(m['voice_alternate'] for m in result)
        assert all('actual' in m['readback'] or '<' in m['readback'] for m in result)
    assert '<piste autorisée>' in messages(service)[0]['readback']


def test_language_and_clearance_corrections_refresh_without_changing_pilot_history(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    station(service, stage='preflight')
    assert messages(service)[0]['language'] == 'fr'
    assert messages(service)[0]['voice_alternate'] is None
    assert 'demandons clairance' in messages(service)[0]['voice']
    assert '<station>' in messages(service)[0]['voice']
    assert '<altitude autorisée>' in messages(service)[0]['readback']
    service.declare(declaration('clearance', value=5000))
    assert '5000 ft' in messages(service)[0]['readback']
    service.declare(declaration('clearance', value=6000))
    assert '6000 ft' in messages(service)[0]['readback']
    assert '5000' not in messages(service)[0]['readback']
    station(service, 'XXXX_TWR', 'preflight')
    assert messages(service)[0]['language'] == 'en'
    assert 'request IFR clearance' in messages(service)[0]['voice']
    before = service.path('demo').read_bytes()
    messages(service); messages(service)
    assert service.path('demo').read_bytes() == before


def test_unicom_is_one_english_line_without_the_flight_callsign(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start(); service.force_phase('departure')
    callsign = service.view()['flight']['values']['callsign']['value']
    origin = bridge.plan.plan['origin']['icao']
    for message in messages(service):
        assert '\n' not in message['unicom']
        assert callsign not in message['unicom']
        assert message['unicom'].startswith(origin+' ')
        assert message['unicom'].endswith(' '+origin)
    service.force_phase('cruise')
    assert next(m for m in messages(service) if m['id'] == 'radio_enroute')['unicom'] is None
    event(service, 'traffic_announcement', 'cruise')
    enroute = next(m for m in messages(service) if m['id'] == 'radio_enroute')
    assert enroute['trigger']['status'] == 'ready' and enroute['unicom']


def test_trigger_is_scoped_revocable_and_never_marks_a_message_emitted(tmp_path):
    service = demo(tmp_path).sessions
    service.start(); service.force_phase('arrival')
    event(service, 'go_around', 'departure')
    go_around = lambda: next(m for m in messages(service) if m['id'] == 'radio_go_around')
    assert go_around()['trigger']['status'] == 'unknown'
    result = event(service, 'go_around', 'arrival')
    assert messages(service)[0]['id'] == 'radio_go_around'
    assert go_around()['trigger']['status'] == 'ready'
    assert go_around()['trigger']['inputs'][0]['nature'] == 'declared'
    service.revoke(result['session']['declarations'][-1]['id'])
    assert go_around()['trigger']['status'] == 'unknown'
    assert not any(e.get('event') in ('radio_sent','radio_emitted') for e in service.view()['session']['history'])


@pytest.mark.asyncio
async def test_published_station_frequencies_and_unknown_coverage_remain_distinct(tmp_path):
    bridge, clock, network = setup(tmp_path)
    await bridge.ivao.refresh()
    service = bridge.sessions
    service.force_phase('arrival')
    message = messages(service)[0]
    assert message['station']['callsign'] == 'XXNC_TWR'
    assert message['station']['frequency_mhz'] == 118.7
    assert message['mode'] == 'choice' and message['language'] == 'en'
    station(service, 'XXNC_TWR')
    assert messages(service)[0]['mode'] == 'voice'
    clock.now += 16; network.failures['whazzup'] = 'offline'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    message = messages(service)[0]
    assert message['station']['frequency_mhz'] is None
    assert message['mode'] == 'choice'
    assert 'périmé' in message['station']['notice']


@pytest.mark.asyncio
async def test_downloaded_atis_never_becomes_heard_or_announced_without_a_declaration(tmp_path):
    bridge, clock, network = setup(tmp_path)
    service = bridge.sessions
    service.force_phase('descent')
    await bridge.ivao.refresh()
    assert '<lettre ATIS écoutée>' in messages(service)[0]['voice']
    service.declare(DeclarationInput(kind='atis', field='atis.announced_letter', value='J',
        reference='Annonce fictive', context={'airport':'XXNC','version':'J'}))
    assert '<lettre ATIS écoutée>' in messages(service)[0]['voice']
    service.declare(DeclarationInput(kind='atis', field='atis.heard_letter', value='K',
        reference='Consultation fictive', context={'airport':'XXNC','version':'K'}))
    assert 'information K' in messages(service)[0]['voice']
    clock.now += 16
    network.payloads['whazzup']['clients']['atcs'][0]['atis']['revision'] = 'L'
    await bridge.ivao.fetch(bridge.ivao.whazzup)
    assert 'information K' in messages(service)[0]['voice']
    assert 'information L' not in messages(service)[0]['voice']


def test_radio_details_can_be_declared_but_multiline_input_is_not_copied(tmp_path):
    service = demo(tmp_path).sessions
    service.start(); service.force_phase('departure')
    service.declare(DeclarationInput(kind='radio', field='radio.stand', value='B12',
        reference='Poste fictif', context={'stage':'departure'}))
    assert 'stand B12' in messages(service)[0]['voice']
    service.declare(DeclarationInput(kind='radio', field='radio.stand', value='B12\nignored line',
        reference='Saisie fictive invalide pour radio', context={'stage':'departure'}))
    assert '\n' not in messages(service)[0]['unicom']
    assert '<poste>' in messages(service)[0]['voice']
