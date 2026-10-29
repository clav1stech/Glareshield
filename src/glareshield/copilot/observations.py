"""Read-only, fail-closed procedure observations from the AI Bridge store."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator

from ..model import StrictModel

Signal = Literal['gear_handle_down', 'parking_brake', 'baro_std', 'flaps_handle_index']


class ObservationBinding(StrictModel):
    """Local confirmation of one exact source and its meaning for one aircraft."""
    signal: Signal
    key: str = Field(pattern=r'^[a-z][a-z0-9_]{0,47}$')
    variable: str = Field(min_length=1, max_length=100)
    origin: Literal['simvar', 'lvar']
    aircraft_title: str = Field(min_length=1, max_length=256)
    values: dict[str, bool | int] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def meanings(self):
        for raw, meaning in self.values.items():
            if not math.isfinite(float(raw)):
                raise ValueError('Valeur source finie requise.')
            if self.signal == 'flaps_handle_index':
                if type(meaning) is not int or not 0 <= meaning <= 5:
                    raise ValueError('Cran entier entre 0 et 5 requis.')
            elif type(meaning) is not bool:
                raise ValueError('Sens booléen requis.')
        if len({float(raw) for raw in self.values}) != len(self.values):
            raise ValueError('Valeurs source équivalentes dupliquées.')
        return self


class Observation(StrictModel):
    checked: bool | None = None
    status: Literal['confirmed', 'contradicted', 'unavailable', 'out_of_phase']
    source: str
    reference: str
    reason: str
    observed_at: float | None = None
    origin: Literal['simconnect', 'scenario']

    def signature(self):
        return self.model_dump(exclude={'observed_at'})


def evaluate(bridge, profile, phase, universe):
    """Only the telemetry store is read; no lighting state, network or cockpit API."""
    store = bridge.store()
    now = bridge.clock()
    entries = {entry.key: entry for entry in bridge.entries()}
    expected_origin = 'scenario' if universe == 'demo' else 'simconnect'

    def sample(key, cap=8):
        entry, value = entries.get(key), store.samples.get(key)
        if not entry or not value or key in store.errors:
            return None
        if not math.isfinite(value.observed_at) or not 0 <= now-value.observed_at <= min(cap, entry.max_age_s):
            return None
        return value

    usable = (store.origin == expected_origin and store.connected and not store.paused
              and store.last_message is not None and 0 <= now-store.last_message <= 8
              and (universe == 'demo' or bridge.settings.enabled))
    title = sample('title', 120) if usable else None
    results = {}
    for section in profile.phases:
        for group in section.groups:
            for step in group.steps:
                rule = step.validation.automatic
                if rule is None:
                    continue
                result = Observation(status='unavailable', source=expected_origin,
                    reference=rule.signal, origin=expected_origin,
                    reason='Source absente, périmée, en pause ou non validée pour cet appareil.')
                if section.id != phase:
                    result.status = 'out_of_phase'
                    result.reason = 'Étape hors de la phase courante ; preuve historique conservée.'
                    results[step.id] = result
                    continue
                if step.trigger.hold_s or not any(all(
                        p.source == 'phase_'+section.id and p.op == 'eq' and p.value is True
                        for p in clause) for clause in step.trigger.any_of):
                    result.reason = 'Déclencheur supplémentaire non observable ; confirmation manuelle requise.'
                    results[step.id] = result
                    continue
                key, mapping = None, None
                if universe == 'demo' and rule.signal in ('gear_handle_down', 'parking_brake', 'flaps_handle_index'):
                    key = rule.signal
                    mapping = {float(i): i for i in range(6)} if rule.signal == 'flaps_handle_index' else {0.: False, 1.: True}
                elif title and isinstance(title.value, str):
                    bindings = [b for b in bridge.settings.copilot_bindings
                                if b.signal == rule.signal and b.aircraft_title == title.value]
                    if len(bindings) == 1:
                        binding = bindings[0]
                        entry = entries.get(binding.key)
                        # These standard signals are known not to follow the Fenix cockpit.
                        excluded = binding.origin == 'simvar' and binding.key in {
                            'flaps_handle_index', 'spoilers_handle', 'spoilers_armed'}
                        if entry and entry.validated and not excluded and (
                                entry.origin == binding.origin and entry.variable == binding.variable):
                            key = binding.key
                            mapping = {float(raw): meaning for raw, meaning in binding.values.items()}
                value = sample(key) if usable and key else None
                if universe == 'simconnect' and value and title and value.observed_at < title.observed_at:
                    value = None
                if value and type(value.value) in (bool, int, float) and math.isfinite(value.value):
                    meaning = mapping.get(float(value.value))
                    if meaning is not None:
                        result.checked = type(meaning) is type(rule.equals) and meaning == rule.equals
                        result.status = 'confirmed' if result.checked else 'contradicted'
                        entry = entries[key]
                        result.reference = entry.origin+':'+entry.variable
                        result.observed_at = value.observed_at
                        result.reason = ('Critère mesuré confirmé.' if result.checked else 'Le signal mesuré ne satisfait plus le critère.')
                results[step.id] = result
    return results
