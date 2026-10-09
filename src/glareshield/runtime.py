from __future__ import annotations

import asyncio
import json
import time
import logging
import uuid
from logging.handlers import RotatingFileHandler
from collections import deque
from pathlib import Path

import httpx

from .config import Configuration,load,save
from .discovery import network
from .drivers.hue import HueDriver
from .drivers.nanoleaf import NanoleafDriver
from .drivers.mock import MockDriver
from .drivers.routed import RoutedDriver
from .drivers.airplay import AirPlayDriver
from .sounds import generate
from .engine import Bucket,Engine
from .simulator import SimulatorSource
from .audio import AudioSource
from .keyboard import KeyboardSource
from .model import Condition,Source
from .effects import render


class Runtime:
    def __init__(self,root:Path,configuration_path:Path):
        self.root=root
        self.path=configuration_path
        self.config=load(configuration_path)
        self.engine=None
        self.sources=[]
        self.tasks=[]
        self.stopping=False
        self.suspended=False
        self.logs=deque(maxlen=300)
        self.manual={}
        self.controllers={}
        self.controller_errors={}
        self.live_values={}
        self.audio_source=None
        self.configuration_lock=asyncio.Lock()
        self.preview=None
        self.test_tasks=set()
        self.render_wake=asyncio.Event()
        log_path=self.root/'local/logs/glareshield.log'
        log_path.parent.mkdir(parents=True,exist_ok=True)
        self.logger=logging.getLogger('glareshield.'+str(id(self)))
        self.logger.setLevel(logging.INFO)
        self.logger.propagate=False
        handler=RotatingFileHandler(log_path,maxBytes=1_000_000,backupCount=3,encoding='utf-8')
        self.logger.addHandler(handler)

    def log(self,event,details=None):
        self.logs.append({'time':time.strftime('%H:%M:%S'),'event':event,'details':details})
        self.logger.info(json.dumps(self.logs[-1],ensure_ascii=False))

    async def make_drivers(self,addresses=None):
        if addresses is None:
            addresses=await network(cache_path=self.root/'local/discovery/inventory.json') if self.config.controllers else {}
        drivers={}
        for key,controller in self.config.controllers.items():
            if key in self.controllers:
                drivers.setdefault(controller.type,{})[key]=self.controllers[key]
                continue
            endpoint=addresses.get(controller.stable_id.casefold(),{})
            host=controller.host or endpoint.get('host')
            if not host and controller.type!='airplay':
                self.controller_errors[key]='Contrôleur non découvert'
                continue
            try:
                if controller.type=='hue':
                    keys=json.loads((self.root/'local/secrets/hue.json').read_text(encoding='utf-8'))
                    driver=HueDriver(host,keys[controller.stable_id]['username'],
                        self.root/'local/secrets'/f'hue-{controller.stable_id}.pem',
                        rate=self.config.settings.driver_rates.get('hue',10))
                elif controller.type=='nanoleaf':
                    keys=json.loads((self.root/'local/secrets/nanoleaf.json').read_text(encoding='utf-8'))
                    driver=NanoleafDriver(host,keys[controller.stable_id]['auth_token'],controller.port or endpoint.get('port',16021))
                else:
                    driver=AirPlayDriver(controller.stable_id,self.root/'local/sounds')
                self.controllers[key]=driver
                try:
                    await driver.discover()
                    self.controller_errors.pop(key,None)
                except Exception as error:
                    self.controller_errors[key]=type(error).__name__
                drivers.setdefault(controller.type,{})[key]=driver
            except Exception as error:
                self.controller_errors[key]=type(error).__name__
        result={name:RoutedDriver(items) for name,items in drivers.items()}
        if any(device.driver=='mock' for device in self.config.devices.values()):
            result['mock']=MockDriver(self.config.devices)
        return result

    def simulator_update(self,message):
        self.engine.connected=message['connected']
        self.engine.paused=message['paused']
        self.live_values.update(message['values'])

    async def start(self):
        self.stopping=False
        self.render_wake.clear()
        self.loop=asyncio.get_running_loop()
        generate(self.root/'local/sounds')
        drivers=await self.make_drivers()
        self.engine=Engine(self.config,drivers,self.root/'local/state/snapshots.json')
        await self.engine.recover()
        if any(source.type in ('lvar','simulator_state') for source in self.config.sources.values()):
            source=SimulatorSource(self.config.sources,self.simulator_update)
            self.sources.append(source)
            self.tasks.append(asyncio.create_task(source.run()))
        else:
            self.engine.connected=True
        if any(source.type=='audio_process' for source in self.config.sources.values()):
            self.audio_source=AudioSource(self.config.sources,self.live_values.update)
            self.sources.append(self.audio_source)
            self.tasks.append(asyncio.create_task(self.audio_source.run()))
        if any(source.type=='keyboard' for source in self.config.sources.values()):
            source=KeyboardSource(self.config.sources,self.live_values.update)
            self.sources.append(source)
            self.tasks.append(asyncio.create_task(source.run()))
        self.tasks.extend([asyncio.create_task(self.render_loop()),asyncio.create_task(self.resolve_loop())])
        self.log('Démarrage')

    async def render_loop(self):
        previous=None
        while not self.stopping:
            start=time.monotonic()
            if self.preview and start>=self.preview['until']:
                await self.end_preview(self.preview)
            self.engine.values.update(self.live_values)
            for key,(value,expiry) in list(self.manual.items()):
                if start>=expiry:
                    self.manual.pop(key)
                    self.engine.values[key]=self.live_values.get(key)
                else:
                    self.engine.values[key]=value
            try:
                if self.suspended and not self.preview:
                    await self.engine.shutdown()
                else:
                    await self.engine.step()
                state=(tuple(sorted(self.engine.winners.items())),tuple(sorted(self.engine.errors.items())),self.engine.connected,self.engine.paused)
                if state!=previous:
                    self.log('État du moteur',{'connected':self.engine.connected,'paused':self.engine.paused,
                        'winners':dict(self.engine.winners),'errors':dict(self.engine.errors)})
                    previous=state
            except Exception as error:
                self.log('Erreur du moteur',type(error).__name__)
            try:
                await asyncio.wait_for(self.render_wake.wait(),max(.01,1/self.engine.config.settings.render_hz-(time.monotonic()-start)))
            except TimeoutError:
                pass
            self.render_wake.clear()

    def schedule_test(self,coroutine):
        task=asyncio.create_task(coroutine)
        self.test_tasks.add(task)
        task.add_done_callback(self.test_tasks.discard)

    async def expire_preview(self,preview):
        await asyncio.sleep(max(0,preview['until']-time.monotonic()))
        async with self.configuration_lock:
            await self.end_preview(preview)

    async def test_source(self,identifier,value,duration):
        async with self.configuration_lock:
            entry=(value,time.monotonic()+duration)
            async with self.engine.lock:
                self.manual[identifier]=entry
                self.engine.values[identifier]=value
            self.schedule_test(self.expire_source(identifier,entry))
            self.render_wake.set()
            if not self.suspended or self.preview:
                await self.engine.step()

    async def expire_source(self,identifier,entry):
        await asyncio.sleep(max(0,entry[1]-time.monotonic()))
        async with self.configuration_lock:
            async with self.engine.lock:
                if self.manual.get(identifier) is not entry:
                    return
                self.manual.pop(identifier)
                self.engine.values[identifier]=self.live_values.get(identifier)
            if not self.suspended or self.preview:
                await self.engine.step()

    def set_rates(self,configuration):
        self.engine.buckets={name:Bucket(configuration.settings.driver_rates.get(name,10),time.monotonic())
                             for name in self.engine.drivers}
        for key,driver in self.controllers.items():
            if hasattr(driver,'rate'):
                driver.rate=configuration.settings.driver_rates.get(self.config.controllers[key].type,10)

    async def start_preview(self,configuration,rule_id,targets=None,effect_id=None,value=1):
        async with self.configuration_lock:
            candidate=Configuration.model_validate(configuration.model_dump(mode='json'))
            if any(getattr(candidate,key)!=getattr(self.config,key) for key in ('devices','controllers','sources')):
                raise ValueError('Enregistrer les changements de connexion ou de source avant de tester leur sortie.')
            rule=next((r.model_copy(deep=True) for r in candidate.rules if r.id==rule_id),None)
            if rule is None:
                raise ValueError('Fonction inconnue.')
            rule.id='preview_'+uuid.uuid4().hex
            rule.enabled=True
            rule.priority+=1
            rule.condition=Condition()
            rule.requires_simulator=False
            rule.suspend_when_paused=False
            if targets is not None:
                rule.targets=targets
            if effect_id is not None:
                rule.effect=effect_id
                rule.sound=None
            rule.source=rule.id
            candidate.sources[rule.source]=Source(type='mock')
            if self.suspended:
                for existing in candidate.rules:
                    existing.enabled=False
            candidate.rules.append(rule)
            candidate=Configuration.model_validate(candidate.model_dump(mode='json'))
            if render(candidate.effects[rule.effect],0,value) is None:
                raise ValueError('Palier inconnu : choisir une valeur définie dans cet effet.')
            devices=candidate.select(rule.targets)
            kind='audio' if candidate.effects[rule.effect].type=='sound' else 'light'
            if not any(candidate.devices[id].kind==kind for id in devices):
                raise ValueError('Sélectionner au moins une sortie audio.' if kind=='audio' else 'Sélectionner au moins une lampe.')
            async with self.engine.lock:
                if self.preview:
                    self.engine.values.pop(self.preview['id'],None)
                self.engine.config=candidate
                self.engine.values[rule.source]=value
                self.preview={'id':rule.id,'rule':rule_id,'until':time.monotonic()+3}
                self.set_rates(candidate)
                self.schedule_test(self.expire_preview(self.preview))
                self.render_wake.set()
            await self.engine.step()
            self.log('Aperçu de 3 secondes',rule_id)

    async def end_preview(self,expected=None):
        async with self.engine.lock:
            if not self.preview or (expected is not None and self.preview is not expected):
                return
            self.engine.values.pop(self.preview['id'],None)
            self.engine.config=self.config
            self.preview=None
            self.set_rates(self.config)
        if self.suspended:
            await self.engine.shutdown()
        else:
            await self.engine.step()

    async def stop_tests(self):
        async with self.configuration_lock:
            async with self.engine.lock:
                for key in self.manual:
                    self.engine.values[key]=self.live_values.get(key)
                self.manual.clear()
            await self.end_preview()
            if self.suspended:
                await self.engine.shutdown()
            else:
                await self.engine.step()

    async def resolve_loop(self):
        while not self.stopping:
            last_resolution=time.monotonic()
            while time.monotonic()-last_resolution<self.config.settings.discovery_interval_s:
                if self.stopping:
                    return
                await asyncio.sleep(.1)
            try:
                addresses=await network(cache_path=self.root/'local/discovery/inventory.json')
                available=await self.make_drivers(addresses)
                for name,driver in available.items():
                    if name not in self.engine.drivers:
                        self.engine.drivers[name]=driver
                        self.engine.buckets[name]=Bucket(self.config.settings.driver_rates.get(name,10),time.monotonic())
                    elif isinstance(driver,RoutedDriver):
                        self.engine.drivers[name].controllers=driver.controllers
                for key,controller in self.config.controllers.items():
                    driver=self.controllers.get(key)
                    endpoint=addresses.get(controller.stable_id.casefold())
                    if driver is not None and endpoint and not controller.host and hasattr(driver,'client'):
                        host=endpoint['host']
                        if driver.client.base_url.host!=host:
                            url=driver.client.base_url.copy_with(host=host)
                            driver.client.base_url=url
                            await driver.discover()
                            self.log('Adresse du contrôleur actualisée',key)
            except Exception as error:
                self.log('Découverte indisponible',type(error).__name__)

    async def stop(self):
        self.stopping=True
        self.render_wake.set()
        self.preview=None
        for task in list(self.test_tasks):
            task.cancel()
        await asyncio.gather(*list(self.test_tasks),return_exceptions=True)
        self.test_tasks.clear()
        for source in self.sources:
            source.stop()
        if self.tasks:
            await asyncio.gather(*self.tasks,return_exceptions=True)
        self.tasks=[]
        self.sources=[]
        if self.engine:
            await self.engine.shutdown()
            for driver in self.engine.drivers.values():
                if hasattr(driver,'close'):
                    await driver.close()
        self.controllers={}
        self.log('Arrêt et restauration',len(self.engine.snapshots) if self.engine else 0)

    async def configure(self,configuration):
        async with self.configuration_lock:
            await self.configure_locked(configuration)

    async def change_scope(self,scope):
        async with self.configuration_lock:
            await self.end_preview()
            candidate=self.config.model_copy(deep=True)
            candidate.active_scope=scope
            checked=Configuration.model_validate(candidate.model_dump(mode='json'))
            async with self.engine.lock:
                self.config=save(self.path,checked)
                self.engine.config=self.config
            await self.engine.step()
            self.log('Portée modifiée',scope)

    async def configure_locked(self,configuration):
        configuration=Configuration.model_validate(configuration.model_dump(mode='json'))
        await self.end_preview()
        if all(getattr(configuration,key)==getattr(self.config,key)
               for key in ('devices','controllers','sources')):
            async with self.engine.lock:
                previous=self.config
                self.config=save(self.path,configuration)
                self.engine.config=self.config
                if previous.settings.driver_rates!=self.config.settings.driver_rates:
                    self.set_rates(self.config)
            if not self.suspended:
                await self.engine.step()
            self.log('Configuration appliquée sans reconnexion')
            return
        await self.stop()
        if self.engine.snapshots:
            await self.start()
            raise RuntimeError('Restauration incomplète ; modification refusée.')
        try:
            self.config=save(self.path,configuration)
        except Exception:
            await self.start()
            raise
        self.controller_errors={}
        self.live_values={}
        self.manual={}
        await self.start()

    def status(self):
        return {'connected':self.engine.connected,'paused':self.engine.paused,'suspended':self.suspended,
            'test_remaining_s':max([0,*[max(0,expiry-time.monotonic()) for _,expiry in self.manual.values()],
                                    max(0,self.preview['until']-time.monotonic()) if self.preview else 0]),
            'preview':{'rule':self.preview['rule'],'remaining_s':max(0,self.preview['until']-time.monotonic())} if self.preview else None,
            'scope':self.config.active_scope,'values':self.engine.values,'winners':self.engine.winners,
            'backgrounds':self.engine.background_winners,
            'source_errors':{type(source).__name__:source.error for source in self.sources if getattr(source,'error',None)},
            'audio_levels':self.audio_source.levels if self.audio_source else {},
            'errors':self.engine.errors,'controller_errors':self.controller_errors,
            'snapshots':len(self.engine.snapshots),'logs':list(self.logs)}
