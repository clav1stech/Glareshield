"""AI Bridge service: single entry point for the web interface, exports and future MCP tools."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ..config import atomic_write
from ..copilot.session import SessionService
from .catalog import GROUPS, STANDARD, Entry
from .config import AIBridgeSettings, load_settings, save_settings
from .context import LEVELS, build_context, chat_text, iso, serialize
from .ivao import ICAO, IVAOError, IVAOService, airports_of_interest
from .scenario import PHASES, ScenarioPlayer, phase
from .simbrief import FlightPlanStore, parse_ofp
from .telemetry import TelemetryStore, qualify


NOTES_MAX = 2000


class AIBridge:
    def __init__(self, root: Path, clock=time.time, transport=None, network_transport=None):
        self.root = root
        self.clock = clock
        self.path = root/'local/ai-bridge.yaml'
        self.settings_error = None
        try:
            self.settings = load_settings(self.path)
        except Exception as error:
            # An invalid private file disables the module without affecting lighting.
            self.settings = AIBridgeSettings()
            self.settings_error = type(error).__name__
        self.live = TelemetryStore('simconnect', clock)
        self.scenario: ScenarioPlayer | None = None
        self.plan = FlightPlanStore(root/'local/state/simbrief-ofp.json', clock, transport)
        self.notes_path = root/'local/state/pilot-notes.json'
        self.notes = self.load_notes()
        self.listeners = []
        self.ivao = IVAOService(clock, network_transport, self.settings.ivao)
        self.ivao.context = self.watch_context
        self.sessions = SessionService(self)

    # Catalogue

    def entries(self) -> list[Entry]:
        validated = set(self.settings.validated)
        standard = [replace(entry, validated=True) if entry.key in validated else entry
                    for entry in STANDARD if entry.key not in self.settings.disabled]
        return standard+[lvar.entry() for lvar in self.settings.lvars]

    def definitions(self) -> dict:
        """Requests for the shared SimConnect worker; empty when the module is disabled."""
        return {entry.key: entry.definition() for entry in self.entries()} if self.settings.enabled else {}

    def save(self, settings: AIBridgeSettings) -> AIBridgeSettings:
        previous = self.definitions()
        self.settings = save_settings(self.path, settings)
        self.settings_error = None
        self.ivao.configure(self.settings.ivao)
        if not self.settings.enabled:
            self.live.clear()
        if self.definitions() != previous:
            for listener in self.listeners:
                listener()
        return self.settings

    # Data sources

    def on_simulator_message(self, message: dict) -> None:
        if self.settings.enabled:
            self.live.update(message)
            if not self.scenario:
                try:
                    self.sessions.refresh_phase()
                except (OSError, ValueError):
                    self.sessions.phase_error = 'Phase non enregistrée ; dernier suivi conservé.'

    def set_scenario(self, active: bool, start_phase: str | None = None) -> None:
        offset = next((start for name, start, _ in PHASES if name == start_phase), 0)
        self.scenario = ScenarioPlayer(self.clock, offset) if active else None
        self.sessions.phase_engines.clear()

    def store(self) -> TelemetryStore:
        return self.scenario.tick() if self.scenario else self.live

    def load_demo_plan(self) -> dict:
        data = json.loads((Path(__file__).parent/'demo_ofp.json').read_text(encoding='utf-8'))
        data['params']['time_generated'] = str(int(self.clock()))
        plan = self.plan.store(parse_ofp(data), 'demo')
        self.sessions.view()  # Synchronize independently of the currently displayed page.
        return plan

    async def refresh_plan(self) -> dict:
        plan = await self.plan.refresh(self.settings.simbrief_user, self.settings.simbrief_kind)
        self.sessions.view()
        return plan

    # Pilot notes: declarations that the simulator cannot provide (MCDU entries, clearances, ATIS)

    def load_notes(self) -> dict:
        try:
            data = json.loads(self.notes_path.read_text(encoding='utf-8'))
            return {'text': str(data['text'])[:NOTES_MAX], 'updated_utc': data.get('updated_utc')}
        except (OSError, ValueError, KeyError, TypeError):
            return {'text': '', 'updated_utc': None}

    def set_notes(self, text: str) -> dict:
        text = text.strip()
        if len(text) > NOTES_MAX:
            raise ValueError(f'Notes limitées à {NOTES_MAX} caractères.')
        self.notes = {'text': text, 'updated_utc': iso(self.clock()) if text else None}
        atomic_write(self.notes_path, json.dumps(self.notes, ensure_ascii=False))
        return self.notes

    def suggested_level(self) -> str:
        """Briefing on the ground or without data, flight update once airborne."""
        on_ground = self.store().samples.get('on_ground')
        # SimConnect reports booleans as 0.0 / 1.0.
        airborne = on_ground is not None and not isinstance(on_ground.value, str) and not on_ground.value
        return 'flight' if airborne else 'briefing'

    def resolve(self, level: str) -> str:
        level = self.suggested_level() if level == 'auto' else level
        if level not in LEVELS:
            raise ValueError('Niveau d’export inconnu.')
        return level

    # IVAO network data: collected by its own loop, read here from the shared cache only

    def aircraft_position(self, now: float) -> dict:
        """Observed position used to select nearby IVAO stations, with its status."""
        store, fields = self.store(), {}
        for entry in self.entries():
            if entry.key in ('latitude', 'longitude'):
                fields[entry.key] = qualify(entry, store, now)
        lat, lon = fields.get('latitude'), fields.get('longitude')
        if not lat or not lon:
            return {'status': 'unavailable', 'reason': 'Position non lue par AI Bridge'}
        if lat['status'] not in ('observed', 'simulated') or lon['status'] not in ('observed', 'simulated'):
            worst = lat if lat['status'] not in ('observed', 'simulated') else lon
            return {'status': worst['status'], 'reason': worst.get('reason') or 'Position non exploitable'}
        return {'status': lat['status'], 'age_s': max(lat['age_s'], lon['age_s']),
                'latitude': lat['value'], 'longitude': lon['value']}

    def watch_context(self) -> tuple[list[dict], tuple[float, float] | None, list[tuple[float, float]]]:
        """Airports, aircraft position and planned route points used to pick the positions worth a notice."""
        aircraft = self.aircraft_position(self.clock())
        position = (aircraft['latitude'], aircraft['longitude']) if 'latitude' in aircraft else None
        route = [(item['latitude'], item['longitude']) for item in (self.plan.plan or {}).get('waypoints', [])
                 if item.get('latitude') is not None and item.get('longitude') is not None]
        return airports_of_interest(self.plan.plan, self.settings.ivao.airports), position, route

    def test_notification(self) -> bool:
        """Show a sample notice so the pilot can check its visibility over the simulator."""
        if not self.ivao.notifier:
            return False
        self.ivao.notifier(['XXNC_TWR 118.700 connecté (arrivée XXNC)', 'Notification de test Glareshield'],
                           self.settings.ivao.notification_seconds)
        return True

    def network(self, level: str, now: float | None = None) -> dict | None:
        now = self.clock() if now is None else now
        return self.ivao.view(level, airports_of_interest(self.plan.plan, self.settings.ivao.airports),
                              self.aircraft_position(now), now)

    def network_page(self) -> dict:
        """get_network_context: IVAO data for the interface, with full provenance."""
        now = self.clock()
        return {**self.ivao.summary(now), 'settings': self.settings.ivao.model_dump(mode='json'),
                'view': self.network('full', now)}

    def lookup_airport(self, icao: str) -> dict:
        """Manual consultation of any airport from the cache; it is not added to the exports."""
        icao = icao.strip().upper()
        if not ICAO.match(icao):
            raise ValueError('Code OACI attendu (4 caractères).')
        if not self.settings.ivao.enabled:
            raise IVAOError('Activer l’intégration IVAO pour consulter un aérodrome.')
        known = next((item for item in airports_of_interest(self.plan.plan, []) if item['icao'] == icao), {})
        airport = {'icao': icao, 'roles': ['manual']}
        if 'latitude' in known:
            airport['latitude'], airport['longitude'] = known['latitude'], known['longitude']
        now = self.clock()
        return self.ivao.view('full', [airport], {'status': 'unavailable', 'reason': 'Consultation d’un aérodrome'}, now)

    # Read-only views, intended to back future MCP tools one to one

    def snapshot(self, level: str = 'auto') -> dict:
        """get_flight_snapshot"""
        level, now = self.resolve(level), self.clock()
        return build_context(level, self.entries(), self.store(), self.plan.plan,
                             self.plan.describe(self.settings.ofp_max_age_h), now, self.notes,
                             self.network(level, now))

    def flight_plan(self) -> dict:
        """get_flight_plan"""
        return {**self.plan.describe(self.settings.ofp_max_age_h), 'plan': self.plan.plan}

    def available_variables(self) -> list[dict]:
        """get_available_variables"""
        store, now = self.store(), self.clock()
        result = []
        for entry in self.entries():
            field = qualify(entry, store, now)
            result.append({'key': entry.key, 'label': entry.label, 'group': entry.group,
                           'group_label': GROUPS.get(entry.group, entry.group), 'origin': entry.origin,
                           'variable': entry.variable, 'unit': entry.unit, 'level': entry.level,
                           'interval_ms': entry.interval_ms, 'max_age_s': entry.max_age_s,
                           'verification': 'validated_locally' if entry.validated else (
                               'msfs_sdk' if entry.origin == 'simvar' else 'configured_unverified'),
                           'note': entry.note, **{k: field.get(k) for k in ('value', 'status', 'age_s', 'reason', 'meaning')}})
        return result

    def chat(self, level: str = 'auto') -> str:
        return chat_text(self.snapshot(level))

    def export(self, level: str = 'auto') -> Path:
        document = self.snapshot(level)
        level = document['level']
        stamp = datetime.fromtimestamp(self.clock(), UTC).strftime('%Y%m%d-%H%M%SZ')
        suffix = '-simulation' if document['data_origin'] != 'simconnect' else ''
        path = self.root/'local/exports'/f'flight-context-{stamp}-{level}{suffix}.json'
        atomic_write(path, json.dumps(document, ensure_ascii=False, indent=2))
        return path

    def status(self) -> dict:
        store = self.store()
        fields = [qualify(entry, store) for entry in self.entries()]
        counts = {status: sum(field['status'] == status for field in fields)
                  for status in ('observed', 'simulated', 'stale', 'unavailable')}
        return {'enabled': self.settings.enabled, 'settings_error': self.settings_error, 'mode': 'scenario' if self.scenario else 'simconnect',
                'scenario_phase': phase(self.scenario.elapsed()) if self.scenario else None,
                'connected': store.connected, 'paused': store.paused, 'counts': counts,
                'telemetry_errors': len(store.errors),
                'suggested_level': self.suggested_level(),
                'sizes': {level: len(serialize(self.snapshot(level))) for level in LEVELS},
                'notes': self.notes,
                'simbrief_configured': bool(self.settings.simbrief_user),
                'ivao': self.ivao.summary(),
                'plan': self.plan.describe(self.settings.ofp_max_age_h)}
