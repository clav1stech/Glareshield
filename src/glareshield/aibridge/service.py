"""AI Bridge service: single entry point for the web interface, exports and future MCP tools."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ..config import atomic_write
from .catalog import GROUPS, STANDARD, Entry
from .config import AIBridgeSettings, load_settings, save_settings
from .context import LEVELS, build_context, chat_text, iso, serialize
from .scenario import PHASES, ScenarioPlayer, phase
from .simbrief import FlightPlanStore, parse_ofp
from .telemetry import TelemetryStore, qualify


NOTES_MAX = 2000


class AIBridge:
    def __init__(self, root: Path, clock=time.time, transport=None):
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

    def set_scenario(self, active: bool, start_phase: str | None = None) -> None:
        offset = next((start for name, start, _ in PHASES if name == start_phase), 0)
        self.scenario = ScenarioPlayer(self.clock, offset) if active else None

    def store(self) -> TelemetryStore:
        return self.scenario.tick() if self.scenario else self.live

    def load_demo_plan(self) -> dict:
        data = json.loads((Path(__file__).parent/'demo_ofp.json').read_text(encoding='utf-8'))
        data['params']['time_generated'] = str(int(self.clock()))
        return self.plan.store(parse_ofp(data), 'demo')

    async def refresh_plan(self) -> dict:
        return await self.plan.refresh(self.settings.simbrief_user, self.settings.simbrief_kind)

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

    # Read-only views, intended to back future MCP tools one to one

    def snapshot(self, level: str = 'auto') -> dict:
        """get_flight_snapshot"""
        return build_context(self.resolve(level), self.entries(), self.store(), self.plan.plan,
                             self.plan.describe(self.settings.ofp_max_age_h), self.clock(), self.notes)

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
                'suggested_level': self.suggested_level(),
                'sizes': {level: len(serialize(self.snapshot(level))) for level in LEVELS},
                'notes': self.notes,
                'simbrief_configured': bool(self.settings.simbrief_user),
                'plan': self.plan.describe(self.settings.ofp_max_age_h)}
