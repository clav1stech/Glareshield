"""Presentation adapter for Vol. No trigger evaluation or cockpit writes."""
import math
from ..aibridge.context import derived, LB_TO_KG
from ..aibridge.telemetry import qualify


def path_value(data, path):
    for part in path.split('.'):
        if part == 'primary' and isinstance(data, list):
            data = data[0] if data else None
        else:
            data = data.get(part) if isinstance(data, dict) else None
    return data


def pilot_number(text):
    """Typed digits become a number for display; anything else stays as typed (04R, FL120)."""
    try:
        number = float(text.replace(' ', '').replace(',', '.'))
    except ValueError:
        return text
    if not math.isfinite(number):
        return text
    return int(number) if number.is_integer() else number


def flight_view(service, session, phase, network):
    bridge, profile, now = service.bridge, service.profile, service.clock()
    store, plan = bridge.store(), service.current_plan()
    fields = {}
    for entry in bridge.entries():
        if entry.origin != 'simvar':
            continue
        field = qualify(entry, store, now)
        if entry.key in store.errors:
            field = {**field, 'value': None, 'status': 'unavailable'}
        fields[entry.key] = {**field, 'source': entry.variable, 'nature': 'observed'}
    declarations = [d for d in (session.declarations if session else [])
                    if d.revoked_at is None and d.invalidated_reason is None]
    plan_status = bridge.plan.describe(bridge.settings.ofp_max_age_h)
    plan_age = plan_status.get('fetched_age_min') if plan else None

    def resolve(source):
        value, reference, age, status = None, source.path, None, 'unavailable'
        path = source.path
        if path.startswith('flight_plan.') and plan:
            value = path_value(plan, path.removeprefix('flight_plan.'))
            if source.unit == 'kg' and plan.get('weight_unit') == 'lb' and type(value) in (int, float):
                value = round(value * LB_TO_KG)
            reference = 'OFP prévu · ' + str(plan.get('ofp_id') or 'sans identifiant') + ' · ' + path
            age = plan_age * 60 if plan_age is not None else None
            status = 'stale' if plan_status.get('generated_age_h', 0) > bridge.settings.ofp_max_age_h else 'available'
        elif path.startswith('pilot.'):
            parts = path.split('.')[1:]
            stage = parts[0] if parts[0] in ('departure', 'arrival') else None
            if stage:
                field = 'selection.' + parts[-1]
            else:
                field = '.'.join(parts)
            aliases = {'clearance.cleared_altitude': 'clearance.altitude',
                       'performance.thrust_reduction': 'performance.thr_red',
                       'performance.acceleration': 'performance.acc', 'radio.station': 'station.callsign'}
            field = aliases.get(field, field)
            matches = [d for d in declarations if d.field == field and
                       (not stage or d.context.get('stage') == stage)]
            if field.startswith('radio.'):
                phases = ('preflight', 'departure', 'climb') if (phase or {}).get('effective', {}).get('value') in (
                    'preflight', 'departure', 'climb') else ('cruise', 'descent', 'arrival')
                matches = [d for d in matches if d.context.get('stage') in phases]
            if field.startswith('atis.'):
                airport = (plan or {}).get('destination' if (phase or {}).get('effective', {}).get('value') in
                          ('cruise', 'descent', 'arrival') else 'origin', {}).get('icao')
                matches = [d for d in matches if d.context.get('airport') == airport]
            if matches:
                d = matches[-1]
                if d.unit == source.unit:
                    value, reference, age, status = d.value, d.reference, max(0, now-d.recorded_at), 'available'
                    if source.kind == 'number' and isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            value = None
        elif path.startswith('publications.'):
            _, stage, key = path.split('.')
            airport = (plan or {}).get('origin' if stage == 'departure' else 'destination', {}).get('icao')
            weather = next((w for w in network['weather'] if w['icao'] == airport), {})
            bulletin = weather.get('metar', {})
            reading = bulletin.get('values', {}).get(key, {})
            if reading.get('status') in ('available', 'stale'):
                value, status = reading.get('value'), reading['status']
                reference = str(bulletin.get('raw') or path)
                age = bulletin.get('provenance', {}).get('age_s')
        elif path.startswith('telemetry.'):
            field = fields.get(path.split('.')[-1], {})
            value, status, age = field.get('value'), field.get('status', 'unavailable'), field.get('age_s')
        valid = (type(value) in (int, float) if source.kind == 'number' else
                 type(value) is bool if source.kind == 'bool' else isinstance(value, str) and bool(value.strip()))
        if source.kind == 'number' and valid:
            valid = math.isfinite(value)
        if not valid:
            value, status = None, 'unavailable'
        if value is not None and source.max_age_s and (age is None or age > source.max_age_s):
            status = 'stale'
        return {'value': value, 'unit': source.unit, 'source': path, 'reference': reference,
                'nature': source.nature, 'status': status, 'age_s': age}

    values = {}
    for key, expected in profile.values.items():
        choices = [resolve(profile.sources[s]) for s in expected.sources]
        chosen = next((v for v in choices if v['value'] is not None and v['status'] != 'stale'), None)
        if chosen is None:
            chosen = next((v for v in choices if v['value'] is not None), None)
        if chosen is None and choices:
            chosen = choices[0]
        if chosen is None:
            chosen = {'value': expected.literal, 'unit': expected.unit, 'nature': 'procedure',
                      'status': 'available' if expected.literal is not None else 'unavailable',
                      'source': profile.procedure_reference if expected.literal is not None else
                                ' / '.join(profile.sources[s].path for s in expected.sources) or 'Procédure',
                      'reference': profile.procedure_reference, 'age_s': None}
        typed = session.pilot_values.get(key) if session else None
        if typed is not None and expected.literal is None:
            # Codes such as a squawk have no unit and keep their leading zeros.
            chosen = {'value': pilot_number(typed.value) if expected.unit else typed.value, 'unit': expected.unit, 'source': 'pilot.value',
                      'reference': 'Saisie pilote', 'nature': 'declared', 'status': 'available',
                      'age_s': max(0, now-typed.recorded_at)}
        values[key] = {**chosen, 'label': expected.label, 'placeholder': expected.placeholder}
    usable = fields if store.connected and not store.paused else {}
    return {'values': values, 'telemetry': fields, 'derived': derived(usable, plan, 'full'),
            'plan': plan, 'plan_age_min': plan_age, 'utc': now, 'connected': store.connected,
            'plan_current': bool(plan and plan_status.get('generated_age_h') is not None
                                 and 0 <= plan_status['generated_age_h'] <= bridge.settings.ofp_max_age_h),
            'paused': store.paused, 'stale': store.last_message is None or now-store.last_message > 8}
