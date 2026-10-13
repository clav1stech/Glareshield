"""Timestamped observations and their qualification for export."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Literal

from .catalog import Entry

Origin = Literal['simconnect', 'scenario']


@dataclass(frozen=True)
class Sample:
    value: float | bool | str
    observed_at: float


class TelemetryStore:
    """Holds the latest value of each telemetry entry, never lighting test values."""

    def __init__(self, origin: Origin = 'simconnect', clock=time.time):
        self.origin = origin
        self.clock = clock
        self.connected = False
        self.paused = False
        self.last_message: float | None = None
        self.samples: dict[str, Sample] = {}
        self.errors: dict[str, str] = {}

    def update(self, message: dict) -> None:
        """Apply a simulator worker message; malformed values are discarded."""
        now = self.clock()
        self.connected = bool(message.get('connected'))
        self.paused = bool(message.get('paused'))
        self.last_message = now
        for key, item in (message.get('telemetry') or {}).items():
            try:
                value, observed_at = item
                observed_at = float(observed_at)
            except (TypeError, ValueError):
                continue
            if isinstance(value, bool) or isinstance(value, str):
                pass
            elif isinstance(value, (int, float)) and math.isfinite(value):
                value = float(value)
            else:
                self.errors[key] = 'Valeur invalide'
                continue
            self.samples[key] = Sample(value, min(observed_at, now))
            self.errors.pop(key, None)
        for key, error in (message.get('telemetry_errors') or {}).items():
            self.errors[key] = str(error)[:80]

    def clear(self) -> None:
        self.samples.clear()
        self.errors.clear()
        self.connected = False
        self.paused = False
        self.last_message = None


def convert(entry: Entry, value):
    if entry.kind == 'bool':
        return bool(value) if not isinstance(value, str) else None
    if entry.kind == 'string':
        return value.strip() or None if isinstance(value, str) else None
    if isinstance(value, (bool, str)):
        return None
    if entry.digits is None:
        return value
    rounded = round(value, entry.digits)
    return int(rounded) if entry.digits == 0 else rounded


def qualify(entry: Entry, store: TelemetryStore, now: float | None = None) -> dict:
    """Describe one field with its value, unit, status and age."""
    now = store.clock() if now is None else now
    sample = store.samples.get(entry.key)
    field = {'label': entry.label}
    if sample is None:
        return {**field, 'value': None, 'unit': entry.unit, 'status': 'unavailable',
                'reason': store.errors.get(entry.key) or ('Simulateur déconnecté' if not store.connected
                                                           else 'Aucune donnée reçue')}
    value = convert(entry, sample.value)
    if entry.min_ground_speed_kt is not None:
        speed = store.samples.get('ground_speed')
        if speed is None or not isinstance(speed.value, float) or speed.value < entry.min_ground_speed_kt:
            return {**field, 'value': None, 'unit': entry.unit, 'status': 'unavailable',
                    'reason': f'Sans signification sous {entry.min_ground_speed_kt:g} kt de vitesse sol'}
    age = max(0.0, now-sample.observed_at)
    if value is None:
        return {**field, 'value': None, 'unit': entry.unit, 'status': 'unavailable', 'reason': 'Valeur invalide'}
    fresh = store.connected and age <= entry.max_age_s
    status = ('simulated' if store.origin == 'scenario' else 'observed') if fresh else 'stale'
    result = {**field, 'value': value, 'unit': entry.unit, 'status': status, 'age_s': round(age, 1)}
    if entry.values and isinstance(value, (int, float)) and not isinstance(value, bool):
        meaning = entry.values.get(str(int(value)) if float(value).is_integer() else str(value))
        if meaning:
            result['meaning'] = meaning
    if not fresh:
        result['reason'] = 'Simulateur déconnecté' if not store.connected else 'Mesure périmée'
    return result
