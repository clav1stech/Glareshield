"""Standard SimVars exported to assistants, independent from lighting sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal['number', 'bool', 'string']
Level = Literal['essential', 'detailed']

GROUPS = {
    'aircraft': 'Appareil',
    'position': 'Position',
    'speed': 'Vitesses',
    'attitude': 'Cap et route',
    'configuration': 'Configuration',
    'engines': 'Moteurs',
    'weights': 'Masses et carburant',
    'environment': 'Environnement',
    'time': 'Heure',
    'fenix': 'Variables Fenix configurées',
}


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    group: str
    variable: str
    sim_unit: str
    unit: str | None
    kind: Kind = 'number'
    interval_ms: int = 1000
    max_age_s: float = 5
    level: Level = 'essential'
    digits: int | None = 0
    origin: Literal['simvar', 'lvar'] = 'simvar'
    note: str | None = None
    values: dict[str, str] = field(default_factory=dict)
    validated: bool = False
    min_ground_speed_kt: float | None = None

    def definition(self) -> dict:
        """Picklable request sent to the SimConnect worker."""
        name = self.variable if self.origin == 'simvar' else 'L:'+self.variable.removeprefix('L:')
        return {'name': name, 'unit': 'String' if self.kind == 'string' else self.sim_unit,
                'interval_ms': self.interval_ms, 'kind': self.kind, 'origin': self.origin}


FENIX_NOTE = 'SimVar standard ; correspondance avec les systèmes du Fenix à valider.'

# Names and units follow the MSFS SDK simulation variable reference.
STANDARD: tuple[Entry, ...] = (
    Entry('title', 'Titre de l’appareil', 'aircraft', 'TITLE', 'String', None, 'string', 30000, 120, digits=None),
    Entry('atc_id', 'Identifiant ATC du simulateur', 'aircraft', 'ATC ID', 'String', None, 'string', 30000, 120,
          'detailed', None),
    Entry('latitude', 'Latitude', 'position', 'PLANE LATITUDE', 'degrees', 'deg', interval_ms=2000, max_age_s=8, digits=4),
    Entry('longitude', 'Longitude', 'position', 'PLANE LONGITUDE', 'degrees', 'deg', interval_ms=2000, max_age_s=8, digits=4),
    Entry('altitude_msl', 'Altitude vraie (MSL)', 'position', 'PLANE ALTITUDE', 'feet', 'ft', interval_ms=2000, max_age_s=8),
    Entry('altitude_indicated', 'Altitude indiquée', 'position', 'INDICATED ALTITUDE', 'feet', 'ft', interval_ms=2000,
          max_age_s=8, note='Dépend du calage de l’altimètre standard du simulateur.'),
    Entry('altitude_agl', 'Hauteur au-dessus du sol', 'position', 'PLANE ALT ABOVE GROUND', 'feet', 'ft',
          interval_ms=2000, max_age_s=8),
    Entry('on_ground', 'Au sol', 'position', 'SIM ON GROUND', 'bool', None, 'bool', 2000, 8, digits=None),
    Entry('ias', 'Vitesse indiquée', 'speed', 'AIRSPEED INDICATED', 'knots', 'kt', interval_ms=2000, max_age_s=8),
    Entry('tas', 'Vitesse vraie', 'speed', 'AIRSPEED TRUE', 'knots', 'kt', interval_ms=2000, max_age_s=8, level='detailed'),
    Entry('mach', 'Mach', 'speed', 'AIRSPEED MACH', 'mach', 'M', interval_ms=2000, max_age_s=8, digits=3),
    Entry('ground_speed', 'Vitesse sol', 'speed', 'GROUND VELOCITY', 'knots', 'kt', interval_ms=2000, max_age_s=8),
    Entry('vertical_speed', 'Vitesse verticale', 'speed', 'VERTICAL SPEED', 'feet per minute', 'ft/min',
          interval_ms=2000, max_age_s=8),
    Entry('heading_magnetic', 'Cap magnétique', 'attitude', 'PLANE HEADING DEGREES MAGNETIC', 'degrees', 'deg',
          interval_ms=2000, max_age_s=8),
    Entry('heading_true', 'Cap vrai', 'attitude', 'PLANE HEADING DEGREES TRUE', 'degrees', 'deg',
          interval_ms=2000, max_age_s=8, level='detailed'),
    Entry('track_magnetic', 'Route magnétique', 'attitude', 'GPS GROUND MAGNETIC TRACK', 'degrees', 'deg',
          interval_ms=2000, max_age_s=8, level='detailed', note='Calculée par le GPS du simulateur ; sans signification à l’arrêt.',
          min_ground_speed_kt=5),
    Entry('gear_handle_down', 'Levier de train sorti', 'configuration', 'GEAR HANDLE POSITION', 'bool', None, 'bool',
          2000, 8, digits=None, note=FENIX_NOTE),
    Entry('flaps_handle_index', 'Cran du levier de volets', 'configuration', 'FLAPS HANDLE INDEX', 'number', None,
          interval_ms=2000, max_age_s=8, note=FENIX_NOTE),
    Entry('spoilers_handle', 'Levier d’aérofreins', 'configuration', 'SPOILERS HANDLE POSITION', 'percent', '%',
          interval_ms=2000, max_age_s=8, level='detailed', note=FENIX_NOTE),
    Entry('spoilers_armed', 'Aérofreins armés', 'configuration', 'SPOILERS ARMED', 'bool', None, 'bool', 2000, 8,
          digits=None, note=FENIX_NOTE),
    Entry('parking_brake', 'Frein de parc', 'configuration', 'BRAKE PARKING POSITION', 'bool', None, 'bool', 2000, 8,
          digits=None, note=FENIX_NOTE),
    Entry('engine_1_running', 'Moteur 1 en fonctionnement', 'engines', 'GENERAL ENG COMBUSTION:1', 'bool', None,
          'bool', 5000, 20, digits=None, note=FENIX_NOTE),
    Entry('engine_2_running', 'Moteur 2 en fonctionnement', 'engines', 'GENERAL ENG COMBUSTION:2', 'bool', None,
          'bool', 5000, 20, digits=None, note=FENIX_NOTE),
    Entry('fuel_total', 'Carburant total', 'weights', 'FUEL TOTAL QUANTITY WEIGHT', 'kilograms', 'kg',
          interval_ms=15000, max_age_s=60, level='detailed', note=FENIX_NOTE),
    Entry('total_weight', 'Masse totale', 'weights', 'TOTAL WEIGHT', 'kilograms', 'kg', interval_ms=15000,
          max_age_s=60, level='detailed', note=FENIX_NOTE),
    Entry('wind_direction', 'Direction du vent', 'environment', 'AMBIENT WIND DIRECTION', 'degrees', 'deg',
          interval_ms=15000, max_age_s=60, note='Direction d’où vient le vent, référence vraie selon le SDK.'),
    Entry('wind_speed', 'Force du vent', 'environment', 'AMBIENT WIND VELOCITY', 'knots', 'kt', interval_ms=15000,
          max_age_s=60),
    Entry('outside_temperature', 'Température extérieure', 'environment', 'AMBIENT TEMPERATURE', 'celsius', '°C',
          interval_ms=15000, max_age_s=60),
    Entry('sea_level_pressure', 'Pression au niveau de la mer', 'environment', 'SEA LEVEL PRESSURE', 'millibars',
          'hPa', interval_ms=30000, max_age_s=120, level='detailed'),
    Entry('zulu_time', 'Heure UTC du simulateur', 'time', 'ZULU TIME', 'seconds', 's', interval_ms=30000,
          max_age_s=120, level='detailed', note='Secondes depuis minuit UTC dans le simulateur.'),
)

STANDARD_KEYS = frozenset(entry.key for entry in STANDARD)
