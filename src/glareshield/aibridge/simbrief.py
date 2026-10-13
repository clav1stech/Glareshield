"""Manual retrieval and summary of the latest SimBrief OFP (planned data only)."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ..config import atomic_write

URL = 'https://www.simbrief.com/api/xml.fetcher.php'
MIN_INTERVAL_S = 15
MAX_WAYPOINTS = 120


class OFPError(Exception):
    pass


def text(value) -> str | None:
    """SimBrief encodes empty XML elements as objects or empty strings."""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        value = str(value).strip()
        return value or None
    return None


def number(value, integer=False):
    raw = text(value)
    if raw is None:
        return None
    try:
        result = float(raw)
    except ValueError:
        return None
    if result != result or result in (float('inf'), float('-inf')):
        return None
    return int(round(result)) if integer else result


def section(data, name) -> dict:
    value = data.get(name) if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


def items(value) -> list:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return [value] if isinstance(value, dict) and value else []


def utc(value) -> str | None:
    """Accept ISO 8601 (json=v2) or Unix seconds (json=1)."""
    raw = text(value)
    if raw is None:
        return None
    try:
        if not raw.lstrip('-').isdigit():
            moment = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                return None
            return moment.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')
        stamp = int(raw)
        if stamp <= 0:
            return None
        return datetime.fromtimestamp(stamp, UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except (OverflowError, OSError, ValueError):
        return None


def minutes(value):
    """Accept HH:MM[:SS] (json=v2) or a number of seconds (json=1)."""
    raw = text(value)
    if raw is not None and ':' in raw:
        try:
            parts = [int(part) for part in raw.split(':')]
        except ValueError:
            return None
        if len(parts) not in (2, 3) or any(part < 0 for part in parts):
            return None
        seconds = parts[0]*3600+parts[1]*60+(parts[2] if len(parts) == 3 else 0)
        return int(round(seconds/60))
    seconds = number(value)
    return None if seconds is None else int(round(seconds/60))


def airport(data) -> dict | None:
    code = text(data.get('icao_code'))
    if not code:
        return None
    return {'icao': code, 'iata': text(data.get('iata_code')), 'name': text(data.get('name')),
            'runway': text(data.get('plan_rwy')), 'elevation_ft': number(data.get('elevation'), True),
            'latitude': number(data.get('pos_lat')), 'longitude': number(data.get('pos_long')),
            'metar': text(data.get('metar'))}


def compact(value):
    """Drop unknown values so the summary never presents a guessed field."""
    if isinstance(value, dict):
        result = {key: compact(child) for key, child in value.items()}
        return {key: child for key, child in result.items() if child not in (None, {}, [])}
    if isinstance(value, list):
        return [compact(child) for child in value if compact(child) not in (None, {}, [])]
    return value


def parse_ofp(data) -> dict:
    """Summarise a SimBrief JSON OFP without inventing missing fields."""
    if not isinstance(data, dict):
        raise OFPError('Réponse SimBrief illisible.')
    fetch = section(data, 'fetch')
    status = text(fetch.get('status'))
    if status and status.casefold() != 'success':
        raise OFPError('SimBrief : '+status[:120])
    general, params = section(data, 'general'), section(data, 'params')
    origin, destination = airport(section(data, 'origin')), airport(section(data, 'destination'))
    if not origin or not destination:
        raise OFPError('OFP incomplet : départ ou destination absent.')
    fuel, times, weights = section(data, 'fuel'), section(data, 'times'), section(data, 'weights')
    aircraft, atc = section(data, 'aircraft'), section(data, 'atc')
    alternates = [airport(item) for item in items(data.get('alternate'))]
    waypoints = []
    navlog = data.get('navlog')
    # json=v2 returns the fixes as a list, json=1 nests them under navlog.fix.
    for fix in items(navlog if isinstance(navlog, list) else section(data, 'navlog').get('fix')):
        ident = text(fix.get('ident'))
        if not ident:
            continue
        waypoints.append({'ident': ident, 'airway': text(fix.get('via_airway')), 'type': text(fix.get('type')),
                          'stage': text(fix.get('stage')), 'altitude_ft': number(fix.get('altitude_feet'), True),
                          'latitude': number(fix.get('pos_lat')), 'longitude': number(fix.get('pos_long'))})
    airline, flight = text(general.get('icao_airline')), text(general.get('flight_number'))
    units = {'kgs': 'kg', 'lbs': 'lb'}.get((text(params.get('units')) or '').casefold(), text(params.get('units')))
    summary = {
        'nature': 'planned',
        'ofp_id': text(params.get('request_id')),
        'generated_utc': utc(params.get('time_generated')),
        'airac': text(params.get('airac')),
        'weight_unit': units,
        'flight': {'callsign': text(atc.get('callsign')), 'number': (airline or '')+(flight or '') or None},
        'aircraft': {'icao': text(aircraft.get('icaocode')), 'name': text(aircraft.get('name')),
                     'registration': text(aircraft.get('reg'))},
        'origin': origin, 'destination': destination,
        'alternates': [item for item in alternates if item],
        'cruise': {'initial_altitude_ft': number(general.get('initial_altitude'), True),
                   'cost_index': text(general.get('costindex')), 'profile': text(general.get('cruise_profile'))},
        'route': text(general.get('route')),
        'sid': text(general.get('sid_ident')), 'star': text(general.get('star_ident')),
        'distance_nm': number(general.get('route_distance'), True) or number(general.get('air_distance'), True),
        'times': {'enroute_min': minutes(times.get('est_time_enroute')), 'block_min': minutes(times.get('est_block')),
                  'scheduled_out_utc': utc(times.get('sched_out')), 'scheduled_in_utc': utc(times.get('sched_in'))},
        'fuel': {key: number(fuel.get(source), True) for key, source in (
            ('ramp', 'plan_ramp'), ('takeoff', 'plan_takeoff'), ('landing', 'plan_landing'),
            ('trip', 'enroute_burn'), ('contingency', 'contingency'), ('alternate', 'alternate_burn'),
            ('final_reserve', 'reserve'), ('extra', 'extra'), ('taxi', 'taxi'), ('minimum_takeoff', 'min_takeoff'))},
        'weights': {key: number(weights.get(source), True) for key, source in (
            ('zero_fuel', 'est_zfw'), ('takeoff', 'est_tow'), ('landing', 'est_ldw'))},
        'waypoints': waypoints[:MAX_WAYPOINTS],
    }
    result = compact(summary)
    result['waypoints_total'] = len(waypoints)
    return result


class FlightPlanStore:
    """Last valid OFP summary, kept when a later retrieval fails."""

    def __init__(self, path: Path, clock=time.time, transport: httpx.AsyncBaseTransport | None = None):
        self.path = path
        self.clock = clock
        self.transport = transport
        self.plan: dict | None = None
        self.fetched_at: float | None = None
        self.source = 'simbrief'
        self.error: str | None = None
        self.last_attempt: float | None = None
        self.load()

    def load(self) -> None:
        try:
            cached = json.loads(self.path.read_text(encoding='utf-8'))
            self.plan, self.fetched_at, self.source = cached['plan'], float(cached['fetched_at']), cached.get('source', 'simbrief')
        except (OSError, ValueError, KeyError, TypeError):
            self.plan = self.fetched_at = None

    def store(self, plan: dict, source: str) -> dict:
        self.plan, self.fetched_at, self.source, self.error = plan, self.clock(), source, None
        atomic_write(self.path, json.dumps({'plan': plan, 'fetched_at': self.fetched_at, 'source': source},
                                           ensure_ascii=False))
        return plan

    def clear(self) -> None:
        self.plan = self.fetched_at = self.error = None
        self.path.unlink(missing_ok=True)

    async def refresh(self, user: str | None, kind: str = 'username') -> dict:
        if not user:
            raise OFPError('Renseigner l’identifiant SimBrief dans les réglages AI Bridge.')
        now = self.clock()
        if self.last_attempt is not None and now-self.last_attempt < MIN_INTERVAL_S:
            raise OFPError(f'Patienter {int(MIN_INTERVAL_S-(now-self.last_attempt))+1} s avant une nouvelle actualisation.')
        self.last_attempt = now
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False,
                                         headers={'User-Agent': 'Glareshield AI Bridge'}) as client:
                response = await client.get(URL, params={kind: user, 'json': 'v2'})
        except httpx.HTTPError:
            self.error = 'Réseau ou service SimBrief indisponible.'
            raise OFPError(self.error) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        try:
            if response.status_code != 200:
                status = text(section(data, 'fetch').get('status')) if isinstance(data, dict) else None
                raise OFPError('SimBrief : '+(status[:120] if status else f'requête refusée (HTTP {response.status_code}).'))
            plan = parse_ofp(data)
        except OFPError as error:
            self.error = str(error)
            raise
        return self.store(plan, 'simbrief')

    def describe(self, max_age_h: float) -> dict:
        """Plan status for display and export, with explicit ageing."""
        if self.plan is None:
            return {'available': False, 'error': self.error}
        now = self.clock()
        result = {'available': True, 'source': self.source, 'error': self.error,
                  'fetched_utc': datetime.fromtimestamp(self.fetched_at, UTC).isoformat(timespec='seconds').replace('+00:00', 'Z'),
                  'fetched_age_min': int((now-self.fetched_at)//60), 'warnings': []}
        generated = self.plan.get('generated_utc')
        if generated:
            age_h = (now-datetime.fromisoformat(generated.replace('Z', '+00:00')).timestamp())/3600
            result['generated_age_h'] = round(age_h, 1)
            if age_h > max_age_h:
                result['warnings'].append(f'OFP généré il y a {age_h:.0f} h : vérifier qu’il correspond au vol en cours.')
        else:
            result['warnings'].append('Heure de génération de l’OFP inconnue.')
        if self.error:
            result['warnings'].append('Dernière actualisation échouée : plan précédent conservé.')
        if self.source == 'demo':
            result['warnings'].append('OFP de démonstration fictif.')
        return result
