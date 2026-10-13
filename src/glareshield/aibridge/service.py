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
from .context import build_context, chat_text, serialize
from .scenario import PHASES, ScenarioPlayer, phase
from .simbrief import FlightPlanStore, parse_ofp
from .telemetry import TelemetryStore, qualify


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

    # Read-only views, intended to back future MCP tools one to one

    def snapshot(self, level: str = 'essential') -> dict:
        """get_flight_snapshot"""
        return build_context(level, self.entries(), self.store(), self.plan.plan,
                             self.plan.describe(self.settings.ofp_max_age_h), self.clock())

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

    def chat(self, level: str = 'essential') -> str:
        return chat_text(self.snapshot(level))

    def export(self, level: str = 'essential') -> Path:
        document = self.snapshot(level)
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
                'essential_chars': len(serialize(self.snapshot('essential'))),
                'simbrief_configured': bool(self.settings.simbrief_user),
                'plan': self.plan.describe(self.settings.ofp_max_age_h)}
