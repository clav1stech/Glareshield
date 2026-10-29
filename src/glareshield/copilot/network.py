"""Copilot view of the existing IVAO cache. No HTTP, notifications or cockpit access."""
from __future__ import annotations

import hashlib
import re

from ..aibridge.ivao import (STALE_FACTOR, airports_of_interest, bulletin_times, match, rank)
from ..aibridge.context import iso
from .contract import PHASE_IDS, QualifiedValue

PUBLICATION_MAX_AGE_S = 1200
STAGE_ROLES = {
    'preflight': ('origin',), 'departure': ('origin',), 'climb': ('origin',),
    'cruise': ('destination',), 'descent': ('destination',), 'arrival': ('destination',),
}
METAR = re.compile(r'^(?:(?:METAR|SPECI) )?([A-Z0-9]{4}) (\d{6}Z) (?:AUTO |COR )?(.+)$')


def provenance(service, feed, now, moment=None, max_age_s=None):
    info = feed.describe(now, service.interval(feed), detailed=True)
    info.update(source=('scenario.' if getattr(service, 'simulation', False) else '')+'ivao.'+feed.name,
                nature='published', age_s=None, source_age_s=None)
    ages = []
    if feed.fetched_at is not None:
        ages.append(max(0, now-feed.fetched_at))
    if feed.source_updated_at is not None:
        age = now-feed.source_updated_at
        info['source_age_s'] = max(0, age)
        ages.append(max(0, age))
        if age < -60 or age > service.interval(feed)*STALE_FACTOR:
            info['status'] = 'stale'
    if moment is not None:
        info['publication_utc'] = iso(moment)
        info['publication_age_s'] = max(0, now-moment)
        ages.append(max(0, now-moment))
        if now-moment < -60 or (max_age_s is not None and now-moment > max_age_s):
            info['status'] = 'stale'
    if ages:
        info['age_s'] = max(ages)
        if max_age_s is not None and info['age_s'] > max_age_s:
            info['status'] = 'stale'
    return info


def read_metar(raw, airport, source, reference, truncated=False):
    """Only unambiguous standard groups in the observation, before trend/remarks.

    No natural-language ATIS parsing, unit guesses or conversion of altimeter inches.
    Every field retains its own reading status and the entire source text.
    """
    header = METAR.fullmatch(raw or '')
    body = re.split(r'\b(?:RMK|NOSIG|TEMPO|BECMG|FM\d{6})\b', header[3])[0] if header else ''
    tokens = body.split()
    patterns = {
        'qnh': (r'Q\d{4}', 'hPa'),
        'temperature': (r'M?\d{2}/(?:M?\d{2}|//)', '°C'),
        'wind': (r'(?:\d{3}|VRB)\d{2,3}(?:G\d{2,3})?(?:KT|MPS)', None),
    }
    result = {}
    for field, (pattern, unit) in patterns.items():
        candidates = [token for token in tokens if re.fullmatch(pattern, token)]
        reading = 'parsed' if len(candidates) == 1 else 'ambiguous' if candidates else 'missing'
        if not header or header[1] != airport:
            reading = 'unsupported'
        if truncated:
            reading = 'truncated'
        value = None
        if reading == 'parsed':
            token = candidates[0]
            if field == 'qnh':
                value = int(token[1:])
                # An Axxxx and Qxxxx together are not silently arbitrated.
                if not 850 <= value <= 1100 or any(re.fullmatch(r'A\d{4}', t) for t in tokens):
                    reading, value = 'ambiguous', None
            elif field == 'temperature':
                value = int(token.split('/')[0].replace('M', '-'))
                if not -80 <= value <= 60:
                    reading, value = 'ambiguous', None
            else:
                value = token
                if token[:3] != 'VRB' and int(token[:3]) > 360:
                    reading, value = 'ambiguous', None
        # A timestamp is required to offer a parsed publication as a current value.
        if source.get('publication_utc') is None:
            value = None
        status = 'unavailable' if value is None else 'available' if source['status'] == 'current' else 'stale'
        qualified = QualifiedValue(value=value, unit=unit, nature='published', status=status,
                                   source='ivao.metar', reference=reference,
                                   age_s=source['age_s'], max_age_s=PUBLICATION_MAX_AGE_S,
                                   verification='unverified').model_dump()
        result[field] = {**qualified, 'reading_status': reading, 'source_text': raw,
                         'provenance': source}
    return result


def declared(declaration, now):
    return QualifiedValue(value=declaration.value, unit=declaration.unit, nature='declared',
                          status='available', source='pilot.'+declaration.field,
                          reference=declaration.id, age_s=max(0, now-(declaration.occurred_at or declaration.recorded_at)),
                          max_age_s=None, verification='not_applicable').model_dump()


class NetworkContext:
    """Shared adapter for Vol and the forthcoming reminder/radio engines (#18/#19)."""

    def __init__(self, bridge):
        self.bridge = bridge

    def view(self, phase, session=None, after=0):
        bridge, now = self.bridge, self.bridge.clock()
        service = bridge.network_cache()
        current = (phase or {}).get('effective', {}).get('value')
        following = PHASE_IDS[PHASE_IDS.index(current)+1] if current in PHASE_IDS[:-1] else None
        declarations = [d for d in session.declarations if d.revoked_at is None
                        and d.invalidated_reason is None] if session else []
        station_declaration = next((d for d in reversed(declarations) if d.field == 'station.callsign'), None)
        pilot_atis = [{**d.model_dump(), 'qualified': declared(d, now)} for d in declarations
                      if d.kind == 'atis']
        feeds = {feed.name: provenance(service, feed, now) for feed in service.feeds}
        result = {'schema_version': 'glareshield.copilot_network/1', 'generated_utc': iso(now),
                  'simulation': bool(getattr(service, 'simulation', False)),
                  'state': 'disabled', 'feeds': feeds, 'phase': current, 'next_phase': following,
                  'phase_status': (phase or {}).get('effective', {}).get('status', 'unavailable'),
                  'positions': None, 'atis': [], 'weather': [], 'publications': {},
                  'used_station': declared(station_declaration, now) if station_declaration else None,
                  'used_station_state': 'disabled' if not service.settings.enabled else 'unknown',
                  'pilot_atis': pilot_atis,
                  'events': service.event_view(after),
                  'notice': 'Positions candidates : rapprochement technique, couverture ATC non confirmée. '
                            'IVAO publié, météo OFP, conditions MSFS et déclarations pilote restent distincts. '
                            'ATIS téléchargé ≠ consulté ≠ annoncé. Aucun choix UNICOM automatique.'}
        if result['simulation']:
            result['notice'] = 'DÉMONSTRATION IVAO fictive, aucun téléchargement. '+result['notice']
        if not service.settings.enabled:
            return result
        plan = bridge.sessions.current_plan()
        airports = airports_of_interest(plan, service.settings.airports)
        aircraft = bridge.aircraft_position(now)
        position = (aircraft['latitude'], aircraft['longitude']) if aircraft.get('status') in ('observed', 'simulated') else None
        radii = {'aerodrome': service.settings.radius_aerodrome_nm,
                 'approach': service.settings.radius_approach_nm, 'enroute': service.settings.radius_enroute_nm}
        result['selection'] = {'aircraft': aircraft, 'radii_nm': radii}
        stations = service.stations()
        result['state'] = 'unknown' if stations is None else 'stale' if feeds['whazzup']['status'] != 'current' else 'current'
        if stations is not None:
            result['used_station_state'] = 'stale' if result['state'] == 'stale' else (
                'online' if station_declaration and any(s['kind'] == 'atc' and s['callsign'] == station_declaration.value
                                                       for s in stations) else 'offline' if station_declaration else 'unknown')
            candidates = []
            for station in stations:
                if station['kind'] != 'atc':
                    continue
                matches, distance = match(station, airports, position, radii)
                if matches or (station_declaration and station['callsign'] == station_declaration.value):
                    candidates.append((station, matches, distance))
            candidates.sort(key=lambda item: rank(item, airports, radii))
            result['positions'] = []
            for station, matches, distance in candidates:
                useful = []
                for slot, phase_id in (('current', current), ('next', following)):
                    profile_phase = next((p for p in bridge.sessions.profile.phases if p.id == phase_id), None)
                    roles = {role for radio in profile_phase.radio for role in radio.station_roles} if profile_phase else set()
                    relevant_airports = {a['icao'] for a in airports if set(a['roles']) & set(STAGE_ROLES.get(phase_id, ()))}
                    if station['position'] in roles and (station['position'] in ('CTR', 'FSS') or any(
                            m.get('airport') in relevant_airports for m in matches)):
                        useful.append(slot)
                item = {**service.station_view(station, matches, distance, True),
                        'provenance': feeds['whazzup'], 'useful_for': useful,
                        'coverage': 'unconfirmed', 'pilot_selected': bool(station_declaration and
                                                                         station['callsign'] == station_declaration.value)}
                result['positions'].append(item)
                if station['atis']:
                    atis = {**service.atis_view(station, matches, airports, now),
                            'matched_by': matches, 'coverage': 'unconfirmed', 'reading_status': 'not_interpreted',
                            'provenance': provenance(service, service.whazzup, now, station['atis']['timestamp'], PUBLICATION_MAX_AGE_S)}
                    text = '\n'.join(atis['lines'])
                    atis['reference'] = station['callsign']+':'+hashlib.sha256(text.encode()).hexdigest()[:16]+':'+(atis.get('revision') or '?')
                    result['atis'].append(atis)
            if result['state'] == 'current' and not result['positions']:
                result['state'] = 'empty'
        for airport in airports:
            weather = {'icao': airport['icao'], 'roles': airport['roles']}
            for feed in (service.metar, service.taf):
                bulletin = service.bulletin(feed, airport['icao'], now, True)
                item = (feed.data or {}).get(airport['icao'])
                moment = None
                if item:
                    times = bulletin_times(item['raw'], feed.name, item['updated_at'] or feed.fetched_at)
                    moment = times.get('observed_at', times.get('issued_at'))
                source = provenance(service, feed, now, moment, PUBLICATION_MAX_AGE_S)
                if item and item['updated_at'] is not None:
                    source['ivao_updated_utc'] = iso(item['updated_at'])
                    source['ivao_updated_age_s'] = max(0, now-item['updated_at'])
                bulletin['provenance'] = source
                bulletin['reference'] = feed.name+':'+airport['icao']+':'+hashlib.sha256((bulletin.get('raw') or '').encode()).hexdigest()[:16]
                if feed is service.metar:
                    bulletin['values'] = read_metar(bulletin.get('raw'), airport['icao'], source,
                                                   bulletin['reference'], bulletin.get('raw_truncated', False))
                weather[feed.name] = bulletin
            result['weather'].append(weather)
            for role, stage in (('origin', 'departure'), ('destination', 'arrival')):
                if role in airport['roles']:
                    result['publications'][stage] = weather['metar']['values']
        for declaration in result['pilot_atis']:
            context = declaration['context']
            relevant = [a for a in result['atis'] if a.get('airport') == context['airport']
                        and (not context.get('station') or a['station'] == context['station'])]
            declaration['comparison'] = 'unknown'
            if len(relevant) == 1 and relevant[0]['provenance']['status'] == 'current':
                letter = relevant[0].get('revision')
                if re.fullmatch('[A-Z]', letter or '') and re.fullmatch('[A-Z]', str(declaration['value'])):
                    declaration['comparison'] = 'same_letter' if letter == declaration['value'] else 'different_letter'
                    declaration['published_reference'] = relevant[0]['reference']
        return result
