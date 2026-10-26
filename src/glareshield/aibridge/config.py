"""Private AI Bridge settings stored outside the lighting configuration."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from ..config import ConfigurationLoader, atomic_write
from ..model import StrictModel
from .catalog import GROUPS, STANDARD_KEYS, Entry

KEY_PATTERN = r'^[a-z][a-z0-9_]{0,47}$'


class LVarEntry(StrictModel):
    key: str = Field(pattern=KEY_PATTERN)
    name: str = Field(pattern=r'^(?:L:)?[A-Za-z0-9_. :-]{1,96}$')
    label: str = Field(min_length=1, max_length=80)
    group: str = 'fenix'
    unit: str | None = Field(default=None, max_length=24)
    level: Literal['essential', 'detailed'] = 'detailed'
    interval_ms: int = Field(default=1000, ge=250, le=60000)
    max_age_s: float = Field(default=5, gt=0, le=600)
    values: dict[str, str] = Field(default_factory=dict)
    validated: bool = False
    note: str | None = Field(default=None, max_length=200)

    def entry(self) -> Entry:
        return Entry(self.key, self.label, self.group if self.group in GROUPS else 'fenix', self.name,
                     'Number', self.unit, 'number', self.interval_ms, self.max_age_s, self.level, None,
                     'lvar', self.note, dict(self.values), self.validated)


class IVAOSettings(StrictModel):
    """Optional read-only IVAO network data, independent from the SimConnect reading."""
    enabled: bool = False
    # Distances to the declared centre of a position, by type: a centre covers far more than a tower.
    radius_aerodrome_nm: int = Field(default=30, ge=5, le=200)
    radius_approach_nm: int = Field(default=80, ge=10, le=300)
    radius_enroute_nm: int = Field(default=400, ge=50, le=1500)
    # IVAO allows one Whazzup download every 15 s at most.
    whazzup_interval_s: int = Field(default=60, ge=15, le=900)
    weather_interval_s: int = Field(default=600, ge=300, le=3600)
    airports: list[str] = Field(default_factory=list, max_length=6)
    # Overlay notice when a selected position connects or disconnects; off until the pilot asks for it.
    notifications: bool = False
    notification_seconds: int = Field(default=10, ge=3, le=60)

    @field_validator('airports')
    @classmethod
    def airports_valid(cls, value):
        codes = [code.strip().upper() for code in value]
        if any(not re.fullmatch(r'[A-Z0-9]{4}', code) for code in codes) or len(codes) != len(set(codes)):
            raise ValueError('Codes OACI invalides ou dupliqués.')
        return codes


class AIBridgeSettings(StrictModel):
    version: int = 1
    enabled: bool = False
    simbrief_user: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    simbrief_kind: Literal['username', 'userid'] = 'username'
    ofp_max_age_h: float = Field(default=12, gt=0, le=240)
    disabled: list[str] = Field(default_factory=list)
    validated: list[str] = Field(default_factory=list)
    lvars: list[LVarEntry] = Field(default_factory=list)
    ivao: IVAOSettings = Field(default_factory=IVAOSettings)

    @model_validator(mode='after')
    def references_valid(self):
        if self.version != 1:
            raise ValueError('Version des réglages AI Bridge inconnue.')
        keys = [lvar.key for lvar in self.lvars]
        if len(keys) != len(set(keys)) or set(keys) & STANDARD_KEYS:
            raise ValueError('Identifiants de variables dupliqués.')
        if any(key not in STANDARD_KEYS for key in [*self.disabled, *self.validated]):
            raise ValueError('Variable standard inconnue.')
        if self.simbrief_kind == 'userid' and self.simbrief_user and not self.simbrief_user.isdigit():
            raise ValueError('Un identifiant SimBrief numérique est attendu.')
        return self


def load_settings(path: Path) -> AIBridgeSettings:
    if not path.exists():
        return AIBridgeSettings()
    data = yaml.load(path.read_text(encoding='utf-8'), Loader=ConfigurationLoader)
    return AIBridgeSettings.model_validate(data or {})


def save_settings(path: Path, settings: AIBridgeSettings) -> AIBridgeSettings:
    checked = AIBridgeSettings.model_validate(settings.model_dump(mode='json'))
    atomic_write(path, yaml.safe_dump(checked.model_dump(mode='json'), allow_unicode=True, sort_keys=False))
    return checked
