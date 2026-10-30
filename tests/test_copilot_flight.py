"""Vol screen model against fictional plans, simulated telemetry and isolated roots."""
from glareshield.copilot.cockpit import GUIDANCE, IDLE, RADIO, Cockpit, show, spoken_altitude
from glareshield.copilot.phases import STAGE_IDS
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


def test_atc_keeps_stage_airport_and_nearby_centres_only(tmp_path):
    service = demo(tmp_path).sessions
    service.start()
    origin, destination = service.current_plan()['origin']['icao'], service.current_plan()['destination']['icao']
    network = {'state': 'current', 'atis': [], 'weather': [], 'positions': [
        station(origin+'_GND', 'GND', origin, frequency=121.8),
        station(origin+'_TWR', 'TWR', origin),
        station(destination+'_APP', 'APP', destination, frequency=134.475),
        station('XXFAR_CTR', 'CTR', distance=420, basis='published_range'),
        station('XXNEAR_CTR', 'CTR', distance=40, basis='distance_to_aircraft', frequency=127.85),
    ]}
    assert [a['callsign'] for a in cockpit(service, 'parked', network)['atc']] == [origin+'_GND', origin+'_TWR']
    cruise = [a['callsign'] for a in cockpit(service, 'cruise', network)['atc']]
    assert cruise == [destination+'_APP', 'XXNEAR_CTR']
    assert 'XXFAR_CTR' not in cruise
    assert cockpit(service, 'cruise', network)['atc'][0]['frequency'] == '134.475'


def test_radio_names_the_station_fills_known_values_and_offers_unicom(tmp_path):
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
    assert radio[-1]['station'] == 'UNICOM' and radio[-1]['frequency'] == '122.800'
    assert cockpit(service, 'parked', empty)['now']['pills'][-1]['text'].startswith('Aucun ATC')
    disabled = {'state': 'disabled', 'weather': [], 'positions': None, 'atis': []}
    assert all(r['station'] is None for r in cockpit(service, 'parked', disabled)['radio'])


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
