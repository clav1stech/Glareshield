"""Vol screen model: what to do now at the detected stage. Presentation only, no cockpit writes."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from string import Formatter

from ..aibridge.context import distance_nm
from .contract import PHASE_IDS
from .phases import STAGE_IDS, STAGE_LABEL, STAGE_PHASE
from .radio import EN_PLACEHOLDERS, PHRASE_GROUPS, PHRASE_NOTES, radio_language

# Ordered work per stage: profile group or step, and the sentence shown in "Maintenant".
# The first one with an unchecked step wins; IDLE applies once everything is done.
GUIDANCE = {
    'parked': [('preflight_mcdu', 'Préparer le MCDU avec l’OFP'), ('preflight_fcu', 'Régler le FCU'),
               ('before_start_check', 'Check-list avant mise en route')],
    'pushback': [('before_start_check', 'Check-list avant mise en route'),
                 ('after_start_check', 'Check-list après mise en route')],
    'taxi_out': [('after_start_check', 'Check-list après mise en route'),
                 ('departure_mcdu', 'Comparer la clairance au F-PLN'),
                 ('departure_fcu', 'Altitude autorisée et squawk'),
                 ('before_taxi_check', 'Check-list avant roulage'),
                 ('before_takeoff_check', 'Check-list avant décollage')],
    'takeoff': [],
    'climb': [('gear_up', 'Train rentré'), ('after_takeoff_check', 'Check-list après décollage'),
              ('climb_std', 'Passage en STD à l’altitude de transition'), ('climb_clearance', 'Niveau autorisé au FCU')],
    'cruise': [('cruise_mcdu', 'Préparer l’arrivée avant le TOD'),
               ('cruise_fcu', 'Altitude de descente autorisée au FCU')],
    'descent': [('cruise_mcdu', 'Terminer la préparation de l’arrivée'),
                ('descent_mcdu', 'Mettre l’arrivée à jour avec l’ATIS'),
                ('descent_fcu', 'QNH au niveau de transition, 250 kt sous FL100'),
                ('approach_check', 'Check-list approche')],
    'approach': [('approach_check', 'Check-list approche'), ('arrival_fcu', 'APPR armé, second AP, train sorti')],
    'final': [('gear_down', 'Train sorti'), ('landing_check', 'Check-list atterrissage')],
    'go_around': [],
    'rollout': [],
    'taxi_in': [('after_landing_check', 'Check-list après atterrissage')],
    'parked_in': [('parking_check', 'Check-list parking'), ('securing_check', 'Check-list sécurisation')],
}
IDLE = {
    'parked': 'Demander la clairance, puis la mise en route',
    'pushback': 'Demander le roulage',
    'taxi_out': 'Alignement et décollage sur autorisation',
    'takeoff': 'Décollage : vario positif, train rentré',
    'climb': 'Montée vers le niveau de croisière',
    'cruise': 'Croisière : surveiller carburant et TOD',
    'descent': 'Descente vers l’approche',
    'approach': 'Interception et configuration d’approche',
    'final': 'Stabilisé à 1 000 ft, sinon remise des gaz',
    'go_around': 'Remise des gaz : suivre la procédure publiée',
    'rollout': 'Dégager la piste',
    'taxi_in': 'Rouler jusqu’au poste',
    'parked_in': 'Vol terminé',
}
RADIO = {
    'parked': ['radio_clearance', 'radio_pushback'], 'pushback': ['radio_taxi'], 'taxi_out': ['radio_takeoff'],
    'takeoff': ['radio_departure_contact'], 'climb': ['radio_departure_contact'],
    'cruise': ['radio_descent_request'], 'descent': ['radio_approach_contact'], 'approach': ['radio_landing'],
    'final': ['radio_landing', 'radio_go_around'], 'go_around': ['radio_go_around'], 'rollout': ['radio_vacated'],
    'taxi_in': ['radio_vacated', 'radio_parked'], 'parked_in': ['radio_parked'],
}
ROLE_NAMES = {'DEL': ('Prévol', 'Delivery'), 'GND': ('Sol', 'Ground'), 'TWR': ('Tour', 'Tower'),
              'DEP': ('Départ', 'Departure'), 'APP': ('Approche', 'Approach'), 'CTR': ('Contrôle', 'Control'),
              'FSS': ('Information', 'Radio')}
ROLE_ORDER = ('DEL', 'GND', 'TWR', 'DEP', 'APP', 'CTR', 'FSS')
ATIS_ORDER = ('TWR', 'APP', 'DEP', 'GND', 'DEL')
SOURCE_LABELS = {'planned': 'OFP', 'declared': 'Pilote', 'published': 'METAR', 'observed': 'Sim'}
ALPHABET = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', (
    'Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliett Kilo Lima Mike November Oscar Papa '
    'Quebec Romeo Sierra Tango Uniform Victor Whiskey X-ray Yankee Zulu').split()))
FLIGHT_LEVEL_KEYS = {'cruise_altitude'}
ATIS_FRESH_S = 900


def grouped(value):
    return f'{value:,.0f}'.replace(',', ' ')


def show(key, item):
    """Short display of a resolved profile value, or None when unknown."""
    value, unit = item.get('value'), item.get('unit')
    if value is None or item.get('status') == 'unavailable':
        return None
    if isinstance(value, bool):
        return 'Oui' if value else 'Non'
    if type(value) in (int, float):
        if key in FLIGHT_LEVEL_KEYS and unit == 'ft' and value >= 10000:
            return f'FL{round(value/100):03d}'
        text = grouped(value) if abs(value) >= 1000 else f'{value:g}'
        if not unit or unit == 'hPa':
            return text
        return text+unit if unit.startswith('°') else text+' '+unit
    return str(value)


def city(airport):
    name = (airport or {}).get('name')
    if not isinstance(name, str) or not name.strip():
        return (airport or {}).get('icao')
    return ' '.join(word.capitalize() for word in name.split('/')[0].split())


def altitude_text(feet, french):
    if feet is None:
        return None
    if feet >= 10000:
        return ('niveau ' if french else 'flight level ')+str(round(feet/100))
    return grouped(round(feet/100)*100)+(' pieds' if french else ' feet')


def spoken_altitude(value, french):
    """Pilot entries are free text: 5000, FL120 or 'niveau 120' stay readable."""
    if type(value) in (int, float) and not isinstance(value, bool):
        return altitude_text(value, french)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().upper().replace(' ', '')
    if text.startswith('FL') and text[2:].isdigit():
        return altitude_text(int(text[2:])*100, french)
    if text.isdigit():
        return altitude_text(int(text), french)
    return value.strip()


def utc_text(stamp):
    try:
        moment = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).strftime('%H:%MZ')


class Cockpit:
    """Builds the Vol payload from already qualified inputs."""

    def __init__(self, profile, session, phase, flight, network, now):
        self.profile, self.session, self.phase, self.flight, self.network, self.now = (
            profile, session, phase or {}, flight, network, now)
        self.plan = flight.get('plan') or {}
        self.stage = self.phase.get('stage')
        self.current = self.phase.get('phase')
        self.steps = {s.id: (phase_def.id, group.id, s) for phase_def in profile.phases
                      for group in phase_def.groups for s in group.steps}
        self.groups = {group.id: [s.id for s in group.steps] for p in profile.phases for group in p.groups}
        self.telemetry = flight.get('telemetry') or {}

    # Inputs

    def checked(self, step_id):
        return self.flight['checked'].get(step_id, False)

    def reading(self, key):
        field = self.telemetry.get(key) or {}
        value = field.get('value')
        if field.get('status') not in ('observed', 'simulated') or type(value) not in (int, float) or isinstance(value, bool):
            return None
        return value

    def altitude(self):
        value = self.reading('altitude_indicated')
        return value if value is not None else self.reading('altitude_msl')

    def value(self, key):
        item = self.flight['values'].get(key)
        return show(key, item) if item else None

    def airport(self, phase=None):
        phase = phase or self.current
        return self.plan.get(self.airport_role(phase)) or {}

    def positions(self):
        if self.network.get('state') not in ('current', 'stale', 'empty'):
            return []
        return self.network.get('positions') or []

    def atis_for(self, icao):
        candidates = [a for a in self.network.get('atis') or []
                      if icao and (a.get('airport') == icao or icao in a.get('covers', []))]
        def role(atis):
            suffix = atis['station'].rsplit('_', 1)[-1]
            return ATIS_ORDER.index(suffix) if suffix in ATIS_ORDER else len(ATIS_ORDER)
        candidates.sort(key=lambda a: (not a.get('revision'), a.get('airport') != icao, role(a)))
        return candidates[0] if candidates else None

    # Sections

    def header(self):
        flight, plan = self.flight, self.plan
        origin, destination = plan.get('origin') or {}, plan.get('destination') or {}
        aircraft = plan.get('aircraft') or {}
        live = ('demo' if self.session.universe == 'demo' else 'paused' if flight['paused'] else
                'disconnected' if not flight['connected'] else 'stale' if flight['stale'] else 'live')
        return {'callsign': self.value('callsign') or (plan.get('flight') or {}).get('number'),
                'origin': origin.get('icao'), 'origin_name': city(origin),
                'destination': destination.get('icao'), 'destination_name': city(destination),
                'aircraft': aircraft.get('name') or aircraft.get('icao'),
                'eta': utc_text((plan.get('times') or {}).get('scheduled_in_utc')) if plan else None,
                'ofp_age_min': flight.get('plan_age_min'), 'airac': plan.get('airac'), 'utc': self.now,
                'status': live}

    def track(self):
        cruise = self.value('cruise_altitude')
        subs = {'preflight': 'au poste', 'departure': 'roulage · décollage',
                'climb': 'vers '+cruise if cruise else 'montée', 'cruise': cruise or 'palier',
                'descent': (cruise+' → approche') if cruise else 'vers l’approche', 'arrival': 'approche · parking'}
        index = PHASE_IDS.index(self.current) if self.current in PHASE_IDS else -1
        result = []
        for position, phase in enumerate(PHASE_IDS):
            stages = [s for s in STAGE_IDS if STAGE_PHASE[s] == phase and s != 'go_around']
            steps = [s for g in self.profile.phases[position].groups for s in g.steps]
            item = {'id': phase, 'label': self.profile.phases[position].label, 'sub': subs[phase],
                    'state': 'done' if position < index else 'current' if position == index else 'todo',
                    'done': sum(self.checked(s.id) for s in steps), 'total': len(steps), 'progress': 0}
            if position < index:
                item['progress'] = 100
            elif position == index and self.stage in stages:
                item['progress'] = round(100*(stages.index(self.stage)+1)/(len(stages)+1))
                item['sub'] = self.live_sub()
            elif position == index:
                item['sub'] = STAGE_LABEL.get(self.stage, '')
                item['progress'] = 50
            result.append(item)
        return result

    def live_sub(self):
        label, altitude, vs = STAGE_LABEL[self.stage], self.altitude(), self.reading('vertical_speed')
        if self.stage in ('climb', 'cruise', 'descent') and altitude is not None:
            arrow = ' ↑' if vs is not None and vs > 300 else ' ↓' if vs is not None and vs < -300 else ''
            text = f'FL{round(altitude/100):03d}' if altitude >= 10000 else grouped(round(altitude/100)*100)+' ft'
            return text+arrow
        return label

    def now_block(self):
        stage = self.stage
        if stage is None:
            return {'title': 'Phase en cours de détection',
                    'why': 'Le suivi se place automatiquement dès que le simulateur envoie des mesures récentes. '
                           'Cliquer une phase du parcours pour la corriger.',
                    'ref': None, 'pills': []}
        title, ref = IDLE[stage], None
        for target, sentence in GUIDANCE[stage]:
            ids = self.groups.get(target, [target])
            if any(not self.checked(i) for i in ids if i in self.steps):
                title, ref = sentence, target
                break
        return {'title': title, 'why': ' · '.join(self.facts()), 'ref': ref, 'pills': self.pills()}

    def facts(self):
        stage, phase, facts = self.stage, self.current, []
        if phase in ('preflight', 'departure'):
            age = self.flight.get('plan_age_min')
            if self.plan:
                facts.append('OFP importé il y a '+(f'{age} min' if age is not None else '<…>'))
            runway, sid = self.value('departure_runway'), self.value('sid')
            if runway or sid:
                facts.append('départ '+' · '.join(x for x in (runway, sid) if x))
        if phase in ('climb',):
            for key, label in (('cleared_altitude', 'autorisé '), ('cruise_altitude', 'croisière prévue ')):
                if self.value(key):
                    facts.append(label+self.value(key))
        if phase in ('cruise', 'descent', 'arrival'):
            runway, approach = self.value('arrival_runway'), self.value('approach')
            if runway or approach:
                facts.append('arrivée '+' · '.join(x for x in (runway, approach) if x))
            if phase == 'arrival' and self.value('minima'):
                facts.append('minima '+self.value('minima'))
        atis = self.atis_for(self.airport().get('icao')) if phase != 'climb' else None
        if atis and atis.get('revision'):
            facts.append('ATIS '+atis.get('airport', '')+' '+atis['revision'])
        distance = self.phase.get('distance_to_destination_nm')
        if phase in ('cruise', 'descent') and distance is not None:
            facts.append(f'{distance} NM de '+(self.plan.get('destination') or {}).get('icao', 'la destination'))
        fuel = ((self.flight.get('derived') or {}).get('route_progress') or {}).get('fuel_vs_plan')
        if fuel and phase in ('climb', 'cruise', 'descent'):
            facts.append(f"carburant {fuel['difference_kg']:+,.0f} kg vs plan".replace(',', ' '))
        if self.phase.get('mode') == 'manual':
            facts.append('phase corrigée à la main')
        return facts

    def pills(self):
        pills = []
        upcoming = (self.phase.get('next') or {}).get('label')
        if upcoming:
            pills.append({'tone': 'acc', 'text': 'Ensuite : '+upcoming[0].lower()+upcoming[1:]})
        airport = self.airport().get('icao')
        atis = self.atis_for(airport)
        change = (atis or {}).get('change')
        if change and change.get('kind') in ('revision', 'text'):
            try:
                detected = datetime.fromisoformat(change['detected_utc'].replace('Z', '+00:00')).timestamp()
            except (KeyError, ValueError):
                detected = None
            if detected is not None and self.now-detected <= ATIS_FRESH_S:
                pills.append({'tone': 'ivao', 'text': 'ATIS '+airport+' : '+(
                    'nouvelle lettre '+atis['revision'] if change['kind'] == 'revision' and atis.get('revision')
                    else 'texte modifié')})
        chosen = [a['callsign'] for a in self.atc() if a['selected']]
        if chosen:
            pills.append({'tone': 'ok', 'text': ' · '.join(chosen[:3])+' coché'+('s' if len(chosen) > 1 else '')})
        elif self.network_known() and self.current in ('preflight', 'departure', 'arrival'):
            pills.append({'tone': 'warn', 'text': 'Aucun ATC coché sur '+(airport or 'l’aérodrome')+' : UNICOM 122.800'})
        return pills

    def items(self):
        """Every phase's groups; the screen shows one phase at a time."""
        result = []
        for phase in self.profile.phases:
            for group in phase.groups:
                rows = []
                for step in group.steps:
                    values = []
                    for key in step.expected:
                        expected = self.profile.values[key]
                        if expected.literal is not None:
                            continue
                        item = self.flight['values'][key]
                        text = show(key, item)
                        values.append({'key': key, 'label': expected.label, 'text': text or expected.placeholder,
                                       'open': text is None,
                                       'source': SOURCE_LABELS.get(item.get('nature')) if text else None})
                    progress = self.flight['progress'].get(step.id, {})
                    rows.append({'id': step.id, 'label': step.label, 'checked': self.checked(step.id),
                                 'detected': progress.get('provenance') == 'detected', 'values': values})
                result.append({'id': group.id, 'phase': phase.id, 'kind': group.kind, 'label': group.label,
                               'steps': rows})
        return result

    def network_known(self):
        return self.network.get('state') in ('current', 'stale', 'empty')

    def route_airports(self):
        return {a.get('icao') for a in (self.plan.get('origin'), self.plan.get('destination')) if a and a.get('icao')}

    def choice(self, callsign):
        return (getattr(self.session, 'atc_choices', None) or {}).get(callsign)

    def selected(self, position):
        """Pilot's tick, else the default: stations of the departure and arrival aerodromes (not centres)."""
        choice = self.choice(position['callsign'])
        if choice is not None:
            return choice
        airports = self.route_airports()
        matches = position.get('matched_by', [])
        if position.get('position') in ('CTR', 'FSS'):
            # En-route control belongs to no aerodrome; it takes over only where no GND/TWR/APP is online.
            return bool(matches) and not any(
                p.get('position') not in ('CTR', 'FSS', 'ATIS') and any(m.get('airport') in airports for m in p.get('matched_by', []))
                for p in self.positions())
        return any(m.get('airport') in airports for m in matches)

    def atc(self):
        """Online controllers the pilot can tick: departure and arrival stations, plus the centres around."""
        airports, stage_airport = self.route_airports(), self.airport().get('icao')
        local, centres = [], []
        for position in self.positions():
            role, callsign = position.get('position'), position['callsign']
            if role == 'ATIS':
                continue
            matched = [m['airport'] for m in position.get('matched_by', []) if m.get('airport') in airports]
            distance = position.get('distance_to_aircraft_nm') or 0
            if role in ('CTR', 'FSS'):
                near = any(m.get('basis') in ('distance_to_aircraft', 'published_range')
                           for m in position.get('matched_by', []))
                if near or matched or self.choice(callsign):
                    centres.append((distance, position, matched))
            elif matched or self.choice(callsign):
                rank = (0 if (matched or [None])[0] == stage_airport else 1,
                        ROLE_ORDER.index(role) if role in ROLE_ORDER else len(ROLE_ORDER), distance)
                local.append((rank, position, matched))
        local.sort(key=lambda item: item[0])
        centres.sort(key=lambda item: item[0])
        result = []
        for _, position, matched in local[:8] + centres[:4]:
            role, callsign = position.get('position'), position['callsign']
            atis = next((a for a in self.network.get('atis') or [] if a['station'] == callsign), None)
            note = ROLE_NAMES.get(role, (role or 'Position',))[0]
            # The station's own aerodrome is the ICAO code of its callsign, not the one a neighbouring approach covers.
            code = callsign.split('_', 1)[0]
            own = code if role not in ('CTR', 'FSS') and len(code) == 4 and code.isalpha() else None
            airport = own or (None if role in ('CTR', 'FSS') else matched[0] if matched else None)
            if airport:
                note += ' '+airport
            if atis and atis.get('revision'):
                note += ' · ATIS '+atis['revision']
            if position.get('distance_to_aircraft_nm') is not None and role in ('CTR', 'FSS'):
                note += f" · {position['distance_to_aircraft_nm']} NM"
            frequency = position.get('frequency_mhz')
            result.append({'callsign': callsign, 'role': role, 'airport': airport, 'note': note,
                           'frequency': f'{frequency:.3f}' if type(frequency) in (int, float) else None,
                           'selected': bool(self.selected(position)), 'auto': self.choice(callsign) is None})
        return result

    def atis(self):
        if self.current == 'climb':
            return None
        airport = self.airport()
        icao = airport.get('icao')
        if not icao:
            return None
        atis = self.atis_for(icao)
        if atis:
            change = atis.get('change') or {}
            changed = None
            if change.get('kind') == 'revision' and change.get('previous_revision'):
                changed = 'Lettre '+change['previous_revision']+' → '+(atis.get('revision') or '?')
            elif change.get('kind') == 'text':
                changed = 'Texte modifié, même lettre'
            return {'airport': icao, 'station': atis['station'], 'letter': atis.get('revision'),
                    'lines': [line for line in atis.get('lines', []) if line.strip()][:8],
                    'age_min': atis.get('source_age_min'), 'changed': changed, 'source': 'IVAO'}
        weather = next((w for w in self.network.get('weather') or [] if w['icao'] == icao), {})
        raw = (weather.get('metar') or {}).get('raw')
        if raw:
            return {'airport': icao, 'letter': None, 'lines': [raw], 'changed': None, 'source': 'METAR IVAO'}
        if airport.get('metar'):
            return {'airport': icao, 'letter': None, 'lines': [airport['metar']], 'changed': None,
                    'source': 'METAR de l’OFP'}
        return None

    def situation(self):
        fuel = self.reading('fuel_total')
        progress = (self.flight.get('derived') or {}).get('route_progress') or {}
        points = [p for p in self.plan.get('waypoints', []) if 'latitude' in p and 'longitude' in p]
        origin = self.plan.get('origin') or {}
        along, tod = [], None
        previous = (origin.get('latitude'), origin.get('longitude')) if 'latitude' in origin else None
        total = 0.0
        for point in points:
            if previous is not None:
                total += distance_nm(previous[0], previous[1], point['latitude'], point['longitude'])
            along.append(total)
            previous = (point['latitude'], point['longitude'])
            if point.get('ident') == 'TOD' and tod is None:
                tod = total
        planned = self.plan.get('distance_nm') or (round(total) if total else None)
        remaining = progress.get('remaining_along_route_nm')
        if remaining is None:
            remaining = self.phase.get('distance_to_destination_nm')
        if self.current in ('preflight', 'departure') and self.stage not in ('takeoff',):
            remaining = planned
        flown = None if planned is None or remaining is None else max(0, min(planned, planned-remaining))
        if self.stage in ('rollout', 'taxi_in', 'parked_in') and planned:
            flown = planned
        return {'altitude_ft': self.altitude(), 'ground_speed_kt': self.reading('ground_speed'),
                'vertical_speed_fpm': self.reading('vertical_speed'), 'fuel_kg': fuel,
                'fuel_vs_plan_kg': (progress.get('fuel_vs_plan') or {}).get('difference_kg'),
                'distance_total_nm': planned, 'distance_flown_nm': None if flown is None else round(flown),
                'tod_ratio': round(tod/total, 3) if tod is not None and total else None}

    def upcoming(self):
        result = []
        progress = (self.flight.get('derived') or {}).get('route_progress') or {}
        upcoming = progress.get('upcoming') or []
        if self.current in ('climb', 'cruise'):
            tod = next((p for p in upcoming if p.get('ident') == 'TOD'), None)
            if tod:
                result.append({'at': 'TOD', 'text': f"dans {tod['distance_nm']} NM : préparer la descente"})
            elif self.current == 'cruise':
                distance = self.phase.get('distance_to_destination_nm')
                if distance is not None:
                    result.append({'at': 'Arrivée', 'text': f'{distance} NM en direct'})
        altitude = self.altitude()
        if self.current == 'descent' and altitude is not None and altitude > 10000:
            result.append({'at': 'FL100', 'text': '250 kt maximum en dessous'})
        if self.current == 'climb' and altitude is not None and altitude < 10000:
            result.append({'at': 'FL100', 'text': 'Accélération au-dessus'})
        if self.stage in ('approach', 'final'):
            result.append({'at': '1 000 ft', 'text': 'Stabilisé ou remise des gaz'})
        if self.current in ('departure', 'climb', 'cruise', 'descent'):
            for point in upcoming:
                if point.get('ident') not in ('TOC', 'TOD'):
                    result.append({'at': point['ident'], 'text': f"prochain point · {point['distance_nm']} NM"})
                    break
        return result[:4]

    def radio(self):
        """At most four ready-to-read messages for this stage; copying never transmits.

        Without a ticked controller for a message, its English UNICOM version takes its place
        (or follows it when the network state is unknown)."""
        if self.stage is None:
            return []
        by_id = {r.id: r for p in self.profile.phases for r in p.radio}
        stage_airport = self.airport().get('icao')
        known, result = self.network_known(), []
        for radio_id in RADIO.get(self.stage, []):
            radio = by_id.get(radio_id)
            if radio is None:
                continue
            station = self.station_for(radio.station_roles, stage_airport)
            callsign = station['callsign'] if station else None
            language = self.language(station)
            french = language == 'fr'
            voice = radio.voice_fr if french else radio.voice_en
            text = self.fill(voice.pilot, station, french)
            frequency = station.get('frequency_mhz') if station else None
            message = {'id': radio.id, 'trigger': radio.trigger.label, 'station': callsign,
                       'frequency': f'{frequency:.3f}' if type(frequency) in (int, float) else None,
                       'language': language, 'text': text,
                       'readback': self.fill(voice.readback, station, french, readback=True)}
            unicom = None if station else self.unicom(radio_id)
            if unicom is not None:
                unicom = {'id': radio_id+'_unicom', 'trigger': 'Sans contrôle coché', 'station': 'UNICOM',
                          'frequency': '122.800', 'language': 'en', 'mode': 'texte', 'text': unicom}
            if unicom is None or not known:
                result.append(message)
            if unicom is not None:
                result.append(unicom)
        return result[:4]

    def language(self, station=None):
        return radio_language((station or {}).get('callsign'), self.airport().get('icao'),
                              getattr(self.session, 'radio_language', 'auto'))

    def phrasebook(self):
        """All voice variants stay reachable, including off-stage and emergency exchanges."""
        first = next((r for p in self.profile.phases for r in p.radio
                      if r.id in RADIO.get(self.stage, [])), None)
        default_roles = first.station_roles if first else ['CTR', 'APP', 'TWR', 'GND', 'DEL']
        result = []
        for category, stages, roles, phrases in PHRASE_GROUPS:
            station = self.station_for(roles or default_roles, self.airport().get('icao'))
            language = self.language(station)
            for identifier, label, english, french in phrases:
                result.append({'id': identifier, 'category': category, 'label': label,
                               'current': not stages or self.stage in stages,
                               'language': language, 'station': (station or {}).get('callsign'),
                               'text': self.fill(french if language == 'fr' else english,
                                                 station, language == 'fr', readback=True),
                               'note': PHRASE_NOTES.get(identifier)})
        return result

    def station_for(self, roles, airport):
        candidates = []
        for position in self.positions():
            role = position.get('position')
            if role not in roles or not self.selected(position):
                continue
            local = any(m.get('airport') == airport for m in position.get('matched_by', []))
            if local or role in ('CTR', 'FSS'):
                candidates.append((not local, roles.index(role), position.get('distance_to_aircraft_nm') or 0, position))
        candidates.sort(key=lambda c: c[:3])
        return candidates[0][3] if candidates else None

    def spoken_station(self, station, french):
        if station is None:
            return '<station>'
        prefix, _, role = station['callsign'].partition('_')
        role = station.get('position') or role.rsplit('_', 1)[-1]
        place = next((city(a) for a in (self.plan.get('origin'), self.plan.get('destination'))
                      if a and a.get('icao') == prefix), prefix)
        names = ROLE_NAMES.get(role)
        return place+(' '+names[0 if french else 1] if names else '')

    def fill(self, template, station, french, readback=False):
        values = self.flight['values']
        altitude = altitude_text(self.altitude(), french)

        def placeholder(key):
            return (self.profile.values[key].placeholder if french else
                    EN_PLACEHOLDERS.get(key, '<'+key.replace('_', ' ')+'>'))

        def parameter(key):
            if key == 'station':
                return self.spoken_station(station, french)
            if key == 'destination':
                return city(self.plan.get('destination')) or self.value('destination') or '<destination>'
            if key == 'atis_heard':
                text = self.value('atis_heard')
                if not text:
                    atis = self.atis_for(self.airport().get('icao'))
                    text = (atis or {}).get('revision')
                return ALPHABET.get(text, text) if text else '<ATIS>'
            if key == 'stand':
                return self.value(self.stand_key()) or placeholder(self.stand_key())
            if key == 'cleared_runway':
                return (self.value('cleared_runway') or
                        (None if readback else self.value('departure_runway')) or placeholder(key))
            if key == 'cleared_altitude':
                return spoken_altitude(values['cleared_altitude'].get('value'), french) or placeholder(key)
            text = self.value(key)
            if not french and text and key == 'speed':
                text = text.replace(' kt', ' knots')
            return text or placeholder(key)

        keys = [key for _, key, _, _ in Formatter().parse(template) if key is not None]
        text = template.format_map({key: parameter(key) for key in keys})
        if altitude:
            text = text.replace('<altitude actuelle>', altitude).replace('<current altitude>', altitude)
        return text

    def airport_role(self, phase=None):
        return 'origin' if (phase or self.current) in (None, 'preflight', 'departure', 'climb') else 'destination'

    def stand_key(self):
        return 'stand' if self.airport_role() == 'origin' else 'arrival_stand'

    def stand_item(self):
        """The gate the pilot types once per aerodrome; it feeds the messages and the AI export."""
        key = self.stand_key()
        item = self.flight['values'][key]
        text = show(key, item)
        return {'key': key, 'label': 'porte de départ' if key == 'stand' else 'porte d’arrivée',
                'text': text or 'Saisir la porte', 'open': text is None,
                'source': SOURCE_LABELS.get(item.get('nature')) if text else None}

    def unicom(self, radio_id):
        """English self-announce for 122.800, or None when the message has no UNICOM equivalent."""
        airport = self.airport().get('icao') or '<aérodrome>'
        departing = self.current in ('preflight', 'departure', 'climb')
        runway = self.value('departure_runway' if departing else 'arrival_runway') or '<piste>'
        stand = self.value(self.stand_key())
        sid = self.value('cleared_sid') or self.value('sid')
        via = f', {sid} departure' if sid else ''
        level = spoken_altitude(self.flight['values']['cleared_altitude'].get('value'), False)
        action = {'radio_clearance': 'IFR to '+(self.value('destination') or '<destination>')+', starting up'
                                     + (f', stand {stand}' if stand else ''),
                  'radio_pushback': 'pushing back'+(f' stand {stand}' if stand else ''),
                  'radio_taxi': 'taxiing to holding point runway '+runway,
                  'radio_takeoff': 'departing runway '+runway+via,
                  'radio_departure_contact': 'airborne runway '+runway+via,
                  'radio_descent_request': 'descending'+(f' to {level}' if level else '')+', inbound',
                  'radio_approach_contact': 'inbound for runway '+runway,
                  'radio_landing': 'final runway '+runway, 'radio_go_around': 'going around runway '+runway,
                  'radio_vacated': 'runway '+runway+' vacated',
                  'radio_parked': 'parked'+(f' stand {stand}' if stand else '')}.get(radio_id)
        return None if action is None else f'{airport} traffic, {action}'

    def build(self):
        return {'stage': self.stage, 'stage_label': STAGE_LABEL.get(self.stage),
                'phase': self.current, 'mode': self.phase.get('mode', 'automatic'), 'live': self.phase.get('live', False),
                'header': self.header(), 'track': self.track(), 'now': self.now_block(), 'groups': self.items(),
                'radio': self.radio(), 'stand': self.stand_item(), 'situation': self.situation(), 'atc': self.atc(), 'atis': self.atis(),
                'radio_language': getattr(self.session, 'radio_language', 'auto'), 'phrasebook': self.phrasebook(),
                'upcoming': self.upcoming()}


def cockpit_view(profile, session, phase, flight, network, now):
    return Cockpit(profile, session, phase, flight, network, now).build()
