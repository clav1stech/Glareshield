"""Versioned procedure data, validated without a simulator, network or UI.

This module deliberately does not evaluate triggers, resolve sources or check steps.
Those operations belong to the flight engine, not to the renderer or profile loader.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path
from string import Formatter
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from ..model import StrictModel

Identifier = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')]
Text = Annotated[str, Field(min_length=1, max_length=1000)]
Scalar = str | bool | int | float
Nature = Literal['planned', 'declared', 'published', 'observed', 'calculated']
PhaseId = Literal['preflight', 'departure', 'climb', 'cruise', 'descent', 'arrival']
PHASE_IDS = ('preflight', 'departure', 'climb', 'cruise', 'descent', 'arrival')
MAX_PROFILE_BYTES = 1_048_576


class Source(StrictModel):
    """Adapter path, not executable code; units describe the normalized value."""
    path: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.]{0,159}$')]
    nature: Nature
    kind: Literal['number', 'bool', 'string']
    unit: str | None
    max_age_s: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def observed_freshness(self):
        if self.nature == 'observed' and self.max_age_s is None:
            raise ValueError('Une source observée exige un délai de fraîcheur.')
        return self


class ExpectedValue(StrictModel):
    label: Text
    unit: str | None
    placeholder: Annotated[str, Field(pattern=r'^<[^<>\r\n]{1,80}>$')]
    purpose: Literal['reference', 'clearance', 'performance', 'procedure'] = 'reference'
    sources: list[Identifier] = Field(default_factory=list, max_length=12)
    literal: Scalar | None = None

    @model_validator(mode='after')
    def one_kind(self):
        if self.literal is not None and (self.sources or self.purpose != 'procedure'):
            raise ValueError('Une constante est réservée aux réponses de procédure sans source dynamique.')
        return self


class Predicate(StrictModel):
    source: Identifier
    op: Literal['eq', 'lt', 'lte', 'gt', 'gte']
    value: Scalar


class Trigger(StrictModel):
    label: Text
    # OR of nonempty AND clauses. No Python, JavaScript, expression or template execution.
    any_of: list[Annotated[list[Predicate], Field(min_length=1, max_length=12)]] = Field(
        min_length=1, max_length=12)
    hold_s: float = Field(default=0, ge=0, le=120)


class AutoValidation(StrictModel):
    # Only these semantic signals may be bound by the trusted telemetry adapter.
    # A button lamp is intentionally absent: it cannot confirm FMA arming/capture.
    signal: Literal['gear_handle_down', 'parking_brake', 'baro_std', 'flaps_handle_index']
    equals: bool | int

    @model_validator(mode='after')
    def signal_type(self):
        if self.signal == 'flaps_handle_index':
            if type(self.equals) is not int or not 0 <= self.equals <= 5:
                raise ValueError('Un cran de volets entier entre 0 et 5 est attendu.')
        elif type(self.equals) is not bool:
            raise ValueError('Une position booléenne est attendue pour ce signal.')
        return self


class Validation(StrictModel):
    mode: Literal['manual', 'observed'] = 'manual'
    automatic: AutoValidation | None = None

    @model_validator(mode='after')
    def automatic_required(self):
        if (self.mode == 'observed') != (self.automatic is not None):
            raise ValueError('Une validation observée exige un signal ; une validation manuelle en interdit un.')
        return self


class Step(StrictModel):
    id: Identifier
    label: Text
    expected: list[Identifier] = Field(min_length=1, max_length=24)
    priority: int = Field(ge=0, le=100)
    trigger: Trigger
    validation: Validation = Field(default_factory=Validation)


class Group(StrictModel):
    id: Identifier
    kind: Literal['mcdu', 'fcu', 'checklist']
    label: Text
    steps: list[Step] = Field(min_length=1, max_length=100)


class Voice(StrictModel):
    pilot: Text
    readback: Text


class Radio(StrictModel):
    id: Identifier
    trigger: Trigger
    priority: int = Field(ge=0, le=100)
    station_roles: list[Literal['DEL', 'GND', 'TWR', 'DEP', 'APP', 'CTR']] = Field(min_length=1)
    voice_fr: Voice
    voice_en: Voice
    unicom_en: Text | None = None


class Phase(StrictModel):
    id: PhaseId
    label: Text
    trigger: Trigger
    groups: list[Group] = Field(min_length=1, max_length=12)
    radio: list[Radio] = Field(default_factory=list, max_length=30)


class Profile(StrictModel):
    schema_version: Literal['glareshield.copilot_profile/1']
    id: Identifier
    revision: int = Field(ge=1)
    aircraft: Text
    scope: Literal['simulation_only']
    procedure_reference: Text
    sources: dict[Identifier, Source] = Field(min_length=1, max_length=300)
    values: dict[Identifier, ExpectedValue] = Field(min_length=1, max_length=300)
    phases: list[Phase] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def references(self):
        if tuple(phase.id for phase in self.phases) != PHASE_IDS:
            raise ValueError('Les six phases doivent être présentes dans l’ordre contractuel.')
        identifiers = [self.id]
        for value in self.values.values():
            if len(value.sources) != len(set(value.sources)):
                raise ValueError('Sources de valeur dupliquées.')
            for key in value.sources:
                source = self.sources.get(key)
                if source is None or source.unit != value.unit:
                    raise ValueError('Source inconnue ou unité incompatible dans une valeur attendue.')
                if value.purpose == 'clearance' and not (
                    source.nature == 'declared' and source.path.startswith('pilot.clearance.')
                ):
                    raise ValueError('Une clairance exige une déclaration structurée du pilote.')
                if value.purpose == 'performance' and not (
                    source.nature == 'declared' and source.path.startswith('pilot.performance.')
                ):
                    raise ValueError('Une performance exige une saisie manuelle sourcée.')
        for phase in self.phases:
            identifiers.append(phase.id)
            triggers = [phase.trigger]
            for group in phase.groups:
                identifiers.append(group.id)
                for step in group.steps:
                    identifiers.append(step.id)
                    triggers.append(step.trigger)
                    if any(key not in self.values for key in step.expected):
                        raise ValueError('Valeur attendue inconnue dans une étape.')
            for radio in phase.radio:
                identifiers.append(radio.id)
                triggers.append(radio.trigger)
                for template in (radio.voice_fr.pilot, radio.voice_fr.readback,
                                 radio.voice_en.pilot, radio.voice_en.readback, radio.unicom_en):
                    if template is None:
                        continue
                    for _, key, spec, conversion in Formatter().parse(template):
                        if key is not None and (key not in self.values or spec or conversion):
                            raise ValueError('Paramètre radio inconnu ou format de gabarit interdit.')
            for trigger in triggers:
                for clause in trigger.any_of:
                    for predicate in clause:
                        source = self.sources.get(predicate.source)
                        if source is None:
                            raise ValueError('Source de déclencheur inconnue.')
                        expected_types = {'number': (int, float), 'bool': (bool,), 'string': (str,)}
                        if type(predicate.value) not in expected_types[source.kind]:
                            raise ValueError('Type du seuil incompatible avec la source du déclencheur.')
                        if predicate.op != 'eq' and type(predicate.value) not in (int, float):
                            raise ValueError('Une comparaison ordonnée exige un seuil numérique.')
        if len(identifiers) != len(set(identifiers)):
            raise ValueError('Identifiants de profil, phase, groupe, étape ou radio dupliqués.')
        return self


class QualifiedValue(StrictModel):
    """Copilot envelope only; existing flight_context/3 fields remain unchanged."""
    value: Scalar | None
    unit: str | None
    nature: Nature
    status: Literal['available', 'observed', 'simulated', 'derived', 'stale', 'unavailable']
    source: Text
    reference: Text
    age_s: float | None = Field(ge=0)
    max_age_s: float | None = Field(gt=0)
    verification: Literal['validated_locally', 'unverified', 'not_applicable']
    method: Text | None = None
    inputs: list[Text] = Field(default_factory=list, max_length=24)

    @model_validator(mode='after')
    def qualification(self):
        if (self.status == 'unavailable') != (self.value is None):
            raise ValueError('Une valeur inconnue est null et unavailable, jamais zéro.')
        if self.status != 'unavailable' and self.age_s is None:
            raise ValueError('Toute valeur disponible conserve son âge.')
        if self.nature == 'observed' and self.value is not None and self.max_age_s is None:
            raise ValueError('Une observation exige un délai de fraîcheur.')
        if self.nature == 'calculated' and (not self.method or not self.inputs):
            raise ValueError('Un calcul conserve sa méthode et ses entrées.')
        if self.status == 'derived' and self.nature != 'calculated':
            raise ValueError('derived est réservé aux calculs.')
        if self.nature == 'calculated' and self.status not in ('derived', 'stale', 'unavailable'):
            raise ValueError('Un calcul disponible doit être étiqueté derived.')
        if self.status in ('observed', 'simulated') and self.nature != 'observed':
            raise ValueError('Une observation reste distincte du plan et des déclarations.')
        if self.nature == 'observed' and self.status == 'available':
            raise ValueError('Une observation précise observed ou simulated.')
        if self.age_s is not None and self.max_age_s is not None and self.age_s > self.max_age_s:
            if self.status not in ('stale', 'unavailable'):
                raise ValueError('Une valeur trop ancienne doit être marquée stale.')
        return self


@dataclass(frozen=True)
class ProfileLoad:
    profile: Profile
    origin: Literal['builtin', 'custom', 'last_valid']
    errors: tuple[str, ...] = ()


def builtin_profile() -> Profile:
    return Profile.model_validate_json(files(__package__).joinpath('a320.json').read_text(encoding='utf-8'))


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Clé JSON dupliquée.')
        result[key] = value
    return result


def load_profile(root: Path, previous: Profile | None = None) -> ProfileLoad:
    """Atomic full replacement from root/local/copilot/profile.json; never writes.

    The caller supplies the installation root (a distinct temporary root in tests).
    Diagnostics contain no user values and must remain in private application state.
    """
    local = (root/'local').resolve()
    path = local/'copilot/profile.json'
    fallback = previous if previous is not None else builtin_profile()
    origin = 'last_valid' if previous is not None else 'builtin'
    try:
        if not path.resolve().is_relative_to(local):
            raise ValueError('Chemin privé invalide.')
        with path.open('rb') as stream:
            data = stream.read(MAX_PROFILE_BYTES+1)
        if len(data) > MAX_PROFILE_BYTES:
            raise ValueError('Taille maximale du profil dépassée.')
        profile = Profile.model_validate(json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique_keys))
        return ProfileLoad(profile, 'custom')
    except FileNotFoundError:
        return ProfileLoad(builtin_profile(), 'builtin')
    except (OSError, ValueError, RecursionError) as error:
        if isinstance(error, ValidationError):
            # Keep model field locations but mask private dictionary keys and all input values.
            public_fields = set().union(*(model.model_fields for model in (
                Profile, Phase, Group, Step, Radio, Voice, Trigger, Predicate,
                Validation, AutoValidation, ExpectedValue, Source)))
            errors = tuple('Personnalisation invalide ('+('.'.join(
                str(part) if isinstance(part, int) or part in public_fields else '<clé>'
                for part in item['loc']) or 'profil')+f') : {item["type"]}.'
                for item in error.errors(include_input=False, include_context=False)[:10])
        else:
            errors = ('Personnalisation illisible, trop volumineuse ou JSON invalide.',)
        return ProfileLoad(fallback, origin, errors)
