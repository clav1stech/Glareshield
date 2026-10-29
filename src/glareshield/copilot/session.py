"""Durable pilot gestures; no phase algorithm, simulator client or cockpit writes."""
from __future__ import annotations

import hashlib
import json
import shutil
from uuid import uuid4
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..config import atomic_write
from ..model import StrictModel
from .contract import Identifier, PhaseId, Scalar, Text, load_profile

Universe = Literal['simconnect', 'demo']
MAX_BYTES = 8_388_608


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def plan_identity(plan: dict) -> str:
    """OFP request ID is stable across corrections; generation/import dates are not identity."""
    if plan.get('ofp_id'):
        return 'ofp:'+str(plan['ofp_id'])
    return 'flight:'+digest([plan.get('flight'), plan.get('origin', {}).get('icao'),
                            plan.get('destination', {}).get('icao'),
                            plan.get('times', {}).get('scheduled_out_utc')])


class DeclarationInput(StrictModel):
    kind: Literal['clearance', 'selection', 'atis', 'performance', 'event']
    field: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.]{0,79}$')]
    value: Scalar
    unit: Text | None = None
    reference: Text
    occurred_at: float | None = Field(default=None, ge=0)
    context: dict[Identifier, Scalar] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def explicit_context(self):
        required = {
            'clearance': ('type', 'station'),
            'selection': ('stage',),
            'atis': ('airport', 'version'),
            'performance': ('aircraft', 'runway', 'mass', 'configuration', 'weather'),
            'event': ('stage',),
        }[self.kind]
        if not self.field.startswith(self.kind+'.') or any(
                key not in self.context or self.context[key] in ('', None) or (
                    isinstance(self.context[key], str) and not self.context[key].strip()) for key in required):
            raise ValueError('Champ et contexte explicites requis pour cette déclaration.')
        if not self.reference.strip():
            raise ValueError('Une référence explicite est obligatoire.')
        if isinstance(self.value, str) and (not self.value.strip() or len(self.value) > 1000):
            raise ValueError('Valeur déclarée vide ou trop longue.')
        if any(isinstance(value, str) and len(value) > 1000 for value in self.context.values()):
            raise ValueError('Contexte trop long.')
        if self.kind == 'performance' and not self.unit:
            raise ValueError('Unité obligatoire pour une performance.')
        if self.kind == 'performance' and type(self.value) not in (int, float):
            raise ValueError('Valeur numérique obligatoire pour une performance.')
        if self.kind == 'selection' and self.context['stage'] not in ('departure', 'arrival'):
            raise ValueError('Choisir départ ou arrivée.')
        if self.kind == 'clearance' and self.context['type'] not in (
                'departure', 'climb', 'descent', 'approach', 'runway', 'taxi', 'transfer'):
            raise ValueError('Type de clairance inconnu.')
        if self.kind == 'atis':
            import re
            if not re.fullmatch(r'[A-Z]{4}', str(self.context['airport'])):
                raise ValueError('Aérodrome ATIS : quatre lettres OACI.')
        return self


class Declaration(DeclarationInput):
    id: str
    revision: int = Field(ge=1)
    recorded_at: float
    revoked_at: float | None = None
    invalidated_reason: Text | None = None


class Gesture(StrictModel):
    checked: bool
    recorded_at: float
    reference: Text
    reason: Text | None = None


class Progress(StrictModel):
    manual: Gesture | None = None
    detected: Gesture | None = None
    # Persist evidence, but require this process's trusted adapter to reconfirm it.
    detection_epoch: str | None = None


class FlightSession(StrictModel):
    id: str
    universe: Universe
    status: Literal['active', 'ended'] = 'active'
    started_at: float
    ended_at: float | None = None
    end_reason: Text | None = None
    profile_id: str
    profile_revision: int
    plan_key: str | None = None
    plan_hash: str | None = None
    plan_summary: dict = Field(default_factory=dict)
    plan_revision: int = 0
    steps: dict[Identifier, Progress] = Field(default_factory=dict)
    declarations: list[Declaration] = Field(default_factory=list)
    forced_phase: PhaseId | None = None
    reminders: dict[Identifier, Gesture] = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)


class SessionFile(StrictModel):
    schema_version: Literal['glareshield.copilot_session/1'] = 'glareshield.copilot_session/1'
    universe: Universe
    sessions: list[FlightSession] = Field(default_factory=list)

    @model_validator(mode='after')
    def consistent(self):
        if any(s.universe != self.universe for s in self.sessions):
            raise ValueError('Univers mélangés.')
        if len({s.id for s in self.sessions}) != len(self.sessions):
            raise ValueError('Sessions dupliquées.')
        if any(s.status == 'active' for s in self.sessions[:-1]):
            raise ValueError('Session active hors de la dernière position.')
        return self


class SessionService:
    def __init__(self, bridge):
        self.bridge, self.clock = bridge, bridge.clock
        self.directory = bridge.root/'local/copilot'
        self.profile_load = load_profile(bridge.root)
        self.profile = self.profile_load.profile
        self.epoch = uuid4().hex
        self.documents = {}
        self.errors = {}
        for universe in ('simconnect', 'demo'):
            try:
                path = self.path(universe)
                with path.open('rb') as stream:
                    raw = stream.read(MAX_BYTES+1)
                if len(raw) > MAX_BYTES:
                    raise ValueError('Volume dépassé.')
                document = SessionFile.model_validate_json(raw)
                if document.universe != universe:
                    raise ValueError('Univers incorrect.')
                self.documents[universe] = document
            except FileNotFoundError:
                self.documents[universe] = SessionFile(universe=universe)
            except (ValueError, OSError, RecursionError):
                self.documents[universe] = SessionFile(universe=universe)
                self.errors[universe] = 'Suivi illisible ou ancien : fichier conservé ; réinitialisation explicite requise.'

    def path(self, universe):
        local = (self.bridge.root/'local').resolve()
        path = self.directory/f'sessions-{universe}.json'
        if not path.resolve().is_relative_to(local):
            raise ValueError('Le suivi doit rester sous local/.')
        return path

    @property
    def universe(self):
        return 'demo' if self.bridge.scenario else 'simconnect'

    def current_plan(self):
        store = self.bridge.plan
        return store.plan if store.plan and (store.source == 'demo') == (self.universe == 'demo') else None

    def _copy(self):
        if self.universe in self.errors:
            raise ValueError(self.errors[self.universe])
        return self.documents[self.universe].model_copy(deep=True)

    def _save(self, document):
        # Revalidate mutable dictionaries and assignments made by internal adapters too.
        document = SessionFile.model_validate(document.model_dump())
        raw = document.model_dump_json(indent=2)
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError('Volume maximal atteint : sauvegarder les suivis sous local/ avant de poursuivre.')
        atomic_write(self.path(document.universe), raw)
        self.documents[document.universe] = document

    def _new(self):
        plan = self.current_plan()
        return FlightSession(id=uuid4().hex, universe=self.universe, started_at=self.clock(),
                             profile_id=self.profile.id, profile_revision=self.profile.revision,
                             plan_key=plan_identity(plan) if plan else None,
                             plan_hash=digest(plan) if plan else None, plan_summary=self._summary(plan),
                             plan_revision=1 if plan else 0)

    @staticmethod
    def _summary(plan):
        return {key: plan.get(key) for key in ('ofp_id', 'flight', 'origin', 'destination', 'generated_utc')} if plan else {}

    def synchronize(self):
        """An active flight follows its own universe's OFP; plan absence never erases it."""
        document = self.documents[self.universe]
        if self.universe in self.errors or not document.sessions or document.sessions[-1].status != 'active':
            return
        plan = self.current_plan()
        session = document.sessions[-1]
        if not plan or session.plan_hash == digest(plan):
            return
        candidate = self._copy()
        session = candidate.sessions[-1]
        if session.plan_key is not None and session.plan_key != plan_identity(plan):
            session.status, session.ended_at, session.end_reason = 'ended', self.clock(), 'new_plan'
            candidate.sessions.append(self._new())
        else:
            session.plan_key, session.plan_hash = plan_identity(plan), digest(plan)
            session.plan_summary = self._summary(plan)
            session.plan_revision += 1
            session.history.append({'event': 'plan_corrected', 'at': self.clock(), 'revision': session.plan_revision})
            for declaration in session.declarations:
                if declaration.revoked_at is None:
                    declaration.invalidated_reason = 'Plan modifié : confirmer à nouveau le contexte.'
        self._save(candidate)

    def _active(self, candidate):
        if not candidate.sessions or candidate.sessions[-1].status != 'active':
            raise ValueError('Démarrer ou reprendre un suivi avant cette action.')
        session = candidate.sessions[-1]
        if (session.profile_id, session.profile_revision) != (self.profile.id, self.profile.revision):
            raise ValueError('Profil modifié : ancien suivi conservé ; réinitialiser explicitement.')
        return session

    def start(self):
        self.synchronize()
        candidate = self._copy()
        if candidate.sessions and candidate.sessions[-1].status == 'active':
            return self.view()
        if self.universe == 'simconnect':
            store = self.bridge.live
            if not self.bridge.settings.enabled or not store.connected or store.paused or (
                    store.last_message is None or self.clock()-store.last_message > 8):
                raise ValueError('AI Bridge et une connexion SimConnect récente hors pause sont requis.')
        candidate.sessions.append(self._new())
        self._save(candidate)
        return self.view()

    def change(self, operation):
        self.synchronize()
        candidate = self._copy()
        operation(self._active(candidate))
        self._save(candidate)
        return self.view()

    def end(self):
        def apply(session):
            session.status, session.ended_at, session.end_reason = 'ended', self.clock(), 'pilot'
        return self.change(apply)

    def resume(self):
        candidate = self._copy()
        if not candidate.sessions:
            return self.start()
        session = candidate.sessions[-1]
        session.status, session.ended_at, session.end_reason = 'active', None, None
        self._active(candidate)
        self._save(candidate)
        self.synchronize()
        return self.view()

    def reset(self):
        universe = self.universe
        if universe in self.errors:
            path = self.path(universe)
            # Preserve exact bytes of an unknown/corrupt schema before replacing it.
            backup = path.with_name(path.stem+'-preserved-'+uuid4().hex+'.json')
            shutil.copyfile(path, backup)
            candidate = SessionFile(universe=universe)
        else:
            candidate = self._copy()
            if candidate.sessions and candidate.sessions[-1].status == 'active':
                previous = candidate.sessions[-1]
                previous.status, previous.ended_at, previous.end_reason = 'ended', self.clock(), 'reset'
        candidate.sessions.append(self._new())
        self._save(candidate)
        self.errors.pop(universe, None)
        return self.view()

    def set_step(self, step_id, checked):
        if step_id not in {s.id for p in self.profile.phases for g in p.groups for s in g.steps}:
            raise ValueError('Étape inconnue du profil.')
        def apply(session):
            progress = session.steps.setdefault(step_id, Progress())
            progress.manual = Gesture(checked=checked, recorded_at=self.clock(), reference='pilot')
            session.history.append({'event': 'manual_step', 'step': step_id, **progress.manual.model_dump()})
        return self.change(apply)

    def record_detection(self, step_id, checked, reference, universe, reason=None):
        """Trusted adapter hook only; detection algorithms and public detection API are out of scope."""
        step = next((s for p in self.profile.phases for g in p.groups for s in g.steps if s.id == step_id), None)
        if universe != self.universe or not step or step.validation.mode != 'observed':
            raise ValueError('Détection incompatible avec le suivi ou le profil.')
        def apply(session):
            progress = session.steps.setdefault(step_id, Progress())
            progress.detected = Gesture(checked=checked, recorded_at=self.clock(), reference=reference, reason=reason)
            progress.detection_epoch = self.epoch
            session.history.append({'event': 'detected_step', 'step': step_id, **progress.detected.model_dump()})
        return self.change(apply)

    def force_phase(self, phase):
        def apply(session):
            session.forced_phase = phase
            session.history.append({'event': 'phase', 'phase': phase, 'at': self.clock()})
        return self.change(apply)

    def declare(self, payload):
        if payload.occurred_at is not None and payload.occurred_at > self.clock()+60:
            raise ValueError('L’heure déclarée ne peut pas être dans le futur.')
        def key(declaration):
            scope = declaration.context.get('stage') if declaration.kind == 'selection' else (
                declaration.context.get('airport') if declaration.kind == 'atis' else None)
            return declaration.field, scope
        def apply(session):
            previous = [d for d in session.declarations if key(d) == key(payload)]
            now = self.clock()
            for declaration in session.declarations:
                if key(declaration) == key(payload) and declaration.revoked_at is None:
                    declaration.revoked_at = now
                elif declaration.kind == 'performance' and (payload.kind in ('selection', 'atis', 'clearance') or (
                        payload.kind == 'performance' and payload.context != declaration.context)):
                    declaration.invalidated_reason = 'Contexte modifié : confirmer à nouveau les performances.'
            data = payload.model_dump()
            if data['occurred_at'] is None:
                data['occurred_at'] = now
            session.declarations.append(Declaration(**data, id=uuid4().hex,
                                                   revision=len(previous)+1, recorded_at=now))
        return self.change(apply)

    def revoke(self, declaration_id):
        def apply(session):
            declaration = next((d for d in session.declarations if d.id == declaration_id), None)
            if declaration is None:
                raise ValueError('Déclaration inconnue.')
            declaration.revoked_at = self.clock()
        return self.change(apply)

    def remember(self, key, reference):
        def apply(session):
            session.reminders[key] = Gesture(checked=True, recorded_at=self.clock(), reference=reference)
        return self.change(apply)

    def view(self):
        warnings = list(self.profile_load.errors)
        try:
            self.synchronize()
        except (OSError, ValueError):
            warnings.append('Enregistrement du plan impossible ; dernier suivi conservé. Réessayer avant toute action.')
        if self.universe in self.errors:
            warnings.append(self.errors[self.universe])
        document = self.documents[self.universe]
        session = document.sessions[-1] if document.sessions else None
        if session and (session.profile_id, session.profile_revision) != (self.profile.id, self.profile.revision):
            warnings.append('Profil modifié : progression conservée, réinitialisation explicite requise.')
        if self.bridge.plan.plan and self.current_plan() is None:
            warnings.append('Plan de l’autre univers exclu de ce suivi.')
        if session and session.plan_revision > 1:
            warnings.append('OFP corrigé : cases conservées ; déclarations à vérifier.')
        if session and session.end_reason == 'new_plan':
            warnings.append('Nouveau plan : un nouveau suivi a été ouvert.')
        if len(document.sessions) > 1 and document.sessions[-2].end_reason == 'new_plan':
            warnings.append('Nouveau plan : suivi précédent archivé, nouvelles cases vides.')
        store = self.bridge.store()
        fresh = store.connected and not store.paused and store.last_message is not None and self.clock()-store.last_message <= 8
        groups = []
        for phase in self.profile.phases:
            for group in phase.groups:
                steps = []
                for step in group.steps:
                    progress = session.steps.get(step.id, Progress()) if session else Progress()
                    manual, detected = progress.manual, progress.detected
                    current = bool(detected is not None and progress.detection_epoch == self.epoch
                                   and fresh and self.clock()-detected.recorded_at <= 8)
                    effective = manual if manual is not None else detected if current else None
                    steps.append({'id': step.id, 'label': step.label,
                                  'checked': effective.checked if effective else False,
                                  'provenance': 'manual' if manual else 'detected' if current else 'pending',
                                  'manual': manual.model_dump() if manual else None,
                                  'detected': detected.model_dump() if detected else None,
                                  'detection_current': current,
                                  'conflict': bool(manual and current and manual.checked != detected.checked)})
                groups.append({'phase': phase.id, 'phase_label': phase.label, 'label': group.label, 'steps': steps})
        return {'universe': self.universe, 'session': session.model_dump() if session else None,
                'warnings': warnings, 'storage_blocked': self.universe in self.errors,
                'archived_count': max(0, len(document.sessions)-1), 'groups': groups,
                'phases': [{'id': p.id, 'label': p.label} for p in self.profile.phases]}
