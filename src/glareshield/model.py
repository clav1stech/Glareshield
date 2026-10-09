from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class LightState(StrictModel):
    on: bool = True
    brightness: float = Field(default=100, ge=0, le=100)
    color: list[int] | None = Field(default=None, min_length=3, max_length=3)
    kelvin: int | None = Field(default=None, ge=1000, le=10000)
    transition_ms: int = Field(default=0, ge=0, le=60000)

    @model_validator(mode="after")
    def valid_color(self):
        if self.color is not None and any(not 0 <= channel <= 255 for channel in self.color):
            raise ValueError("Couleur RVB hors limites.")
        if self.color is not None and self.kelvin is not None:
            raise ValueError("Choisir une couleur ou une température.")
        return self


class Device(StrictModel):
    name: str
    driver: str = "mock"
    kind: Literal["light", "audio"] = "light"
    controller: str | None = None
    resource_id: str | None = None
    stable_id: str | None = None
    initial_state: LightState = Field(default_factory=LightState)


class Controller(StrictModel):
    type: Literal['hue','nanoleaf','airplay']
    stable_id: str = Field(pattern=r'^[A-Za-z0-9:_-]+$')
    host: str | None = None
    port: int | None = Field(default=None,ge=1,le=65535)


class Source(StrictModel):
    type: Literal["mock", "lvar", "audio_process", "simulator_state", "keyboard"] = "mock"
    name: str | None = None
    poll_ms: int = Field(default=100, ge=50, le=60000)
    process_names: list[str] = Field(default_factory=list)
    threshold: float = Field(default=.02, ge=0, le=1)
    min_ms: int = Field(default=300, ge=0)
    cooldown_s: float = Field(default=10, ge=0)
    hold_s: float = Field(default=5,gt=0,le=60)
    key_code: int | None = Field(default=None,ge=1,le=254)

    @model_validator(mode='after')
    def keyboard_binding(self):
        if self.type=='keyboard' and self.key_code is None:
            raise ValueError('Code de touche requis pour une source clavier.')
        if self.type in ('lvar','simulator_state') and not self.name:
            raise ValueError('Nom requis pour une source simulateur.')
        if self.type=='simulator_state' and self.name not in ('paused','running'):
            raise ValueError('État simulateur attendu : paused ou running.')
        return self


class Condition(StrictModel):
    source: str | None = None
    op: Literal["always", "eq", "ne", "gt", "ge", "lt", "le", "active", "all", "any"] = "always"
    value: float | bool | None = None
    conditions: list[Condition] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_shape(self):
        if self.op in ("all", "any"):
            if not self.conditions or self.source is not None or self.value is not None:
                raise ValueError("Une condition composée nécessite des sous-conditions seules.")
        elif self.op == "always":
            if self.source is not None or self.value is not None or self.conditions:
                raise ValueError("La condition always ne prend pas de paramètre.")
        elif self.source is None or self.conditions or (self.op != "active" and self.value is None):
            raise ValueError("Condition simple incomplète.")
        return self


class StaticEffect(StrictModel):
    type: Literal["static"]
    state: LightState


class BlinkEffect(StrictModel):
    type: Literal["blink", "pulse"]
    color: list[int] = Field(min_length=3, max_length=3)
    period_s: float = Field(gt=0)
    high: float = Field(default=100, ge=1, le=100)
    low: float = Field(default=15, ge=1, le=100)
    duty: float = Field(default=.5, gt=0, lt=1)
    cycles: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_levels(self):
        LightState(color=self.color)
        if self.low > self.high:
            raise ValueError("La luminosité basse dépasse la luminosité haute.")
        return self


class LevelMapEffect(StrictModel):
    type: Literal["level_map"]
    map: dict[str, LightState]


class SoundEffect(StrictModel):
    type: Literal["sound"]
    file: str
    volume: float = Field(default=.5, ge=0, le=1)
    repeat_s: float = Field(default=0, ge=0)


Effect = Annotated[StaticEffect | BlinkEffect | LevelMapEffect | SoundEffect, Field(discriminator="type")]


class Rule(StrictModel):
    id: str
    enabled: bool = True
    priority: int = 0
    source: str | None = None
    condition: Condition = Field(default_factory=Condition)
    effect: str
    targets: list[str] = Field(min_length=1)
    sound: str | None = None
    requires_simulator: bool = True
    suspend_when_paused: bool = False


class Settings(StrictModel):
    render_hz: float = Field(default=10, gt=0, le=50)
    max_flash_hz: float = Field(default=2, gt=0, le=2)
    brightness_threshold: float = Field(default=3, ge=0, le=100)
    driver_rates: dict[str, float] = Field(default_factory=lambda: {"mock": 100})
    timeout_s: float = Field(default=5, gt=0, le=60)

    @model_validator(mode="after")
    def rates_valid(self):
        if any(rate <= 0 for rate in self.driver_rates.values()):
            raise ValueError("Les cadences des pilotes doivent être positives.")
        return self
