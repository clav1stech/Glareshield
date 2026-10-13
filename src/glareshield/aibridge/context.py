"""Channel-agnostic flight context document shared by the UI, exports and future MCP tools."""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from .catalog import GROUPS, Entry
from .telemetry import TelemetryStore, qualify

SCHEMA = 'glareshield.flight_context/1'
LIMITS = {'essential': 12000, 'detailed': 48000}
NOTICE = ('Données de simulation (MSFS 2024, Fenix A320) relevées par Glareshield en lecture seule. '
          'status : observed = mesure récente du simulateur ; stale = dernière mesure connue, périmée ; '
          'unavailable = non disponible ; simulated = scénario fictif sans simulateur. '
          'Le plan SimBrief est un plan prévu, pas la route active du MCDU. '
          'Ne pas déduire de mode FMA, d’alerte ECAM ni de valeur absente. Usage limité à la simulation.')
CHAT_HEADER = ('Voici le contexte de mon vol simulé (MSFS 2024, Fenix A320), exporté par Glareshield. '
               'Appuie-toi uniquement sur les valeurs fournies, en tenant compte de leur statut et de leur âge ; '
               'signale toute information manquante au lieu de la supposer.')


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def distance_nm(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3440.065*2*math.asin(min(1, math.sqrt(a)))


def plan_view(plan: dict | None, level: str) -> dict | None:
    if plan is None:
        return None
    view = {key: value for key, value in plan.items() if key not in ('waypoints', 'waypoints_total')}
    if level == 'essential':
        for key in ('origin', 'destination'):
            if key in view:
                view[key] = {k: v for k, v in view[key].items() if k not in ('latitude', 'longitude', 'name', 'iata')}
        view['alternates'] = [{k: v for k, v in item.items() if k in ('icao', 'runway')} for item in view.get('alternates', [])]
        view.pop('weights', None)
        view['fuel'] = {k: v for k, v in view.get('fuel', {}).items() if k in ('ramp', 'takeoff', 'trip', 'landing', 'minimum_takeoff')}
    else:
        view['waypoints'] = plan.get('waypoints', [])
        view['waypoints_total'] = plan.get('waypoints_total', len(view['waypoints']))
    return view


def checks(fields: dict, plan: dict | None, store: TelemetryStore) -> list[dict]:
    """Explicit, verifiable consistency checks; no flight phase or guidance mode is inferred."""
    result = []
    if store.origin == 'simconnect' and not store.connected:
        result.append({'level': 'warning', 'message': 'Simulateur non connecté : aucune mesure actuelle.'})
    if store.paused:
        result.append({'level': 'info', 'message': 'Simulateur en pause.'})
    stale = [key for key, field in fields.items() if field['status'] == 'stale']
    if stale:
        result.append({'level': 'warning', 'message': 'Mesures périmées : '+', '.join(stale)+'.'})
    position = [fields.get(key, {}) for key in ('latitude', 'longitude', 'on_ground')]
    if plan and all(item.get('status') in ('observed', 'simulated') for item in position) and position[2]['value']:
        distances = {}
        for name in ('origin', 'destination'):
            airport = plan.get(name, {})
            if 'latitude' in airport and 'longitude' in airport:
                distances[name] = distance_nm(position[0]['value'], position[1]['value'],
                                              airport['latitude'], airport['longitude'])
        if len(distances) == 2 and min(distances.values()) > 30:
            result.append({'level': 'warning', 'message': 'Appareil au sol à plus de 30 NM du départ et de la '
                           'destination de l’OFP : le plan ne correspond peut-être pas à la session.'})
    return result


def derived(fields: dict, plan: dict | None) -> dict:
    """Values computed from observations, labelled with their method."""
    result = {}
    lat, lon = fields.get('latitude', {}), fields.get('longitude', {})
    destination = (plan or {}).get('destination', {})
    if (lat.get('status') in ('observed', 'simulated') and lon.get('status') in ('observed', 'simulated')
            and 'latitude' in destination and 'longitude' in destination):
        result['direct_distance_to_destination'] = {
            'value': round(distance_nm(lat['value'], lon['value'], destination['latitude'], destination['longitude'])),
            'unit': 'NM', 'status': 'derived',
            'method': 'Orthodromie entre la position observée et l’aéroport de destination de l’OFP ; ne suit pas la route.'}
    return result


def build_context(level: str, entries: list[Entry], store: TelemetryStore, plan: dict | None,
                  plan_status: dict, now: float) -> dict:
    if level not in LIMITS:
        raise ValueError('Niveau d’export inconnu.')
    selected = [entry for entry in entries if level == 'detailed' or entry.level == 'essential']
    fields = {entry.key: qualify(entry, store, now) for entry in selected}
    groups: dict[str, dict] = {}
    unavailable = []
    for entry in selected:
        field = dict(fields[entry.key])
        if level == 'essential':
            field.pop('label', None)
            if field['status'] == 'unavailable':
                unavailable.append(entry.key)
                continue
            field.pop('reason', None)
        else:
            field['source'] = ('SimVar ' if entry.origin == 'simvar' else 'LVar ')+entry.variable
            field['verification'] = 'validated_locally' if entry.validated else (
                'msfs_sdk' if entry.origin == 'simvar' else 'configured_unverified')
            if entry.note:
                field['note'] = entry.note
        if field.get('unit') is None:
            field.pop('unit', None)
        groups.setdefault(entry.group, {})[entry.key] = field
    document = {
        'schema': SCHEMA,
        'generated_utc': iso(now),
        'level': level,
        'data_origin': 'simulation_scenario' if store.origin == 'scenario' else 'simconnect',
        'notice': NOTICE,
        'simulator': {'connected': store.connected, 'paused': store.paused,
                      'last_message_age_s': None if store.last_message is None else round(now-store.last_message, 1)},
        'telemetry': groups,
    }
    if unavailable:
        document['unavailable'] = unavailable
    extra = derived(fields, plan)
    if extra:
        document['derived'] = extra
    document['flight_plan'] = None if plan is None else {
        'source': plan_status.get('source'), 'fetched_utc': plan_status.get('fetched_utc'),
        'warnings': plan_status.get('warnings', []), **plan_view(plan, level)}
    document['checks'] = checks(fields, plan, store)
    return limit(document, LIMITS[level])


def limit(document: dict, maximum: int) -> dict:
    """Trim optional route details first; flag any truncation explicitly."""
    plan = document.get('flight_plan') or {}
    while len(serialize(document)) > maximum and plan.get('waypoints'):
        plan['waypoints'] = plan['waypoints'][:len(plan['waypoints'])//2]
        plan['waypoints_truncated'] = True
    if len(serialize(document)) > maximum and plan.get('route'):
        plan['route'] = plan['route'][:400]+' …'
        plan['route_truncated'] = True
    return document


def serialize(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(',', ':'))


def chat_text(document: dict) -> str:
    """Text ready to paste into a conversational assistant."""
    return CHAT_HEADER+'\n\n```json\n'+serialize(document)+'\n```\n'


def group_labels() -> dict:
    return dict(GROUPS)
