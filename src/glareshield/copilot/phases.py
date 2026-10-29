"""Read-only flight phase inference. No UI, scenario labels or cockpit commands."""
from __future__ import annotations

from dataclasses import dataclass
import math

from pydantic import Field

from ..aibridge.context import derived
from ..model import StrictModel
from .contract import PHASE_IDS, PhaseId, QualifiedValue


@dataclass(frozen=True)
class PhaseThresholds:
    max_age_s: float = 8
    moving_kt: float = 3
    stopped_kt: float = 1
    takeoff_kt: float = 80
    takeoff_exit_kt: float = 60
    landing_roll_kt: float = 40
    taxi_after_landing_kt: float = 30
    vertical_fpm: float = 300
    cruise_gap_ft: float = 1000
    arrival_nm: float = 60
    arrival_agl_ft: float = 10000
    movement_s: float = 5
    takeoff_s: float = 3
    climb_s: float = 8
    cruise_s: float = 30
    descent_s: float = 15
    arrival_s: float = 8
    landing_s: float = 5
    parking_s: float = 10


class PhaseState(StrictModel):
    phase: PhaseId = 'preflight'
    confirmed: bool = False
    cruise_seen: bool = False
    airborne_seen: bool = False
    substate: str | None = None
    changed_at: float | None = None
    evidence: list[str] = Field(default_factory=list)


class PhaseEngine:
    """State is durable; continuous confirmation timers deliberately are not.

    Each call supplies qualified flat telemetry, connection health and the planned
    OFP. Missing samples, clock reversal or a gap >8 s reset all pending holds.
    Only the highest *confirmed* forward phase is selected. Arrival remains the
    phase during a go-around; its substate changes without touching any actions.
    """

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

    def evaluate(self, state, fields, plan, now, *, connected, paused,
                 last_message, forced=None, forced_at=None, active=True, departure_ready=False,
                 plan_current=True, suspension_reason=None):
        limits = self.limits
        if self.last_at is None or not 0 <= now-self.last_at <= limits.max_age_s:
            self.holds.clear()
        self.last_at = now
        state = state.model_copy(deep=True)
        inputs, reasons, evidence = [], [], []
        input_ages, valid_ages = [], []
        inputs.extend(['session.started_at', 'session.phase_state'])

        def read(key, unit, boolean=False):
            field = fields.get(key, {})
            inputs.append('telemetry.'+key)
            value = field.get('value')
            age = field.get('age_s')
            if age is not None:
                input_ages.append(max(0, age))
            valid = type(value) is bool if boolean else type(value) in (int, float) and math.isfinite(value)
            if (field.get('status') not in ('observed', 'simulated') or not valid
                    or field.get('unit') != unit or field.get('age_s') is None
                    or not 0 <= field['age_s'] <= limits.max_age_s):
                reasons.append(key+' : mesure absente, périmée ou unité invalide.')
                return None
            valid_ages.append(age)
            return value

        ground = read('on_ground', None, True)
        speed = read('ground_speed', 'kt') if ground else None
        vertical = read('vertical_speed', 'ft/min') if ground is False else None
        healthy = connected and not paused and last_message is not None and 0 <= now-last_message <= limits.max_age_s
        if not healthy:
            reasons.append('Transitions suspendues : connexion absente, pause ou télémétrie périmée.')
        if not active:
            reasons.append('Suivi inactif : transitions suspendues.')
        if suspension_reason:
            reasons.append(suspension_reason)
        blocked = not healthy or not active or bool(reasons)
        geometry = {}
        gap = distance = agl = None
        if plan is not None and not plan_current:
            plan = None
            reasons.append('Plan prévu périmé ou sans date : transitions dépendant du plan suspendues.')
        if not blocked and ground is False:
            altitude = read('altitude_msl', 'ft')
            target = (plan or {}).get('cruise', {}).get('initial_altitude_ft')
            if altitude is not None and type(target) in (int, float) and math.isfinite(target):
                gap = altitude-target
                inputs.append('flight_plan.cruise.initial_altitude_ft')
                evidence.append(f'Écart altitude MSL / altitude prévue : {gap:g} ft (références différentes possibles).')
            else:
                reasons.append('Niveau prévu absent : croisière non confirmable.')
            # Reuse the existing geometric calculations; never a scenario phase.
            lat, lon = read('latitude', 'deg'), read('longitude', 'deg')
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                geometry = derived(fields, plan, 'flight')
                distance = geometry.get('direct_distance_to_destination', {}).get('value')
                if distance is not None:
                    inputs.append('flight_plan.destination')
                    evidence.append(f'Destination prévue à {distance:g} NM en orthodromie.')
            if distance is None:
                reasons.append('Position ou destination prévue absente : arrivée non confirmable.')
            agl = read('altitude_agl', 'ft')

        candidates = []
        conditions = {
            'departure': (ground is True and speed is not None and speed > limits.moving_kt, limits.movement_s,
                          f'Au sol, vitesse sol > {limits.moving_kt:g} kt pendant {limits.movement_s:g} s.'),
            'climb': (ground is False and vertical is not None and vertical > limits.vertical_fpm, limits.climb_s,
                      f'En vol, vario > {limits.vertical_fpm:g} ft/min pendant {limits.climb_s:g} s.'),
            'cruise': (ground is False and vertical is not None and abs(vertical) <= limits.vertical_fpm
                       and gap is not None and abs(gap) <= limits.cruise_gap_ft, limits.cruise_s,
                       f'Palier ±{limits.vertical_fpm:g} ft/min à ±{limits.cruise_gap_ft:g} ft du niveau prévu pendant {limits.cruise_s:g} s.'),
            'descent': (state.cruise_seen and ground is False and vertical is not None
                        and vertical < -limits.vertical_fpm, limits.descent_s,
                        f'Croisière déjà atteinte, vario < −{limits.vertical_fpm:g} ft/min pendant {limits.descent_s:g} s.'),
            'arrival': (state.cruise_seen and ground is False and vertical is not None and vertical <= 0
                        and distance is not None and distance <= limits.arrival_nm
                        and agl is not None and agl <= limits.arrival_agl_ft, limits.arrival_s,
                        f'Croisière atteinte, destination ≤ {limits.arrival_nm:g} NM, hauteur ≤ {limits.arrival_agl_ft:g} ft AGL et vario ≤ 0 pendant {limits.arrival_s:g} s.'),
        }
        if forced is not None or blocked:
            self.holds.clear()
        else:
            for phase, (condition, duration, label) in conditions.items():
                if self.held('phase_'+phase, condition, duration, now):
                    candidates.append((phase, label))
            if departure_ready:
                inputs.append('pilot.event.departure_ready')
                candidates.append(('departure', 'Pilote prêt pour le départ (déclaration explicite).'))
            if self.held('returned_ground', state.airborne_seen and ground is True, limits.landing_s, now):
                candidates.append(('arrival', 'Retour au sol confirmé après le vol ; destination non déduite.'))
            if not state.confirmed and ground is True:
                state.confirmed, state.changed_at = True, now
                state.evidence = ['Suivi démarré ; appareil observé au sol.']
            if candidates:
                selected, reason = max(candidates, key=lambda item: PHASE_IDS.index(item[0]))
                if PHASE_IDS.index(selected) > PHASE_IDS.index(state.phase):
                    state.phase, state.confirmed, state.changed_at = selected, True, now
                    state.evidence = [reason]
                    state.substate = None
                if selected == 'cruise':
                    state.cruise_seen = True
            if (self.held('airborne', ground is False, limits.climb_s, now)
                    and state.confirmed and state.phase != 'preflight'):
                state.airborne_seen = True
            self.substate(state, ground, speed, vertical, now)

        if not state.confirmed:
            reasons.append('Phase automatique non confirmée ; correction manuelle disponible.')
        if ground is False and not state.cruise_seen and state.phase not in ('preflight', 'departure'):
            if vertical is not None and vertical < -limits.vertical_fpm:
                reasons.append('Descente sans croisière confirmée : corriger manuellement si nécessaire.')
        # Age refers only to the actual phase inputs, not unrelated catalogue entries.
        age = max(input_ages if blocked else valid_ages, default=0)
        current_missing = ground is False and ((state.phase == 'cruise' and gap is None)
                                               or (state.phase == 'arrival' and (distance is None or agl is None)))
        status = 'unavailable' if not state.confirmed else 'stale' if blocked or current_missing else 'derived'
        automatic = QualifiedValue(value=state.phase if state.confirmed else None, unit=None,
                                   nature='calculated', status=status, source='copilot.phase_engine',
                                   reference='phase:'+str(state.changed_at), age_s=age if state.confirmed else None,
                                   max_age_s=limits.max_age_s, verification='not_applicable',
                                   method='Seuils confirmés dans la durée ; progression vers l’avant, état conservé sur interruption.',
                                   inputs=list(dict.fromkeys(inputs)) or ['session.started'])
        effective = automatic
        if forced is not None:
            effective = QualifiedValue(value=forced, unit=None, nature='declared', status='available',
                                       source='pilot.phase', reference='session.forced_phase:'+str(forced_at),
                                       age_s=max(0, now-forced_at) if forced_at is not None else 0,
                                       max_age_s=None, verification='not_applicable')
        next_phase = PHASE_IDS[PHASE_IDS.index(state.phase)+1] if state.phase != 'arrival' else None
        if not state.confirmed and ground is False:
            next_phase = 'climb' if vertical is not None and vertical > limits.vertical_fpm else 'cruise'
        trigger = conditions.get(next_phase)
        pending = self.holds.get('phase_'+str(next_phase))
        return state, {
            'effective': effective.model_dump(), 'automatic': automatic.model_dump(),
            'mode': 'manual' if forced else 'automatic',
            'substate': state.substate if forced is None else None,
            'evidence': state.evidence+evidence, 'uncertainty': list(dict.fromkeys(reasons)),
            'suspended': blocked or forced is not None,
            'next_trigger': {'phase': next_phase, 'label': trigger[2] if trigger else
                             'Arrivée conservée : approche, atterrissage, roulage, parking ou remise des gaz.',
                             'hold_s': trigger[1] if trigger else 0,
                             'elapsed_s': max(0, now-pending) if pending is not None else 0},
            'geometry': geometry,
        }

    def substate(self, state, ground, speed, vertical, now):
        limits = self.limits
        taxi = (ground is True and speed is not None and speed > limits.moving_kt
                and (not state.airborne_seen or speed < limits.taxi_after_landing_kt)
                and (state.substate != 'takeoff' or speed < limits.takeoff_exit_kt))
        candidates = [
            ('taxi', taxi, limits.movement_s),
            ('takeoff', state.phase == 'departure' and (ground is False or
                        speed is not None and speed >= limits.takeoff_kt), limits.takeoff_s),
            ('approach', state.phase == 'arrival' and ground is False and vertical is not None
                         and vertical <= 0, limits.arrival_s),
            ('landing', state.airborne_seen and ground is True and speed is not None
                        and speed >= limits.landing_roll_kt, limits.landing_s),
            ('parking', ground is True and speed is not None and speed <= limits.stopped_kt, limits.parking_s),
            ('go_around', state.phase == 'arrival' and ground is False and vertical is not None
                          and vertical > limits.vertical_fpm, limits.climb_s),
        ]
        confirmed = [name for name, condition, duration in candidates
                     if self.held('sub_'+name, condition, duration, now)]
        if confirmed:
            state.substate = confirmed[-1]
