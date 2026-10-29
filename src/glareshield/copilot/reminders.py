"""Session-scoped reminders from qualified observations and the shared IVAO cache."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math

from pydantic import Field

from ..model import StrictModel


class ReminderEvent(StrictModel):
    id: str
    rule: str
    label: str
    priority: int
    triggered_at: float
    source: str
    method: str
    reference: str
    acknowledged_at: float | None = None


class ReminderState(StrictModel):
    events: dict[str, ReminderEvent] = Field(default_factory=dict, max_length=500)
    fired: list[str] = Field(default_factory=list, max_length=50)
    atis: dict[str, str] = Field(default_factory=dict, max_length=300)
    network_stream: str | None = None
    network_sequence: int = 0


def tod_view(session, now):
    declarations = [d for d in session.declarations if d.field == 'selection.tod_utc'
                    and d.revoked_at is None and d.invalidated_reason is None]
    if declarations:
        declaration = declarations[-1]
        try:
            stamp = datetime.fromisoformat(str(declaration.value).replace('Z', '+00:00'))
            if stamp.tzinfo is not None and 0 <= now-declaration.recorded_at <= 43200:
                return {'kind': 'supplied', 'status': 'available', 'value': stamp.timestamp(),
                        'unit': 'UTC', 'source': 'pilot.selection.tod_utc', 'reference': declaration.reference,
                        'remaining_s': stamp.timestamp()-now,
                        'notice': 'TOD fourni explicitement par le pilote ; aucune lecture du TOD MCDU.'}
        except (ValueError, TypeError, OverflowError):
            pass
    return {'kind': 'unknown', 'status': 'unavailable', 'value': None, 'unit': 'UTC',
            'source': 'indisponible', 'reference': None, 'remaining_s': None,
            'notice': 'TOD inconnu ; aucune estimation géométrique du TOD ni déduction du TOD MCDU.'}


def current_number(flight, key, unit):
    value = flight['telemetry'].get(key, {})
    if (value.get('status') not in ('observed', 'simulated') or value.get('unit') != unit
            or type(value.get('value')) not in (int, float) or not math.isfinite(value['value']) or value.get('age_s') is None
            or not 0 <= value['age_s'] <= 8):
        return None
    return value['value']


class ReminderEngine:
    def __init__(self):
        self.last_at = None
        self.holds = {}
        self.armed = set()

    def hold(self, key, condition, duration, now):
        if not condition:
            self.holds.pop(key, None)
            return False
        self.holds.setdefault(key, now)
        return now-self.holds[key] >= duration

    def evaluate(self, state, rules, session, phase, flight, network, now, *, active=True):
        state = state.model_copy(deep=True)
        healthy = active and flight['connected'] and not flight['paused'] and not flight['stale']
        if not healthy or self.last_at is None or not 0 <= now-self.last_at <= 8:
            self.holds.clear()
            self.armed.clear()
        self.last_at = now
        current = (phase or {}).get('effective', {}).get('value')
        altitude = current_number(flight, 'altitude_msl', 'ft')
        agl = current_number(flight, 'altitude_agl', 'ft')
        critical = (current in ('departure', 'arrival') and (phase or {}).get('substate') != 'parking'
                    or current in ('climb', 'descent') and (agl is None or agl < 10000))
        tod = tod_view(session, now)
        upcoming = []

        def emit(rule, reference, method, label=None, occurrence=None):
            token = json.dumps([rule.id, occurrence or reference], sort_keys=True)
            key = 'reminder_'+hashlib.sha256(token.encode()).hexdigest()[:24]
            if key in state.events:
                return
            if len(state.events) >= 500:
                completed = next((k for k, e in state.events.items() if e.acknowledged_at is not None), None)
                if completed is None:
                    return
                del state.events[completed]
            state.events[key] = ReminderEvent(id=key, rule=rule.id, label=label or rule.label,
                priority=rule.priority, triggered_at=now, source=('scenario.ivao' if network.get('simulation') else 'ivao') if rule.kind.startswith(('atis', 'atc')) else
                'scenario' if session.universe == 'demo' else 'simconnect', method=method, reference=reference)

        for rule in rules:
            if rule.kind.startswith(('atis', 'atc')):
                continue
            eligible = current in rule.phases
            method = ''
            condition = False
            missing = []
            if rule.kind == 'arrival_preparation':
                distance = flight['derived'].get('direct_distance_to_destination', {}).get('value')
                plan_current = flight.get('plan') is not None and flight.get('plan_current', False)
                distance = distance if plan_current and type(distance) in (int, float) else None
                supplied = tod['remaining_s']
                condition = (distance is not None and distance <= rule.distance_nm or
                             supplied is not None and 0 < supplied <= rule.tod_lead_s)
                method = (f'En croisière, destination prévue à ≤ {rule.distance_nm:g} NM en orthodromie '
                          f'ou TOD explicitement fourni dans ≤ {rule.tod_lead_s/60:g} min ; '
                          f'confirmation continue {rule.hold_s:g} s. Ceci ne calcule pas le TOD.')
                if distance is None:
                    missing.append('Position fraîche ou OFP actuel absent.')
                if tod['kind'] == 'unknown':
                    missing.append('TOD non fourni ; seul l’indice de distance est disponible.')
            elif rule.kind == 'descent':
                condition = current == 'descent'
                method = f'Phase descente confirmée ou déclarée pendant {rule.hold_s:g} s ; aucune clairance déduite.'
            elif rule.kind == 'altitude_crossing':
                low, high = rule.altitude_ft-rule.hysteresis_ft, rule.altitude_ft+rule.hysteresis_ft
                method = (f'Altitude vraie MSL, seuil {rule.altitude_ft:g} ft, hystérésis ±{rule.hysteresis_ft:g} ft ; '
                          f'{rule.hold_s:g} s stables de chaque côté. Ce n’est pas un franchissement de FL100.')
                if altitude is None or not healthy or not eligible:
                    self.armed.discard(rule.id)
                    self.holds.pop(rule.id+'_arm', None)
                    missing.append('Altitude MSL fraîche et connexion hors pause requises.')
                else:
                    before = altitude <= low if rule.direction == 'up' else altitude >= high
                    if self.hold(rule.id+'_arm', before, rule.hold_s, now):
                        self.armed.add(rule.id)
                    condition = rule.id in self.armed and (altitude >= high if rule.direction == 'up' else altitude <= low)
            fired = rule.id in state.fired
            upcoming.append({'id': rule.id, 'label': rule.label, 'trigger': method,
                             'uncertainty': missing, 'fired': fired, 'eligible': eligible})
            if not fired and self.hold(rule.id, healthy and eligible and condition, rule.hold_s, now):
                emit(rule, rule.id, method)
                state.fired.append(rule.id)

        # This reads the existing non-consuming stream. It never calls an overlay notifier.
        stream = network['events']
        same_stream = state.network_stream == stream['stream_id']
        gap = same_stream and state.network_sequence < stream.get('oldest_sequence', 1)-1
        events = [e for e in stream['events'] if same_stream and not gap and e['sequence'] > state.network_sequence]
        positions = {p['callsign']: p for p in network.get('positions') or []}
        network_current = active and healthy and network['state'] in ('current', 'empty')
        if network_current:
            for atis in network['atis']:
                station = atis['station']
                if atis['provenance']['status'] != 'current':
                    continue
                previous = state.atis.get(station)
                reference = atis['reference']
                position = positions.get(station, {})
                stage_airport = (flight.get('plan') or {}).get('origin' if current in (
                    'preflight', 'departure', 'climb') else 'destination', {}).get('icao')
                relevant = ('current' in position.get('useful_for', []) or position.get('pilot_selected')
                            or stage_airport is not None and atis.get('airport') == stage_airport)
                if relevant and previous != reference:
                    state.atis[station] = reference
                    kind = 'atis_acquired' if previous is None else 'atis_changed'
                    rule = next((r for r in rules if r.kind == kind and current in r.phases), None)
                    if relevant and rule:
                        event = next((e for e in reversed(events) if e['callsign'] == station and e['kind'] in ('atis_new', 'atis_changed')), None)
                        change = 'première acquisition, pas un changement' if previous is None else (
                            'lettre' if previous.rsplit(':', 1)[-1] != reference.rsplit(':', 1)[-1] else 'texte à lettre identique')
                        emit(rule, reference, 'Cache IVAO partagé : '+change+' ; téléchargé ne signifie pas consulté.',
                             rule.label+' · '+station+' · '+change,
                             occurrence=[reference, event or now])
            for event in events:
                if event['kind'] not in ('connected', 'disconnected'):
                    continue
                station = positions.get(event['callsign'])
                stage_airport = (flight.get('plan') or {}).get('origin' if current in ('preflight', 'departure', 'climb') else 'destination', {}).get('icao')
                relevant = (station and ('current' in station['useful_for'] or station['pilot_selected'])) or any(
                    m.get('airport') == stage_airport for m in event.get('matched_by', []))
                rule = next((r for r in rules if r.kind == 'atc_presence' and current in r.phases), None)
                if relevant and rule:
                    emit(rule, event['callsign'], 'Événement du flux IVAO partagé ; couverture non confirmée, aucune nouvelle notification externe.',
                         rule.label+' · '+event['callsign']+' · '+('connecté' if event['kind'] == 'connected' else 'déconnecté'),
                         occurrence=[stream['stream_id'], event['sequence']])
        # An outage, pause or fresh process sets a baseline rather than inventing missed transitions.
        state.network_stream = stream['stream_id']
        state.network_sequence = stream['latest_sequence']
        pending = sorted((e.model_dump() for e in state.events.values() if e.acknowledged_at is None),
                         key=lambda e: (-e['priority'], e['triggered_at'], e['id']))
        visible = [e for e in pending if not critical or e['priority'] >= 80]
        limit = 1 if critical else 5
        return state, {'active': visible[:limit], 'pending_count': len(pending),
                       'deferred_count': len(pending)-len(visible[:limit]), 'critical': bool(critical),
                       'upcoming': upcoming, 'tod': tod, 'suspended': not healthy,
                       'network_state': network['state'], 'gap': bool(gap)}
