"""Private AI Bridge settings stored outside the lighting configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

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


class AIBridgeSettings(StrictModel):
    version: int = 1
    enabled: bool = False
    simbrief_user: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_.-]{1,64}$')
    simbrief_kind: Literal['username', 'userid'] = 'username'
    ofp_max_age_h: float = Field(default=12, gt=0, le=240)
    disabled: list[str] = Field(default_factory=list)
    validated: list[str] = Field(default_factory=list)
    lvars: list[LVarEntry] = Field(default_factory=list)

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
