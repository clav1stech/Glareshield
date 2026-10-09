from __future__ import annotations

import json
import re
import os
import tempfile
import time
from pathlib import Path

import yaml
from pydantic import Field, model_validator

from .model import (BlinkEffect, Condition, Controller, Device, Effect, LevelMapEffect,
                    Rule, Settings, SoundEffect, Source, StrictModel)


class ConfigurationLoader(yaml.SafeLoader):
    pass


ConfigurationLoader.yaml_implicit_resolvers = {
    key:[item for item in rules if item[0] != 'tag:yaml.org,2002:bool']
    for key,rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
ConfigurationLoader.add_implicit_resolver('tag:yaml.org,2002:bool',
    re.compile(r'^(?:true|false|True|False|TRUE|FALSE)$'),list('tTfF'))


def unique_mapping(loader,node,deep=False):
    result = {}
    for key_node,value_node in node.value:
        key = loader.construct_object(key_node,deep=deep)
        if key in result:
            raise ValueError('Clé de configuration dupliquée.')
        result[key] = loader.construct_object(value_node,deep=deep)
    return result


ConfigurationLoader.add_constructor('tag:yaml.org,2002:map',unique_mapping)


class Configuration(StrictModel):
    version: int = 1
    devices: dict[str, Device] = Field(default_factory=dict)
    controllers: dict[str, Controller] = Field(default_factory=dict)
    groups: dict[str, list[str]] = Field(default_factory=dict)
    scopes: dict[str, list[str]] = Field(default_factory=dict)
    active_scope: str
    sources: dict[str, Source] = Field(default_factory=dict)
    effects: dict[str, Effect] = Field(default_factory=dict)
    rules: list[Rule] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)

    def group_devices(self, identifier: str, trail: frozenset[str] = frozenset()) -> set[str]:
        if identifier in trail:
            raise ValueError("Cycle dans les groupes.")
        if identifier not in self.groups:
            raise ValueError("Groupe inconnu.")
        result = set()
        for member in self.groups[identifier]:
            if member.startswith("group:"):
                result |= self.group_devices(member[6:], trail | {identifier})
            elif member in self.devices:
                result.add(member)
            else:
                raise ValueError("Appareil inconnu dans un groupe.")
        return result

    def select(self, selectors: list[str]) -> set[str]:
        included, excluded = set(), set()
        for selector in selectors:
            target = excluded if selector.startswith("exclude:") else included
            if selector.startswith("exclude:"):
                selector = selector[8:]
            if selector.startswith("device:") and selector[7:] in self.devices:
                target.add(selector[7:])
            elif selector.startswith("group:"):
                target.update(self.group_devices(selector[6:]))
            elif selector == "scope:active":
                for group in self.scopes[self.active_scope]:
                    target.update(self.group_devices(group))
            else:
                raise ValueError("Sélecteur inconnu.")
        return included - excluded

    @model_validator(mode="after")
    def references_valid(self):
        if self.version != 1:
            raise ValueError("Version de configuration inconnue.")
        if self.active_scope not in self.scopes:
            raise ValueError("Portée active inconnue.")
        if set(self.devices) & set(self.groups):
            raise ValueError("Les identifiants de groupes et d’appareils doivent être distincts.")
        for device in self.devices.values():
            if device.driver!='mock':
                if device.controller not in self.controllers or self.controllers[device.controller].type!=device.driver:
                    raise ValueError('Contrôleur absent ou incompatible avec le pilote.')
        for identifier in self.groups:
            self.group_devices(identifier)
        for groups in self.scopes.values():
            for identifier in groups:
                self.group_devices(identifier)
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Identifiants de règles dupliqués.")
        def check_condition(condition: Condition):
            if condition.source is not None and condition.source not in self.sources:
                raise ValueError("Source de condition inconnue.")
            for child in condition.conditions:
                check_condition(child)
        for rule in self.rules:
            self.select(rule.targets)
            check_condition(rule.condition)
            if rule.source is not None and rule.source not in self.sources:
                raise ValueError("Source de règle inconnue.")
            if rule.effect not in self.effects:
                raise ValueError("Effet inconnu.")
            if rule.sound is not None and not isinstance(self.effects.get(rule.sound), SoundEffect):
                raise ValueError("Effet sonore inconnu.")
            if isinstance(self.effects[rule.effect], LevelMapEffect) and rule.source is None:
                raise ValueError("Une table de niveaux nécessite une source.")
        for effect in self.effects.values():
            if isinstance(effect,BlinkEffect) and 1 / effect.period_s > self.settings.max_flash_hz:
                raise ValueError("Cadence lumineuse au-dessus du plafond configuré.")
        return self


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix=path.name+".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(20):
            try:
                os.replace(filename,path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.05)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def load(path: Path) -> Configuration:
    return Configuration.model_validate(yaml.load(path.read_text(encoding="utf-8"),Loader=ConfigurationLoader))


def save(path: Path, configuration: Configuration) -> Configuration:
    checked = Configuration.model_validate(configuration.model_dump(mode="json"))
    content = yaml.safe_dump(checked.model_dump(mode="json"),allow_unicode=True,sort_keys=False)
    if path.exists():
        load(path)
        atomic_write(path.with_suffix(".last-valid.yaml"),path.read_text(encoding="utf-8"))
    atomic_write(path,content)
    return checked
