"""Vol screen model against fictional plans, simulated telemetry and isolated roots."""
import pytest
from glareshield.copilot.cockpit import GUIDANCE, IDLE, RADIO, Cockpit, show, spoken_altitude
from glareshield.copilot.phases import STAGE_IDS
from glareshield.copilot.radio import PHRASE_GROUPS, radio_language
from test_copilot_session import demo, declaration


def cockpit(service, stage, network=None, plan=None, **phase):
    """Cockpit for an arbitrary stage, reusing the demo session's resolved values."""
    view = service.view()
    session = service.documents[service.universe].sessions[-1]
    flight = {**view['flight'], 'plan': plan if plan is not None else service.current_plan()}
    from glareshield.copilot.phases import STAGE_PHASE
    phase_view = {'stage': stage, 'phase': STAGE_PHASE[stage], 'mode': 'automatic', 'live': True,
                  'next': {'label': 'Fictif'}, 'distance_to_destination_nm': 120, **phase}
    return Cockpit(service.profile, session, phase_view, flight,
                   network if network is not None else view['network'], service.clock()).build()


def station(callsign, role, airport=None, distance=None, basis=None, frequency=118.7):
    matched = []
    if airport:
        matched.append({'basis': 'callsign_prefix', 'airport': airport})
    if basis:
        matched.append({'basis': basis, 'distance_nm': distance})
    return {'callsign': callsign, 'position': role, 'frequency_mhz': frequency, 'matched_by': matched,
            'distance_to_aircraft_nm': distance}


def test_guidance_references_known_profile_items_and_every_stage_has_content(tmp_path):
    service = demo(tmp_path).sessions
    known = {g.id for p in service.profile.phases for g in p.groups} | {
        s.id for p in service.profile.phases for g in p.groups for s in g.steps}
    radios = {r.id for p in service.profile.phases for r in p.radio}
    assert set(GUIDANCE) == set(IDLE) == set(RADIO) == set(STAGE_IDS)
    assert {ref for items in GUIDANCE.values() for ref, _ in items} <= known
    assert {r for ids in RADIO.values() for r in ids} <= radios


def test_now_follows_the_stage_and_moves_on_when_steps_are_checked(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    now = cockpit(service, 'parked')['now']
    assert now['title'] == 'Préparer le MCDU avec l’OFP' and now['ref'] == 'preflight_mcdu'
    for step in [s.id for g in service.profile.phases[0].groups if g.id == 'preflight_mcdu' for s in g.steps]:
        service.set_step(step, True)
    assert cockpit(service, 'parked')['now']['ref'] == 'preflight_fcu'
    assert cockpit(service, 'cruise')['now']['title'] == 'Préparer l’arrivée avant le TOD'
    assert cockpit(service, 'rollout')['now']['title'] == IDLE['rollout']
    assert cockpit(service, 'climb', mode='manual')['now']['why'].endswith('phase corrigée à la main')


def test_items_show_values_with_short_sources_and_unknowns_are_open(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    groups = {g['id']: g for g in cockpit(service, 'parked')['groups']}
    init = {s['id']: s for s in groups['preflight_mcdu']['steps']}
    cruise = init['init_cruise']['values'][0]
    assert cruise['text'].startswith('FL') and cruise['source'] == 'OFP' and not cruise['open']
    v1 = init['perf_takeoff']['values'][0]
    assert v1['open'] and v1['text'] == '<V1>' and v1['source'] is None
    checklist = {g['id']: g for g in cockpit(service, 'parked')['groups']}['preflight_checks']['steps'][0]
    assert checklist['values'] == []  # Procedure literals such as "EFFECTUÉE" are noise on screen.
    service.set_value('v1', '142')
    v1 = {s['id']: s for g in cockpit(service, 'parked')['groups'] for s in g['steps']}['perf_takeoff']['values'][0]
    assert (v1['text'], v1['source'], v1['open']) == ('142 kt', 'Pilote', False)


def test_track_marks_done_current_and_live_altitude(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    track = cockpit(service, 'descent')['track']
    assert [t['state'] for t in track] == ['done', 'done', 'done', 'done', 'current', 'todo']
    assert track[0]['progress'] == 100 and 0 < track[4]['progress'] < 100


def test_atc_lists_route_stations_and_centres_with_route_stations_ticked_by_default(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    origin, destination = service.current_plan()['origin']['icao'], service.current_plan()['destination']['icao']
    network = {'state': 'current', 'atis': [], 'weather': [], 'positions': [
        station(origin+'_GND', 'GND', origin, frequency=121.8),
        station(origin+'_TWR', 'TWR', origin),
        station(destination+'_APP', 'APP', destination, frequency=134.475),
        station('XXFAR_CTR', 'CTR'),
        station('XXNEAR_CTR', 'CTR', distance=40, basis='distance_to_aircraft', frequency=127.85),
        station('XXRNG_CTR', 'CTR', distance=200, basis='published_range', frequency=125.5),
    ]}
    rows = {a['callsign']: a for a in cockpit(service, 'parked', network)['atc']}
    assert list(rows) == [origin+'_GND', origin+'_TWR', destination+'_APP', 'XXNEAR_CTR', 'XXRNG_CTR']
    assert [rows[c]['selected'] for c in rows] == [True, True, True, False, False]
    assert rows[destination+'_APP']['frequency'] == '134.475' and rows[origin+'_GND']['airport'] == origin
    assert 'XXFAR_CTR' not in rows


def test_ticking_a_centre_or_unticking_a_station_changes_the_messages(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    origin = service.current_plan()['origin']['icao']
    network = {'state': 'current', 'atis': [], 'weather': [], 'positions': [
        station(origin+'_GND', 'GND', origin, frequency=121.8),
        station('XXNEAR_CTR', 'CTR', distance=40, basis='distance_to_aircraft', frequency=127.85)]}
    assert cockpit(service, 'cruise', network)['radio'][0]['station'] == 'UNICOM'
    service.set_atc('XXNEAR_CTR', True)
    view = cockpit(service, 'cruise', network)
    assert view['radio'][0]['station'] == 'XXNEAR_CTR' and view['radio'][0]['frequency'] == '127.850'
    assert [a['selected'] for a in view['atc']] == [True, True] and [a['auto'] for a in view['atc']] == [True, False]
    service.set_atc('XXNEAR_CTR', None)
    service.set_atc(origin+'_GND', False)
    radio = cockpit(service, 'parked', network)['radio']
    assert all(r['station'] == 'UNICOM' for r in radio)
    assert cockpit(service, 'parked', network)['now']['pills'][-1]['text'].startswith('Aucun ATC coché')
    service.set_atc(origin+'_GND', None)
    assert cockpit(service, 'parked', network)['radio'][0]['station'] == origin+'_GND'
    with pytest.raises(ValueError):
        service.set_atc('bad callsign', True)


def test_radio_names_the_station_fills_known_values_and_falls_back_to_english_unicom(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    plan = service.current_plan()
    origin = plan['origin']['icao']
    network = {'state': 'current', 'weather': [], 'positions': [station(origin+'_GND', 'GND', origin, frequency=121.8)],
               'atis': [{'station': origin+'_GND', 'airport': origin, 'revision': 'K', 'lines': ['Fictif']}]}
    service.set_value('stand', 'B12')
    radio = cockpit(service, 'parked', network)['radio']
    assert [r['id'] for r in radio] == ['radio_clearance', 'radio_pushback']
    assert radio[0]['station'] == origin+'_GND' and radio[0]['frequency'] == '121.800'
    assert 'Ground' in radio[0]['text'] or 'Sol' in radio[0]['text']
    assert 'B12' in radio[0]['text'] and 'Kilo' in radio[0]['text'] and '<station>' not in radio[0]['text']
    empty = {'state': 'current', 'weather': [], 'positions': [], 'atis': []}
    radio = cockpit(service, 'parked', empty)['radio']
    assert [r['id'] for r in radio] == ['radio_clearance_unicom', 'radio_pushback_unicom']
    assert all(r['station'] == 'UNICOM' and r['frequency'] == '122.800' and r['language'] == 'en' for r in radio)
    callsign = service.view()['flight']['values']['callsign']['value']
    assert callsign and all(callsign not in r['text'] for r in radio)  # Already shown on IVAO.
    assert radio[1]['text'].endswith(f'pushing back stand B12') and f'{origin} traffic' in radio[1]['text']
    assert cockpit(service, 'parked', empty)['now']['pills'][-1]['text'].startswith('Aucun ATC')
    # Without network data the ATC message stays (the pilot may have a controller) and UNICOM follows it.
    disabled = {'state': 'disabled', 'weather': [], 'positions': None, 'atis': []}
    radio = cockpit(service, 'parked', disabled)['radio']
    assert [r['station'] for r in radio] == [None, 'UNICOM', None, 'UNICOM']


def test_gate_is_typed_per_aerodrome_and_reaches_messages_and_the_ai_export(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    origin, destination = service.current_plan()['origin']['icao'], service.current_plan()['destination']['icao']
    empty = {'state': 'current', 'weather': [], 'positions': [], 'atis': []}
    stand = cockpit(service, 'parked', empty)['stand']
    assert stand['key'] == 'stand' and stand['open'] and stand['label'] == 'porte de départ'
    service.set_value('stand', 'A1')
    service.set_value('arrival_stand', 'C42')
    assert cockpit(service, 'parked', empty)['stand']['text'] == 'A1'
    arrival = cockpit(service, 'parked_in', empty)
    assert arrival['stand'] == {**arrival['stand'], 'key': 'arrival_stand', 'text': 'C42', 'source': 'Pilote'}
    assert 'stand C42' in arrival['radio'][-1]['text'] and 'A1' not in arrival['radio'][-1]['text']
    context = service.pilot_context()
    assert context['departure_stand'] == 'A1' and context['arrival_stand'] == 'C42'


def test_climb_message_reads_current_and_declared_altitude(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    service.set_value('cleared_altitude', 'FL120')
    text = cockpit(service, 'climb')['radio'][0]['text']
    assert '<altitude' not in text and ('120' in text)
    assert spoken_altitude('5000', True) == '5 000 pieds'
    assert spoken_altitude('FL120', False) == 'flight level 120'
    assert spoken_altitude('à confirmer', True) == 'à confirmer'


def test_atis_panel_prefers_the_stage_airport_and_reports_a_new_letter(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    destination = service.current_plan()['destination']['icao']
    network = {'state': 'current', 'weather': [], 'positions': [], 'atis': [
        {'station': destination+'_TWR', 'airport': destination, 'revision': 'L', 'lines': ['Fictif L', ''],
         'change': {'kind': 'revision', 'previous_revision': 'K', 'detected_utc': '2099-01-01T00:00:00Z'}}]}
    atis = cockpit(service, 'descent', network)['atis']
    assert (atis['airport'], atis['letter'], atis['lines'], atis['changed']) == (destination, 'L', ['Fictif L'], 'Lettre K → L')
    assert cockpit(service, 'climb', network)['atis'] is None
    fallback = cockpit(service, 'parked', {'state': 'disabled', 'weather': [], 'positions': None, 'atis': []})['atis']
    assert fallback is None or fallback['source'].startswith('METAR')


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
    service.revoke(service.view()['session']['declarations'][-1]['id'])
    assert values()[clearance]['value'] is None
    for value in values().values():
        assert value['source']
        if value['status'] == 'unavailable':
            assert value['value'] is None
            assert value['placeholder'].startswith('<')


def test_paused_or_disconnected_simulator_is_shown_and_derivations_stop(tmp_path):
    bridge = demo(tmp_path)
    service = bridge.sessions
    service.start()
    store = bridge.store()
    bridge.store = lambda: store
    store.paused = True
    view = service.view()
    assert view['cockpit']['header']['status'] == 'demo'
    assert view['flight']['paused'] and view['flight']['derived'] == {}
    assert view['phase']['live'] is False
    store.connected = False
    assert service.view()['flight']['connected'] is False


def test_display_formats_levels_masses_and_codes():
    assert show('cruise_altitude', {'value': 35000, 'unit': 'ft'}) == 'FL350'
    assert show('cleared_altitude', {'value': 5000, 'unit': 'ft'}) == '5 000 ft'
    assert show('block_fuel', {'value': 8420, 'unit': 'kg'}) == '8 420 kg'
    assert show('qnh', {'value': 1017, 'unit': 'hPa'}) == '1 017'
    assert show('temperature', {'value': 14, 'unit': '°C'}) == '14°C'
    assert show('squawk', {'value': '0421', 'unit': None}) == '0421'
    assert show('v1', {'value': None, 'unit': 'kt', 'status': 'unavailable'}) is None


def test_unicom_departure_messages_give_the_sid(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    service.set_value('cleared_sid', 'MOKA2A')
    empty = {'state': 'current', 'weather': [], 'positions': [], 'atis': []}
    takeoff = {r['id']: r['text'] for r in cockpit(service, 'taxi_out', empty)['radio']}['radio_takeoff_unicom']
    assert takeoff.endswith(', MOKA2A departure') and 'departing runway' in takeoff
    climb = cockpit(service, 'climb', empty)['radio'][0]
    assert climb['station'] == 'UNICOM' and 'airborne runway' in climb['text'] and 'MOKA2A' in climb['text']


def test_descent_without_a_ticked_centre_is_announced_on_unicom(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    destination = service.current_plan()['destination']['icao']
    network = {'state': 'current', 'atis': [], 'weather': [], 'positions': [
        station(destination+'_TWR', 'TWR', destination), station('XXNEAR_CTR', 'CTR', distance=40, basis='distance_to_aircraft')]}
    radio = cockpit(service, 'cruise', network)['radio']
    assert [r['id'] for r in radio] == ['radio_descent_request_unicom'] and '<station>' not in radio[0]['text']
    assert radio[0]['text'].startswith(f'{destination} traffic, descending') and radio[0]['station'] == 'UNICOM'
    service.set_value('cleared_altitude', 'FL120')
    assert 'descending to flight level 120, inbound' in cockpit(service, 'cruise', network)['radio'][0]['text']
    service.set_atc('XXNEAR_CTR', True)
    assert cockpit(service, 'cruise', network)['radio'][0]['station'] == 'XXNEAR_CTR'


@pytest.mark.parametrize(('callsign', 'airport', 'language'), [
    ('LFXX_TWR', 'LFXX', 'fr'), ('LFXX_N_CTR', 'EGXX', 'fr'),
    ('LSGG_APP', 'LSGG', 'fr'), ('LSGG_A_GND', 'LSGG', 'fr'),
    ('LSGS_TWR', 'LSGS', 'en'), ('LSZH_APP', 'LSZH', 'en'), ('LSAG_CTR', 'LSGG', 'en'),
    ('GMMX_APP', 'GMMX', 'en'), ('DAAG_TWR', 'DAAG', 'en'), ('DTTA_TWR', 'DTTA', 'en'),
    ('EDXX_CTR', 'LFXX', 'en'), (None, 'LSGG', 'fr'), (None, 'DTTA', 'en'), (None, None, 'en'),
])
def test_language_uses_the_contacted_controller_and_conservative_regional_defaults(callsign, airport, language):
    assert radio_language(callsign, airport) == language
    assert radio_language(callsign, airport, 'en') == 'en'
    assert radio_language(callsign, airport, 'fr') == 'fr'


@pytest.mark.parametrize('stage', STAGE_IDS)
def test_every_stage_and_every_phrase_uses_english_with_a_foreign_centre(tmp_path, stage):
    service = demo(tmp_path).sessions
    service.start()
    plan = service.current_plan()
    # Fictional plan: a foreign centre can provide top-down control at a French airport.
    from copy import deepcopy
    plan = deepcopy(plan)
    plan['origin'].update(icao='LFXX', name='Testfield')
    plan['destination'].update(icao='LFYY', name='Testport')
    network = {'state': 'current', 'weather': [], 'atis': [], 'positions': [
        station('EGXX_CTR', 'CTR', 'LFXX', frequency=128.5)]}
    view = cockpit(service, stage, network, plan)
    voice = [r for r in view['radio'] if r['station'] != 'UNICOM']
    assert voice and all(r['language'] == 'en' for r in voice)
    assert all(p['language'] == 'en' for p in view['phrasebook'])
    # Missing values in English transmissions must not turn into French placeholders.
    import re
    placeholders = re.findall(r'<[^>]+>', ' '.join(r['text'] + r['readback'] for r in voice) +
                              ' '.join(p['text'] for p in view['phrasebook']))
    assert not any(re.search(r'[éèàêç]|\bpiste\b|\bposte\b|\bautorisé', p) for p in placeholders)


def test_phrasebook_keeps_all_exchanges_accessible_and_limits_current_suggestions(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    view = cockpit(service, 'parked')
    book = {p['id']: p for p in view['phrasebook']}
    assert len(book) == sum(len(phrases) for _, _, _, phrases in PHRASE_GROUPS)
    assert len(book) >= 100
    # Acceptance matrix spans the complete flight, not only the initial calls.
    assert {
        'clearance_readback', 'startup_request', 'pushback_request', 'taxi_readback', 'hold_short',
        'cross_readback', 'lineup', 'conditional_lineup', 'takeoff_readback', 'departure_contact',
        'enroute_contact', 'position_report', 'contact_frequency', 'monitor_frequency', 'no_contact',
        'climb_readback', 'descent_readback', 'heading_readback', 'speed_readback', 'qnh_readback',
        'squawk_readback', 'direct_readback', 'restriction', 'weather_deviation', 'holding_readback',
        'approach_clearance', 'ils_established', 'continue_approach', 'landing_readback',
        'go_around_report', 'missed_approach', 'vacated', 'taxi_stand', 'parking',
        'say_again', 'speak_slower', 'unable', 'request_text', 'pan', 'mayday', 'minimum_fuel',
        'fuel_emergency', 'tcas', 'clear_conflict', 'emergency_descent', 'diversion', 'radio_failure',
    } <= book.keys()
    assert book['say_again']['current'] and book['mayday']['current'] and book['lineup']['current']
    assert not book['landing_readback']['current']  # Still present under "Tout le vol".
    arrival = {p['id']: p for p in cockpit(service, 'final')['phrasebook']}
    assert arrival['landing_readback']['current'] and not arrival['lineup']['current']
    assert len({p[0] for _, _, _, phrases in PHRASE_GROUPS for p in phrases}) == len(book)


def test_readback_never_takes_a_planned_runway_and_landing_never_reuses_departure_clearance(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    service.set_radio_language('en')
    origin, destination = service.current_plan()['origin']['icao'], service.current_plan()['destination']['icao']
    network = {'state': 'current', 'weather': [], 'atis': [], 'positions': [
        station(origin+'_GND', 'GND', origin), station(destination+'_TWR', 'TWR', destination)]}
    initial = cockpit(service, 'parked', network)['radio'][0]
    assert '<cleared runway>' in initial['readback']
    assert '<cleared SID>' in initial['readback'] and '<cleared level>' in initial['readback']
    service.set_value('cleared_runway', '09R')
    service.set_value('squawk', '0421')
    service.set_value('cleared_altitude', 'FL120')
    initial = cockpit(service, 'parked', network)['radio'][0]
    assert '09R' in initial['readback'] and '0421' in initial['readback'] and 'flight level 120' in initial['readback']
    landing = cockpit(service, 'final', network)['radio'][0]
    assert '09R' not in landing['readback'] and '<received landing runway>' in landing['readback']
    unicom = cockpit(service, 'parked', {**network, 'positions': []})['radio']
    assert all('readback' not in r and r['language'] == 'en' for r in unicom)


def test_voice_override_reaches_all_voice_models_and_never_changes_unicom(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    origin = service.current_plan()['origin']['icao']
    network = {'state': 'current', 'weather': [], 'atis': [], 'positions': [station('LFXX_CTR', 'CTR', origin)]}
    for language in ('fr', 'en'):
        service.set_radio_language(language)
        view = cockpit(service, 'parked', network)
        assert view['radio_language'] == language
        assert all(r['language'] == language for r in view['radio'] + view['phrasebook'])
        assert all(r['language'] == 'en' for r in cockpit(service, 'parked', {**network, 'positions': []})['radio'])
