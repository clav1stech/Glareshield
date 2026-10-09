from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from .config import Configuration, atomic_write
from .effects import condition_matches, render
from .model import BlinkEffect, Device, LightState, SoundEffect


class Bucket:
    def __init__(self, rate: float, now: float):
        self.rate = rate
        self.capacity = max(1,rate)
        self.tokens = self.capacity
        self.updated = now

    def take(self,now):
        self.tokens = min(self.capacity,self.tokens+max(0,now-self.updated)*self.rate)
        self.updated = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class Engine:
    def __init__(self, configuration: Configuration, drivers: dict, snapshot_path: Path, clock=time.monotonic):
        self.config = configuration
        self.drivers = drivers
        self.snapshot_path = snapshot_path
        self.clock = clock
        self.connected = False
        self.paused = False
        self.values: dict[str,float|bool|None] = {}
        self.active: dict[str,float] = {}
        self.snapshots = {}
        self.last: dict[str,LightState] = {}
        self.sent = {}
        self.winners: dict[str,str] = {}
        self.background_winners: dict[str,str] = {}
        self.errors: dict[str,str] = {}
        self.next_retry = {}
        self.failures = {}
        self.sound_sent = {}
        self.sound_tasks: dict[str,asyncio.Task] = {}
        self.sound_owners: dict[str,str] = {}
        self.buckets = {name:Bucket(configuration.settings.driver_rates.get(name,10),clock()) for name in drivers}
        self.lock = asyncio.Lock()

    def persist(self):
        atomic_write(self.snapshot_path,json.dumps(self.snapshots,ensure_ascii=False,indent=2))

    async def call(self,device,operation,timeout=None):
        try:
            result = await asyncio.wait_for(operation(),timeout or self.config.settings.timeout_s)
            self.errors.pop(device,None)
            self.next_retry.pop(device,None)
            self.failures.pop(device,None)
            return True,result
        except Exception as error:
            # Error messages and request URLs may contain credentials.
            self.errors[device] = type(error).__name__
            self.failures[device] = self.failures.get(device,0)+1
            self.next_retry[device] = self.clock()+min(self.config.settings.retry_max_s,self.config.settings.retry_initial_s*2**min(16,self.failures[device]-1))
            return False,None

    async def restore_one(self,identifier):
        entry = self.snapshots[identifier]
        device = Device.model_validate(entry["device"])
        driver = self.drivers.get(device.driver)
        if driver is None:
            self.errors[identifier] = "Pilote indisponible"
            return
        success,_ = await self.call(identifier,lambda:driver.restore(identifier,device,entry["state"]),timeout=self.config.settings.restore_timeout_s)
        if success:
            self.snapshots.pop(identifier,None)
            self.last.pop(identifier,None)
            self.winners.pop(identifier,None)
            try:
                self.persist()
            except OSError as error:
                self.snapshots[identifier] = entry
                self.errors[identifier] = type(error).__name__
                self.next_retry[identifier] = self.clock()+self.config.settings.retry_initial_s

    async def recover(self):
        async with self.lock:
            if self.snapshot_path.exists():
                self.snapshots = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            await asyncio.gather(*(self.restore_one(identifier) for identifier in list(self.snapshots)))

    def differs(self,identifier,state):
        previous = self.last.get(identifier)
        if previous is None:
            return True
        return (previous.on != state.on or previous.color != state.color or previous.kelvin != state.kelvin
                or previous.transition_ms != state.transition_ms
                or (previous.brightness != state.brightness and
                    abs(previous.brightness-state.brightness) >= self.config.settings.brightness_threshold))

    async def capture(self,identifier):
        device = self.config.devices[identifier]
        driver = self.drivers[device.driver]
        if identifier not in self.snapshots:
            success,snapshot = await self.call(identifier,lambda:driver.snapshot(identifier,device))
            if not success:
                return False
            self.snapshots[identifier] = {"device":device.model_dump(mode="json"),"state":snapshot}
            try:
                self.persist()
            except OSError as error:
                self.snapshots.pop(identifier,None)
                self.errors[identifier] = type(error).__name__
                self.next_retry[identifier] = self.clock()+self.config.settings.retry_initial_s
                return False
        return True

    async def apply_one(self,identifier,rule,state):
        device = self.config.devices[identifier]
        driver = self.drivers[device.driver]
        if not await self.capture(identifier):
            return
        success,_ = await self.call(identifier,lambda:driver.apply(identifier,device,state))
        if success:
            self.last[identifier] = state.model_copy(deep=True)
            self.sent[identifier] = self.clock()
            self.winners[identifier] = rule.id

    async def apply_group(self,driver_name,items):
        prepared = {}
        for identifier,(rule,state) in items.items():
            if await self.capture(identifier):
                prepared[identifier] = (self.config.devices[identifier],state)
        if not prepared:
            return
        try:
            failures = await asyncio.wait_for(self.drivers[driver_name].apply_batch(prepared),
                self.config.settings.timeout_s)
        except Exception as error:
            failures = {identifier:type(error).__name__ for identifier in prepared}
        for identifier,(device,state) in prepared.items():
            if identifier in failures:
                self.errors[identifier] = failures[identifier]
                self.failures[identifier] = self.failures.get(identifier,0)+1
                self.next_retry[identifier] = self.clock()+min(self.config.settings.retry_max_s,self.config.settings.retry_initial_s*2**min(16,self.failures[identifier]-1))
            else:
                self.errors.pop(identifier,None)
                self.next_retry.pop(identifier,None)
                self.failures.pop(identifier,None)
                self.last[identifier] = state.model_copy(deep=True)
                self.sent[identifier] = self.clock()
                self.winners[identifier] = items[identifier][0].id

    async def play_one(self,identifier,device,effect,key):
        success,_ = await self.call(identifier,lambda:self.drivers[device.driver].play(identifier,device,effect),timeout=self.config.settings.sound_timeout_s)
        if not success:
            self.sound_sent.pop(key,None)

    async def step(self):
        async with self.lock:
            now = self.clock()
            for driver in self.drivers.values():
                invalidated = getattr(driver,'invalidated',set())
                for identifier,device in self.config.devices.items():
                    if device.resource_id in invalidated:
                        self.last.pop(identifier,None)
                invalidated.clear()
            desired = {}
            backgrounds = {}
            overlays = {}
            sounds = {}
            matched = set()
            for rule in sorted(self.config.rules,key=lambda r:(-r.priority,r.id)):
                if not rule.enabled or (rule.requires_simulator and not self.connected) or (rule.suspend_when_paused and self.paused):
                    continue
                if not condition_matches(rule.condition,self.values):
                    continue
                matched.add(rule.id)
                start = self.active.setdefault(rule.id,now)
                configured_effect = self.config.effects[rule.effect]
                state = render(configured_effect,now-start,self.values.get(rule.source))
                if state is None:
                    continue
                for identifier in self.config.select(rule.targets):
                    device = self.config.devices[identifier]
                    if device.kind == "light" and isinstance(state,LightState):
                        if isinstance(configured_effect,BlinkEffect) and configured_effect.type=='blink':
                            high=((now-start)/configured_effect.period_s)%1 < configured_effect.duty
                            overlays.setdefault(identifier,(rule,state,high))
                        else:
                            backgrounds.setdefault(identifier,(rule,state))
                    elif device.kind == "audio":
                        effect = state if isinstance(state,SoundEffect) else self.config.effects.get(rule.sound)
                        if isinstance(effect,SoundEffect):
                            sounds.setdefault(identifier,(rule,effect,start))
            desired.update(backgrounds)
            self.background_winners={identifier:rule.id for identifier,(rule,state) in backgrounds.items()}
            for identifier,(rule,state,high) in overlays.items():
                background=backgrounds.get(identifier)
                desired[identifier]=(rule,state if high or background is None else background[1])
            for rule_id in set(self.active)-matched:
                self.active.pop(rule_id,None)
                for key in list(self.sound_sent):
                    if key[0] == rule_id:
                        self.sound_sent.pop(key,None)
            operations = []
            batches = {}
            for identifier in set(self.snapshots)-set(desired):
                if now >= self.next_retry.get(identifier,0):
                    operations.append(self.restore_one(identifier))
            for identifier,(rule,state) in sorted(desired.items(),key=lambda item:(-item[1][0].priority,self.sent.get(item[0],float("-inf")),item[0])):
                device = self.config.devices[identifier]
                if device.driver not in self.drivers:
                    self.errors[identifier] = "Pilote indisponible"
                    continue
                if not self.differs(identifier,state):
                    self.winners[identifier] = rule.id
                    continue
                if now < self.next_retry.get(identifier,0):
                    continue
                if hasattr(self.drivers[device.driver],'apply_batch'):
                    batches.setdefault(device.driver,{})[identifier] = (rule,state)
                    continue
                if not self.buckets[device.driver].take(now):
                    continue
                operations.append(self.apply_one(identifier,rule,state))
            for name,items in batches.items():
                if self.buckets[name].take(now):
                    operations.append(self.apply_group(name,items))
            if operations:
                await asyncio.gather(*operations)
            for identifier,task in self.sound_tasks.items():
                if not task.done() and (identifier not in sounds or self.sound_owners.get(identifier)!=sounds[identifier][0].id):
                    task.cancel()
            for identifier,(rule,effect,start) in sounds.items():
                key = (rule.id,identifier,start)
                last = self.sound_sent.get(key)
                if last is not None and (effect.repeat_s == 0 or now-last < effect.repeat_s):
                    continue
                pending = self.sound_tasks.get(identifier)
                device = self.config.devices[identifier]
                if device.driver not in self.drivers or (pending and not pending.done()) or now < self.next_retry.get(identifier,0):
                    continue
                self.sound_sent[key] = now
                self.sound_owners[identifier] = rule.id
                self.sound_tasks[identifier] = asyncio.create_task(self.play_one(identifier,device,effect,key))

    async def shutdown(self):
        async with self.lock:
            for task in self.sound_tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self.sound_tasks.values(),return_exceptions=True)
            await asyncio.gather(*(self.restore_one(identifier) for identifier in list(self.snapshots)))
            self.background_winners.clear()

    async def reconfigure(self,configuration):
        async with self.lock:
            await asyncio.gather(*(self.restore_one(identifier) for identifier in list(self.snapshots)))
            if self.snapshots:
                raise RuntimeError("Restauration incomplète ; conserver la configuration actuelle.")
            self.config = configuration
            self.active.clear()
            self.sound_sent.clear()
            self.buckets = {name:Bucket(configuration.settings.driver_rates.get(name,10),self.clock()) for name in self.drivers}
