"""Deterministic fictitious A320 flight used to exercise AI Bridge without a simulator."""
from __future__ import annotations

import math
import time

from .telemetry import TelemetryStore

ORIGIN = (48.7233, 2.3794, 291)
DESTINATION = (43.6584, 7.2159, 13)
DURATION_S = 1500
PHASES = (
    ('parking', 0, 90), ('taxi_out', 90, 210), ('takeoff', 210, 260), ('climb', 260, 700),
    ('cruise', 700, 1000), ('descent', 1000, 1300), ('approach', 1300, 1420),
    ('landing', 1420, 1470), ('taxi_in', 1470, DURATION_S),
)


def bearing(start, end):
    lat1, lon1, lat2, lon2 = map(math.radians, (start[0], start[1], end[0], end[1]))
    x = math.sin(lon2-lon1)*math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1)
    return (math.degrees(math.atan2(x, y))+360) % 360


def ramp(t, start, end, low, high):
    if t <= start:
        return low
    if t >= end:
        return high
    return low+(high-low)*(t-start)/(end-start)


def phase(t: float) -> str:
    t %= DURATION_S
    return next(name for name, start, end in PHASES if start <= t < end)


def values(t: float) -> dict:
    """Return plausible SimVar values for the scenario time ``t`` in seconds."""
    t %= DURATION_S
    name = phase(t)
    progress = ramp(t, 210, 1450, 0, 1)
    latitude = ORIGIN[0]+(DESTINATION[0]-ORIGIN[0])*progress
    longitude = ORIGIN[1]+(DESTINATION[1]-ORIGIN[1])*progress
    on_ground = name in ('parking', 'taxi_out', 'takeoff', 'landing', 'taxi_in') and not (name == 'takeoff' and t > 255)
    if name == 'climb':
        altitude = ramp(t, 260, 700, ORIGIN[2], 35000)
    elif name == 'cruise':
        altitude = 35000
    elif name == 'descent':
        altitude = ramp(t, 1000, 1300, 35000, 3000)
    elif name == 'approach':
        altitude = ramp(t, 1300, 1420, 3000, DESTINATION[2])
    elif name == 'takeoff':
        altitude = ramp(t, 255, 260, ORIGIN[2], ORIGIN[2]+50)
    else:
        altitude = ORIGIN[2] if t < 700 else DESTINATION[2]
    vertical = {'climb': ramp(t, 260, 700, 2800, 900), 'descent': -2200, 'approach': -800}.get(name, 0)
    speed = {'parking': 0, 'taxi_out': 15, 'takeoff': ramp(t, 210, 255, 0, 150), 'climb': ramp(t, 260, 700, 160, 280),
             'cruise': 270, 'descent': ramp(t, 1000, 1300, 280, 250), 'approach': ramp(t, 1300, 1420, 210, 137),
             'landing': ramp(t, 1420, 1470, 137, 20), 'taxi_in': 12}[name]
    temperature = max(-56.5, 15-altitude/1000*1.98)
    mach = speed*(1+altitude/1000*.02)/(38.967854*math.sqrt(temperature+273.15))
    wind = ramp(altitude, 0, 35000, 8, 45)
    track = bearing(ORIGIN, DESTINATION) if 210 <= t < 1470 else (95 if t < 210 else 210)
    burnt = ramp(t, 60, DURATION_S, 0, 3600)
    flaps = 0 if name in ('climb', 'cruise', 'descent') and not (name == 'climb' and t < 330) else 1
    if name == 'approach':
        flaps = 3 if t < 1380 else 4
    return {
        'title': 'Démonstration Glareshield A320 (données simulées)',
        'atc_id': 'GSH123',
        'latitude': latitude, 'longitude': longitude,
        'altitude_msl': altitude, 'altitude_indicated': altitude,
        'altitude_agl': max(0.0, altitude-(ORIGIN[2] if t < 700 else DESTINATION[2])),
        'on_ground': on_ground,
        'ias': speed, 'tas': speed*(1+altitude/1000*.02), 'mach': mach,
        'ground_speed': max(0.0, speed*(1+altitude/1000*.02)-wind*.3),
        'vertical_speed': vertical,
        'heading_magnetic': (track-2) % 360, 'heading_true': track, 'track_magnetic': (track-2) % 360,
        'gear_handle_down': not (270 <= t < 1330),
        'flaps_handle_index': float(flaps),
        'spoilers_handle': 0.0,
        'parking_brake': t < 85 or t >= 1495,
        'engine_1_running': t >= 50, 'engine_2_running': t >= 65,
        'fuel_total': 6200-burnt, 'total_weight': 66500-burnt,
        'wind_direction': 280.0, 'wind_speed': wind,
        'outside_temperature': temperature,
        'sea_level_pressure': 1016.0,
        'zulu_time': float((9*3600+int(t)) % 86400),
    }


class ScenarioPlayer:
    """Feeds a separate store, so simulated values never mix with live observations."""

    def __init__(self, clock=time.time, offset_s: float = 0):
        self.clock = clock
        self.started = clock()-offset_s
        self.store = TelemetryStore('scenario', clock)

    def elapsed(self) -> float:
        return (self.clock()-self.started) % DURATION_S

    def tick(self) -> TelemetryStore:
        now = self.clock()
        self.store.update({'connected': True, 'paused': False,
                           'telemetry': {key: (value, now) for key, value in values(self.elapsed()).items()}})
        return self.store
