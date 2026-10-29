"""Data-template radio preparation. No transmission, speech, clipboard or clearance inference."""
from __future__ import annotations

import math
from string import Formatter


def french_position(callsign):
    # Explicit French prefixes; FM outside FMEE/FMCZ includes non-French positions.
    return bool(callsign and callsign.startswith(('LF', 'TFF', 'FMEE', 'FMCZ', 'NWW', 'NT', 'SOCA')))


def scalar_text(value):
    if type(value) in (int, float):
        return f'{value:g}'
    return str(value)


class RadioEngine:
    def __init__(self):
        self.holds = {}
        self.last_at = None

    def trigger(self, radio, profile, session, phase, flight, now):
        inputs = []
        declarations = [d for d in session.declarations if d.revoked_at is None and d.invalidated_reason is None]
        stage = (phase or {}).get('effective', {}).get('value')
        expected_status = 'simulated' if session.universe == 'demo' else 'observed'

        def read(source_id):
            source = profile.sources[source_id]
            path = source.path
            value, nature, reference = None, source.nature, path
            if path.startswith('session.phase.'):
                value = stage == path.rsplit('.', 1)[-1] if stage and (phase or {}).get('effective', {}).get('status') in ('available', 'derived') else None
                nature = 'declared' if (phase or {}).get('mode') == 'manual' else 'calculated'
            elif path.startswith('session.substate.'):
                substate = (phase or {}).get('substate')
                value = substate == path.rsplit('.', 1)[-1] if substate is not None and flight['connected'] and not flight['paused'] and not flight['stale'] else None
            elif path.startswith('events.'):
                key = 'event.'+path.split('.', 1)[1]
                declared = next((d for d in reversed(declarations) if d.field == key
                                 and d.context.get('stage') == stage), None)
                if declared:
                    value, nature, reference = declared.value, 'declared', declared.reference
            elif path.startswith('telemetry.'):
                field = flight['telemetry'].get(path.split('.')[-1], {})
                if (flight['connected'] and not flight['paused'] and not flight['stale']
                        and field.get('status') == expected_status and field.get('unit') == source.unit
                        and field.get('age_s') is not None
                        and 0 <= field['age_s'] <= (source.max_age_s or 8)):
                    value = field.get('value')
            inputs.append({'source': path, 'value': value, 'nature': nature, 'reference': reference})
            return value

        clauses = []
        for clause in radio.trigger.any_of:
            results = []
            for predicate in clause:
                value = read(predicate.source)
                if value is None:
                    results.append(None)
                elif predicate.op == 'eq':
                    numeric = type(value) in (int, float) and type(predicate.value) in (int, float)
                    results.append((numeric or type(value) is type(predicate.value)) and value == predicate.value)
                elif type(value) in (int, float) and math.isfinite(value):
                    results.append({'lt': value < predicate.value, 'lte': value <= predicate.value,
                                    'gt': value > predicate.value, 'gte': value >= predicate.value}[predicate.op])
                else:
                    results.append(None)
            clauses.append(False if False in results else None if None in results else True)
        ready = True in clauses
        if not ready:
            self.holds.pop(radio.id, None)
        else:
            self.holds.setdefault(radio.id, now)
            ready = now-self.holds[radio.id] >= radio.trigger.hold_s
        return {'status': 'ready' if ready else 'unknown' if None in clauses else 'upcoming',
                'label': radio.trigger.label, 'hold_s': radio.trigger.hold_s, 'inputs': inputs}

    def view(self, profile, session, phase, flight, network, now):
        if self.last_at is None or not 0 <= now-self.last_at <= 8:
            self.holds.clear()
        self.last_at = now
        current = (phase or {}).get('effective', {}).get('value')
        section = next((p for p in profile.phases if p.id == current), None)
        if section is None or session.status != 'active':
            return []
        published_current = network['state'] in ('current', 'empty')
        used = network.get('used_station')
        positions = network.get('positions') or []
        stage_airport = (flight.get('plan') or {}).get('origin' if current in (
            'preflight', 'departure', 'climb') else 'destination', {}).get('icao')
        result = []
        for order, radio in enumerate(section.radio):
            trigger = self.trigger(radio, profile, session, phase, flight, now)
            candidates = [p for p in positions if p.get('position') in radio.station_roles
                          and ('current' in p['useful_for'] or stage_airport is not None and
                               any(m.get('airport') == stage_airport for m in p['matched_by']))]
            candidates.sort(key=lambda p: radio.station_roles.index(p['position']))
            position = next((p for p in positions if used and p['callsign'] == used['value']), None) if used else (
                candidates[0] if candidates else None)
            callsign = used['value'] if used else position['callsign'] if position else None
            station = {'callsign': callsign, 'declared': used is not None,
                       'coverage': 'unconfirmed', 'frequency_mhz': None,
                       'state': network['state'], 'source': 'pilot.station.callsign' if used else
                       network.get('feeds', {}).get('whazzup', {}).get('source', 'ivao.whazzup'),
                       'candidates': [p['callsign'] for p in candidates]}
            if position and published_current and position.get('provenance', {}).get('status') == 'current':
                frequency = position.get('frequency_mhz')
                if type(frequency) in (int, float) and math.isfinite(frequency):
                    station['frequency_mhz'] = frequency
            station['notice'] = ('Station déclarée par le pilote ; couverture à confirmer.' if used else
                                 'Station candidate ; couverture probable à confirmer.' if position else
                                 'Couverture inconnue ; absence de position candidate ne vaut pas absence de contrôle.')
            if not published_current:
                station['notice'] += ' Flux indisponible ou périmé ; fréquence publiée non proposée.'
            if used and position and position.get('position') not in radio.station_roles:
                station['notice'] += ' Rôle différent de celui du message ; transfert à confirmer.'
            language = 'fr' if french_position(callsign) else 'en'
            values = flight['values']
            qualified = {}

            def parameter(key):
                item = values[key]
                if key == 'station':
                    # The feed publishes an identifier, not a verified spoken city/station name.
                    qualified[key] = {**item, 'value': None, 'placeholder': '<station>',
                                      'source': station['source'], 'reference': callsign,
                                      'status': 'unavailable'}
                    return '<station>'
                value = item.get('value')
                valid = item['status'] in ('available', 'observed', 'simulated', 'derived') and value is not None
                if profile.values[key].purpose == 'clearance' and item['nature'] != 'declared':
                    valid = False
                if key == 'atis_heard' and (item['nature'] != 'declared' or item['source'] != 'pilot.atis.heard_letter'):
                    valid = False
                if isinstance(value, str):
                    valid = valid and len(value) <= 1000 and not any(ord(c) < 32 for c in value)
                qualified[key] = item if valid else {**item, 'value': None, 'status': 'unavailable'}
                if not valid:
                    return item['placeholder']
                text = scalar_text(value)
                return text + (' '+item['unit'] if item.get('unit') else '')

            def fill(template):
                keys = [key for _, key, _, _ in Formatter().parse(template) if key is not None]
                return template.format_map({key: parameter(key) for key in keys})

            voice = radio.voice_fr if language == 'fr' else radio.voice_en
            pilot, readback = fill(voice.pilot), fill(voice.readback)
            alternate = fill(radio.voice_fr.pilot) if callsign is None else None
            alternate_readback = fill(radio.voice_fr.readback) if callsign is None else None
            unicom = None
            # Cruise announcements require the explicit traffic/airfield trigger, never a polling loop.
            if radio.unicom_en and (not radio.unicom_requires_trigger or trigger['status'] == 'ready'):
                unicom = ' '.join(fill(radio.unicom_en).split())
            result.append({'id': radio.id, 'order': order, 'priority': radio.priority,
                           'trigger': trigger, 'station': station, 'language': language,
                           'mode': 'voice' if used and published_current and position else 'choice',
                           'voice': pilot, 'readback': readback, 'unicom': unicom,
                           'voice_alternate': alternate, 'readback_alternate': alternate_readback,
                           'values': qualified,
                           'readback_notice': 'Gabarit à compléter uniquement après réception ; aucune instruction ATC illustrative ou reçue inventée.',
                           'unicom_notice': 'Variante conditionnelle en anglais ; lire la fréquence et confirmer l’absence de contrôle avant émission. Référence UNICOM 122.800.',
                           'copy_notice': 'Copier ne signifie pas émettre.'})
        return sorted(result, key=lambda r: (r['trigger']['status'] != 'ready', r['order']))
