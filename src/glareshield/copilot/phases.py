"""Read-only flight stage detection: where the aircraft is, never what the pilot did.

Thirteen stages refine the six contractual phases. Each stage only lists the
transitions that make sense from it, held for a few seconds to ignore noise.
Missing inputs simply prevent the transitions that need them; a pilot
correction re-anchors the automatic tracking, which then continues from there.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from pydantic import Field, model_validator

from ..aibridge.context import distance_nm
from ..model import StrictModel
from .contract import PHASE_IDS, PhaseId

StageId = Literal['parked', 'pushback', 'taxi_out', 'takeoff', 'climb', 'cruise', 'descent',
                  'approach', 'final', 'go_around', 'rollout', 'taxi_in', 'parked_in']

# id, phase, label, what the tracker waits for next
STAGES = (
    ('parked', 'preflight', 'Au poste', 'Repoussage, mise en route ou roulage'),
    ('pushback', 'preflight', 'Repoussage · mise en route', 'Roulage au-delà de 6 kt'),
    ('taxi_out', 'departure', 'Roulage', 'Décollage : 40 kt de vitesse sol'),
    ('takeoff', 'departure', 'Décollage', 'Montée au-dessus de 1 500 ft sol'),
    ('climb', 'climb', 'Montée', 'Croisière : palier stable près du niveau prévu'),
    ('cruise', 'cruise', 'Croisière', 'Descente : vario sous −500 ft/min'),
    ('descent', 'descent', 'Descente', 'Approche : 30 NM de la destination ou sous 3 000 ft sol'),
    ('approach', 'arrival', 'Approche', 'Finale sous 1 500 ft sol'),
    ('final', 'arrival', 'Finale', 'Toucher des roues'),
    ('go_around', 'arrival', 'Remise des gaz', 'Nouvelle approche en descente'),
    ('rollout', 'arrival', 'Atterrissage', 'Piste dégagée sous 30 kt'),
    ('taxi_in', 'arrival', 'Roulage', 'Arrêt au poste'),
    ('parked_in', 'arrival', 'Au poste', None),
)
STAGE_IDS = tuple(stage[0] for stage in STAGES)
STAGE_PHASE = {stage[0]: stage[1] for stage in STAGES}
STAGE_LABEL = {stage[0]: stage[2] for stage in STAGES}
STAGE_NEXT = {stage[0]: stage[3] for stage in STAGES}
# Stage chosen when the pilot corrects the phase.
PHASE_ENTRY = {'preflight': 'parked', 'departure': 'taxi_out', 'climb': 'climb', 'cruise': 'cruise',
               'descent': 'descent', 'arrival': 'approach'}
GROUND_STAGES = ('parked', 'pushback', 'taxi_out', 'rollout', 'taxi_in', 'parked_in')
# Older consumers (network, radio wording) still read the coarse substate.
SUBSTATE = {'pushback': 'parking', 'parked': 'parking', 'parked_in': 'parking', 'taxi_out': 'taxi',
            'taxi_in': 'taxi', 'takeoff': 'takeoff', 'approach': 'approach', 'final': 'approach',
            'go_around': 'go_around', 'rollout': 'landing'}


@dataclass(frozen=True)
class PhaseThresholds:
    max_age_s: float = 8
    creep_kt: float = 1
    taxi_kt: float = 6
    takeoff_kt: float = 40
    reject_kt: float = 30
    vacate_kt: float = 30
    initial_climb_agl_ft: float = 1500
    level_fpm: float = 300
    descent_fpm: float = 500
    go_around_fpm: float = 500
    descent_drop_ft: float = 3000
    cruise_margin_ft: float = 4000
    cruise_floor_ft: float = 20000
    approach_nm: float = 30
    approach_agl_ft: float = 8000
    approach_blind_agl_ft: float = 3000
    final_agl_ft: float = 1500
    bootstrap_s: float = 3
    pushback_s: float = 3
    taxi_s: float = 5
    takeoff_s: float = 2
    climb_s: float = 3
    cruise_s: float = 60
    recruise_s: float = 120
    descent_s: float = 20
    approach_s: float = 5
    final_s: float = 2
    go_around_s: float = 5
    touchdown_s: float = 2
    parked_s: float = 20


class PhaseState(StrictModel):
    stage: StageId | None = None
    phase: PhaseId = 'preflight'
    airborne_seen: bool = False
    peak_ft: float | None = None
    changed_at: float | None = None
    manual: bool = False
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def legacy(cls, data):
        """Sessions written by 1.2.x stored a coarse phase without stage."""
        if not isinstance(data, dict) or 'stage' in data or 'confirmed' not in data:
            return data
        data = dict(data)
        confirmed = data.pop('confirmed')
        data.pop('cruise_seen', None)
        substate = data.pop('substate', None)
        phase = data.get('phase', 'preflight')
        if confirmed and phase in PHASE_ENTRY:
            data['stage'] = 'parked_in' if phase == 'arrival' and substate == 'parking' else PHASE_ENTRY[phase]
        return data


def number(fields, key, unit, limit):
    field = fields.get(key) or {}
    value, age = field.get('value'), field.get('age_s')
    if (field.get('status') not in ('observed', 'simulated') or type(value) not in (int, float)
            or isinstance(value, bool) or not math.isfinite(value) or field.get('unit') != unit
            or age is None or not 0 <= age <= limit):
        return None
    return float(value)


def flag(fields, key, limit):
    field = fields.get(key) or {}
    age = field.get('age_s')
    if (field.get('status') not in ('observed', 'simulated') or type(field.get('value')) is not bool
            or age is None or not 0 <= age <= limit):
        return None
    return field['value']


def read_sample(fields, plan, limit=8):
    """Fresh, typed measurements only; anything else is None."""
    altitude = number(fields, 'altitude_indicated', 'ft', limit)
    if altitude is None:
        altitude = number(fields, 'altitude_msl', 'ft', limit)
    engines = [flag(fields, key, 20) for key in ('engine_1_running', 'engine_2_running')]
    sample = {'ground': flag(fields, 'on_ground', limit), 'gs': number(fields, 'ground_speed', 'kt', limit),
              'vs': number(fields, 'vertical_speed', 'ft/min', limit), 'alt': altitude,
              'agl': number(fields, 'altitude_agl', 'ft', limit),
              'engines': True if True in engines else False if engines == [False, False] else None,
              'distance': None}
    lat, lon = number(fields, 'latitude', 'deg', limit), number(fields, 'longitude', 'deg', limit)
    destination = (plan or {}).get('destination') or {}
    if (lat is not None and lon is not None and type(destination.get('latitude')) in (int, float)
            and type(destination.get('longitude')) in (int, float)):
        sample['distance'] = distance_nm(lat, lon, destination['latitude'], destination['longitude'])
    return sample


def cruise_floor(plan, limits):
    planned = ((plan or {}).get('cruise') or {}).get('initial_altitude_ft')
    if type(planned) in (int, float) and math.isfinite(planned) and planned > 0:
        return max(planned-limits.cruise_margin_ft, min(planned, 5000))
    return limits.cruise_floor_ft


class PhaseEngine:
    """Durable stage, in-memory hold timers. A data gap resets the timers only."""

    def __init__(self, thresholds: PhaseThresholds | None = None):
        self.limits = thresholds or PhaseThresholds()
        self.reset()

    def reset(self):
        self.holds = {}
        self.last_at = None

    def held(self, key, condition, duration, now):
        if not condition:
            self.holds.pop(key, None)
            return False
        self.holds.setdefault(key, now)
        return now-self.holds[key] >= duration

    def bootstrap(self, s, floor):
        """First placement, from the current measurements alone."""
        L = self.limits
        ground, gs, vs, alt, agl, distance = s['ground'], s['gs'], s['vs'], s['alt'], s['agl'], s['distance']
        if ground is True and gs is not None:
            if gs >= L.takeoff_kt:
                return 'takeoff'
            if gs > L.taxi_kt:
                return 'taxi_out'
            return 'pushback' if gs >= L.creep_kt or s['engines'] else 'parked'
        if ground is not False or vs is None:
            return None
        if agl is not None and agl < L.initial_climb_agl_ft and vs > L.level_fpm and (
                distance is None or distance > L.approach_nm):
            return 'takeoff'
        if distance is not None and distance <= L.approach_nm and agl is not None and agl <= L.approach_agl_ft:
            return 'final' if agl <= L.final_agl_ft else 'approach'
        if vs > L.level_fpm:
            return 'climb'
        if vs < -L.descent_fpm:
            return 'descent'
        return 'cruise' if alt is not None and alt >= floor else 'climb'

    def transitions(self, state, s, floor):
        """(target, condition, hold, evidence) allowed from the current stage."""
        L = self.limits
        stage, ground, gs, vs, alt, agl, distance = (state.stage, s['ground'], s['gs'], s['vs'],
                                                    s['alt'], s['agl'], s['distance'])
        on_ground, airborne = ground is True, ground is False
        level = vs is not None and abs(vs) <= L.level_fpm
        result = []
        if stage == 'parked':
            result.append(('pushback', on_ground and (gs is not None and gs >= L.creep_kt or s['engines'] is True),
                           L.pushback_s, 'Mouvement lent ou moteur en marche au poste.'))
        if stage in ('parked', 'pushback'):
            result.append(('taxi_out', on_ground and gs is not None and gs > L.taxi_kt, L.taxi_s,
                           f'Au sol, vitesse sol > {L.taxi_kt:g} kt.'))
        if stage in ('parked', 'pushback', 'taxi_out'):
            result.append(('takeoff', on_ground and gs is not None and gs >= L.takeoff_kt or airborne,
                           L.takeoff_s, f'Vitesse sol ≥ {L.takeoff_kt:g} kt ou appareil en vol.'))
        if stage == 'takeoff':
            result.append(('taxi_out', on_ground and gs is not None and gs < L.reject_kt and not state.airborne_seen,
                           L.taxi_s, 'Décollage interrompu : retour à la vitesse de roulage.'))
            result.append(('climb', airborne and agl is not None and agl >= L.initial_climb_agl_ft, L.climb_s,
                           f'En vol au-dessus de {L.initial_climb_agl_ft:g} ft sol.'))
        if stage == 'climb':
            result.append(('cruise', airborne and level and alt is not None and alt >= floor, L.cruise_s,
                           f'Palier stable à {alt:,.0f} ft.'.replace(',', ' ') if alt is not None else ''))
        if stage in ('climb', 'cruise'):
            result.append(('descent', airborne and vs is not None and vs < -L.descent_fpm and alt is not None
                           and state.peak_ft is not None and alt <= state.peak_ft-L.descent_drop_ft, L.descent_s,
                           f'Vario < −{L.descent_fpm:g} ft/min, {L.descent_drop_ft:g} ft sous le plus haut niveau.'))
        if stage == 'descent':
            result.append(('cruise', airborne and level and alt is not None and alt >= floor and (
                distance is None or distance > 3*L.approach_nm), L.recruise_s, 'Nouveau palier haut prolongé.'))
        if stage in ('climb', 'cruise', 'descent'):
            near = distance is not None and distance <= L.approach_nm and agl is not None and agl <= L.approach_agl_ft
            # Low in descent is an approach even far from the planned destination (diversion, long final).
            blind = stage == 'descent' and agl is not None and agl <= L.approach_blind_agl_ft
            result.append(('approach', airborne and vs is not None and vs <= L.level_fpm and (near or blind),
                           L.approach_s, f'À {distance:.0f} NM de la destination, {agl:,.0f} ft sol.'.replace(',', ' ')
                           if near else f'Sous {L.approach_blind_agl_ft:g} ft sol en descente.'))
        if stage in ('approach', 'go_around'):
            result.append(('final', airborne and agl is not None and agl <= L.final_agl_ft and vs is not None
                           and vs < 0, L.final_s, f'Sous {L.final_agl_ft:g} ft sol en descente.'))
        if stage in ('approach', 'final'):
            result.append(('go_around', airborne and vs is not None and vs > L.go_around_fpm and (
                agl is None or agl < L.approach_agl_ft), L.go_around_s, f'Vario > +{L.go_around_fpm:g} ft/min en approche.'))
        if stage == 'go_around':
            result.append(('approach', airborne and vs is not None and vs < -L.level_fpm, 15,
                           'Nouvelle descente après la remise des gaz.'))
        if stage in ('climb', 'cruise', 'descent', 'approach', 'final', 'go_around'):
            result.append(('rollout', on_ground, L.touchdown_s, 'Retour au sol après le vol.'))
        if stage == 'rollout':
            result.append(('taxi_in', on_ground and gs is not None and gs < L.vacate_kt, L.taxi_s,
                           f'Vitesse sol < {L.vacate_kt:g} kt après l’atterrissage.'))
        if stage in ('rollout', 'taxi_in'):
            result.append(('parked_in', on_ground and gs is not None and gs < L.creep_kt, L.parked_s,
                           f'Arrêt pendant {L.parked_s:g} s.'))
        if stage == 'parked_in':
            result.append(('taxi_in', on_ground and gs is not None and gs > L.taxi_kt, L.taxi_s,
                           'Nouveau roulage après l’arrêt.'))
        return result

    def correct(self, state, phase, now):
        """Pilot correction: jump to the phase entry stage; automatic tracking resumes from it."""
        self.reset()
        stage = PHASE_ENTRY[phase]
        return state.model_copy(update={
            'stage': stage, 'phase': phase, 'changed_at': now, 'manual': True,
            'airborne_seen': phase not in ('preflight', 'departure'), 'peak_ft': None,
            'evidence': ['Phase corrigée par le pilote.']})

    def evaluate(self, state, sample, plan, now, *, live, active=True):
        L = self.limits
        if self.last_at is None or not 0 <= now-self.last_at <= L.max_age_s:
            self.holds.clear()
        self.last_at = now
        state = state.model_copy(deep=True)
        floor = cruise_floor(plan, L)
        pending = None
        if not live or not active:
            self.holds.clear()
        elif state.stage is None:
            guess = self.bootstrap(sample, floor)
            for key in [k for k in self.holds if k != 'boot_'+str(guess)]:
                self.holds.pop(key)
            if guess and self.held('boot_'+guess, True, L.bootstrap_s, now):
                state.stage, state.changed_at, state.manual = guess, now, False
                state.airborne_seen = sample['ground'] is False
                state.evidence = ['Suivi démarré : appareil observé en '+STAGE_LABEL[guess].lower()+'.']
        else:
            candidates = []
            for target, condition, hold, reason in self.transitions(state, sample, floor):
                key = state.stage+'>'+target
                if self.held(key, bool(condition), hold, now):
                    candidates.append((target, reason))
                elif key in self.holds and pending is None:
                    pending = {'stage': target, 'elapsed_s': round(now-self.holds[key]), 'hold_s': hold}
            if candidates:
                index = STAGE_IDS.index(state.stage)
                forward = [c for c in candidates if STAGE_IDS.index(c[0]) > index]
                target, reason = max(forward, key=lambda c: STAGE_IDS.index(c[0])) if forward else candidates[0]
                state.stage, state.changed_at, state.manual, state.evidence = target, now, False, [reason]
                self.holds.clear()
                pending = None
        if state.stage is not None:
            state.phase = STAGE_PHASE[state.stage]
        if live and sample['ground'] is False:
            if state.stage not in GROUND_STAGES:
                state.airborne_seen = True
            if sample['alt'] is not None:
                state.peak_ft = sample['alt'] if state.peak_ft is None else max(state.peak_ft, sample['alt'])
        known = state.stage is not None
        status = 'unavailable' if not known else 'derived' if live and active else 'stale'
        return state, {
            'stage': state.stage, 'stage_label': STAGE_LABEL.get(state.stage),
            'phase': state.phase if known else None,
            'effective': {'value': state.phase if known else None, 'status': status},
            'substate': SUBSTATE.get(state.stage),
            'mode': 'manual' if state.manual else 'automatic',
            'live': bool(live and active), 'since': state.changed_at, 'evidence': state.evidence,
            'next': {'label': STAGE_NEXT.get(state.stage) if known else
                     'Placement automatique dès réception de mesures récentes', **(pending or {})},
            'distance_to_destination_nm': None if sample['distance'] is None else round(sample['distance']),
        }


__all__ = ['PHASE_IDS', 'PhaseEngine', 'PhaseState', 'PhaseThresholds', 'STAGES', 'read_sample']
