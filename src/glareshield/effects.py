import math
import operator

from .model import (BlinkEffect, Condition, LevelMapEffect, LightState,
                    SoundEffect, StaticEffect)


def condition_matches(condition: Condition, values: dict) -> bool:
    if condition.op == "always":
        return True
    if condition.op in ("all","any"):
        matches = (condition_matches(child,values) for child in condition.conditions)
        return all(matches) if condition.op == "all" else any(matches)
    actual = values.get(condition.source)
    if actual is None:
        return False
    if condition.op == "active":
        return bool(actual)
    operations = {"eq":operator.eq,"ne":operator.ne,"gt":operator.gt,
                  "ge":operator.ge,"lt":operator.lt,"le":operator.le}
    return operations[condition.op](actual,condition.value)


def render(effect, elapsed: float, value=None) -> LightState | SoundEffect | None:
    if isinstance(effect,StaticEffect):
        return effect.state
    if isinstance(effect,SoundEffect):
        return effect
    if isinstance(effect,LevelMapEffect):
        if value is None:
            return None
        key = str(int(value)) if isinstance(value,(int,float)) and int(value) == value else str(value)
        return effect.map.get(key)
    if isinstance(effect,BlinkEffect):
        if effect.cycles is not None and elapsed >= effect.period_s * effect.cycles:
            return None
        phase = (elapsed / effect.period_s) % 1
        if effect.type == "blink":
            brightness = effect.high if phase < effect.duty else effect.low
        else:
            brightness = effect.low + (effect.high-effect.low)*(1-math.cos(phase*2*math.pi))/2
        return LightState(color=effect.color,brightness=brightness)
    raise ValueError("Effet non pris en charge.")
