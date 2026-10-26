"""Channel-agnostic flight context document shared by the UI, exports and future MCP tools."""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from .catalog import GROUPS, Entry
from .telemetry import TelemetryStore, qualify

SCHEMA = 'glareshield.flight_context/3'
# briefing: once on the ground; flight: compact update sent repeatedly; full: diagnostics.
LEVELS = ('briefing', 'flight', 'full')
LIMITS = {'briefing': 30000, 'flight': 8000, 'full': 60000}
UPCOMING = 5
LB_TO_KG = .45359237
USABLE = ('observed', 'simulated')
NOTICE = ('Données de simulation (MSFS 2024, Fenix A320) relevées par Glareshield en lecture seule. '
          'status : observed = mesure récente du simulateur ; stale = dernière mesure connue, périmée ; '
          'unavailable = non disponible ; simulated = scénario fictif sans simulateur ; '
          'derived = calculé par Glareshield, méthode indiquée. '
          'Le plan SimBrief est un plan prévu, pas la route active du MCDU. '
          'pilot_notes contient des déclarations du pilote, non vérifiées par le simulateur. '
          'ivao contient des données publiées par le réseau IVAO, avec leur provenance (voir ivao.notice). '
          'Ne pas déduire de mode FMA, d’alerte ECAM ni de valeur absente. Usage limité à la simulation.')
RULE = ('Appuie-toi uniquement sur les valeurs fournies, en tenant compte de leur statut et de leur âge ; '
        'signale toute information manquante au lieu de la supposer.')
CHAT_HEADERS = {
    'briefing': ('Voici le briefing de mon vol simulé (MSFS 2024, Fenix A320), exporté par Glareshield. '
                 'Garde-le comme référence pour la suite de la conversation : je t’enverrai ensuite des '
                 'points de situation en vol. '+RULE),
    'flight': ('Point de situation de mon vol simulé (MSFS 2024, Fenix A320), exporté par Glareshield. '
               'Il complète le briefing envoyé plus tôt dans cette conversation. '+RULE),
    'full': ('Voici l’export complet de diagnostic de mon vol simulé (MSFS 2024, Fenix A320), exporté par '
             'Glareshield, avec la source et la vérification de chaque valeur. '+RULE),
}


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def distance_nm(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3440.065*2*math.asin(min(1, math.sqrt(a)))


def pick(data: dict, keys) -> dict:
    return {key: data[key] for key in keys if key in data}


def plan_view(plan: dict | None, level: str) -> dict | None:
    if plan is None:
        return None
    if level == 'full':
        return dict(plan)
    if level == 'flight':
        view = pick(plan, ('nature', 'ofp_id', 'generated_utc', 'airac', 'weight_unit', 'flight', 'star', 'cruise'))
        view['destination'] = pick(plan.get('destination', {}), ('icao', 'runway', 'elevation_ft', 'metar'))
        view['alternates'] = [pick(item, ('icao', 'runway')) for item in plan.get('alternates', [])]
        view['fuel'] = pick(plan.get('fuel', {}), ('landing', 'alternate', 'final_reserve'))
        return {key: value for key, value in view.items() if value not in ({}, [])}
    view = {key: value for key, value in plan.items() if key != 'waypoints'}
    for key in ('origin', 'destination'):
        if key in view:
            view[key] = {k: v for k, v in view[key].items() if k not in ('latitude', 'longitude')}
    view['alternates'] = [{k: v for k, v in item.items() if k not in ('latitude', 'longitude')}
                          for item in view.get('alternates', [])]
    view['waypoints'] = [{k: v for k, v in fix.items() if k not in ('latitude', 'longitude')}
                         for fix in plan.get('waypoints', [])]
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
    if plan and all(item.get('status') in USABLE for item in position) and position[2]['value']:
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


def route_progress(position, fuel, plan: dict) -> dict | None:
    """Locate the aircraft along the planned waypoints; purely geometric, not the active MCDU route."""
    points = [fix for fix in plan.get('waypoints', []) if 'latitude' in fix and 'longitude' in fix]
    origin = plan.get('origin', {})
    if not points:
        return None
    lat, lon = position
    gaps = [distance_nm(lat, lon, fix['latitude'], fix['longitude']) for fix in points]
    closest = min(range(len(points)), key=gaps.__getitem__)
    nxt = closest
    if closest+1 < len(points):
        leg = distance_nm(points[closest]['latitude'], points[closest]['longitude'],
                          points[closest+1]['latitude'], points[closest+1]['longitude'])
        if gaps[closest+1] < leg:
            nxt = closest+1
    along = [gaps[nxt]]
    for previous, current in zip(points[nxt:], points[nxt+1:]):
        along.append(along[-1]+distance_nm(previous['latitude'], previous['longitude'],
                                           current['latitude'], current['longitude']))
    upcoming = []
    for fix, distance in zip(points[nxt:nxt+UPCOMING], along):
        item = pick(fix, ('ident', 'airway', 'stage', 'altitude_ft', 'planned_fuel'))
        item['distance_nm'] = round(distance)
        upcoming.append(item)
    result = {'status': 'derived', 'next_waypoint': points[nxt]['ident'], 'upcoming': upcoming,
              'remaining_along_route_nm': round(along[-1]),
              'method': 'Points de route de l’OFP : point le plus proche de la position observée, puis cumul des '
                        'orthodromies entre points. Route prévue, pas la route active du MCDU.'}
    # Planned fuel at the current position, interpolated between the previous and the next waypoint.
    if fuel is not None and 'planned_fuel' in points[nxt]:
        if nxt > 0:
            start = points[nxt-1]
            start_fuel = start.get('planned_fuel')
        else:
            start, start_fuel = origin, plan.get('fuel', {}).get('takeoff')
        if start_fuel is not None and 'latitude' in start and 'longitude' in start:
            leg = distance_nm(start['latitude'], start['longitude'], points[nxt]['latitude'], points[nxt]['longitude'])
            fraction = 1-min(1, gaps[nxt]/leg) if leg > 0 else 1
            planned = start_fuel+(points[nxt]['planned_fuel']-start_fuel)*fraction
            if plan.get('weight_unit') == 'lb':
                planned *= LB_TO_KG
            result['fuel_vs_plan'] = {
                'observed_kg': round(fuel), 'planned_kg': round(planned), 'difference_kg': round(fuel-planned),
                'method': 'Carburant prévu à bord par l’OFP, interpolé entre les points encadrant la position ; '
                          'différence = observé − prévu.'}
    return result


def derived(fields: dict, plan: dict | None, level: str) -> dict:
    """Values computed from observations, labelled with their method."""
    result = {}
    lat, lon = fields.get('latitude', {}), fields.get('longitude', {})
    if plan is None or lat.get('status') not in USABLE or lon.get('status') not in USABLE:
        return result
    destination = plan.get('destination', {})
    if 'latitude' in destination and 'longitude' in destination:
        result['direct_distance_to_destination'] = {
            'value': round(distance_nm(lat['value'], lon['value'], destination['latitude'], destination['longitude'])),
            'unit': 'NM', 'status': 'derived',
            'method': 'Orthodromie entre la position observée et l’aéroport de destination de l’OFP ; ne suit pas la route.'}
    if level != 'briefing':
        fuel = fields.get('fuel_total', {})
        progress = route_progress((lat['value'], lon['value']),
                                  fuel['value'] if fuel.get('status') in USABLE else None, plan)
        if progress:
            result['route_progress'] = progress
    return result


def build_context(level: str, entries: list[Entry], store: TelemetryStore, plan: dict | None,
                  plan_status: dict, now: float, notes: dict | None = None, network: dict | None = None) -> dict:
    if level not in LIMITS:
        raise ValueError('Niveau d’export inconnu.')
    selected = [entry for entry in entries if level == 'full' or entry.level == 'essential']
    fields = {entry.key: qualify(entry, store, now) for entry in selected}
    # The fuel comparison needs the fuel reading even when it is only exported in full mode.
    fuel_entry = next((entry for entry in entries if entry.key == 'fuel_total'), None)
    if fuel_entry is not None and 'fuel_total' not in fields:
        progress_fields = {**fields, 'fuel_total': qualify(fuel_entry, store, now)}
    else:
        progress_fields = fields
    groups: dict[str, dict] = {}
    unavailable = []
    for entry in selected:
        field = dict(fields[entry.key])
        if level != 'full':
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
    extra = derived(progress_fields, plan, level)
    if extra:
        document['derived'] = extra
    if notes and notes.get('text'):
        document['pilot_notes'] = {'nature': 'declared_by_pilot', 'text': notes['text'],
                                   'updated_utc': notes.get('updated_utc')}
    document['flight_plan'] = None if plan is None else {
        'source': plan_status.get('source'), 'fetched_utc': plan_status.get('fetched_utc'),
        'warnings': plan_status.get('warnings', []), **plan_view(plan, level)}
    if network is not None:
        document['ivao'] = network
    document['checks'] = checks(fields, plan, store)+network_checks(network)
    return limit(document, LIMITS[level])


def network_checks(network: dict | None) -> list[dict]:
    if network is None:
        return []
    degraded = [f'{name} {feed["status"]}' for name, feed in network['feeds'].items() if feed['status'] != 'current']
    return [{'level': 'warning', 'message': 'Flux IVAO non à jour : '+', '.join(degraded)+' (voir ivao.feeds).'}]         if degraded else []


def limit(document: dict, maximum: int) -> dict:
    """Trim optional route details first; flag any truncation explicitly."""
    plan = document.get('flight_plan') or {}
    while len(serialize(document)) > maximum and plan.get('waypoints'):
        plan['waypoints'] = plan['waypoints'][:len(plan['waypoints'])//2]
        plan['waypoints_truncated'] = True
    if len(serialize(document)) > maximum and plan.get('route'):
        plan['route'] = plan['route'][:400]+' …'
        plan['route_truncated'] = True
    if document.get('ivao'):
        from .ivao import trim
        trim(document['ivao'], lambda: len(serialize(document)) > maximum)
    notes = document.get('pilot_notes')
    if len(serialize(document)) > maximum and notes:
        notes['text'] = notes['text'][:1000]+' …'
        notes['truncated'] = True
    return document


def serialize(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(',', ':'))


def chat_text(document: dict) -> str:
    """Text ready to paste into a conversational assistant."""
    return CHAT_HEADERS[document['level']]+'\n\n```json\n'+serialize(document)+'\n```\n'


def group_labels() -> dict:
    return dict(GROUPS)
