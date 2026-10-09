from __future__ import annotations

import asyncio
import copy
import ssl
import time
from pathlib import Path

import httpx

from ..colors import rgb_to_xy
from ..model import Device, LightState


class HueError(RuntimeError):
    pass


class HueDriver:
    def __init__(self, host: str, key: str, certificate: Path, *, transport=None, rate=10):
        context = ssl.create_default_context(cafile=str(certificate)) if transport is None else True
        if isinstance(context,ssl.SSLContext):
            context.check_hostname = False
            context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        self.client = httpx.AsyncClient(base_url=f'https://{host}',verify=context,
            headers={'hue-application-key':key},timeout=5,trust_env=False,transport=transport)
        self.resources = {}
        self.groups = {}
        self.rate = rate
        self.last_command = 0.0
        self.rate_lock = asyncio.Lock()
        self.command_times = []
        self.scenes = []
        self.invalidated = set()
        self.restore_queue = {}
        self.restore_task = None
        self.diagnostics = []
        self.controlled = set()
        self.captured_scenes = {}

    async def request(self,method,path,body=None):
        for attempt in range(3):
            if method == 'PUT':
                async with self.rate_lock:
                    await asyncio.sleep(max(0,self.last_command+1/self.rate-time.monotonic()))
                    self.last_command = time.monotonic()
            try:
                response = await self.client.request(method,'/clip/v2/resource/'+path,json=body)
                response.raise_for_status()
                result = response.json()
                if result.get('errors'):
                    self.diagnostics.append({'path':path,'errors':result['errors']})
                    raise HueError('Le pont Hue a refusé la commande.')
                if method == 'PUT':
                    self.command_times.append(time.monotonic())
                return result.get('data',[])
            except (httpx.HTTPError,ValueError) as error:
                transient = isinstance(error,httpx.TransportError) or (
                    isinstance(error,httpx.HTTPStatusError) and error.response.status_code in (429,500,502,503,504))
                if not transient or attempt==2:
                    label=f'HTTP {error.response.status_code}' if isinstance(error,httpx.HTTPStatusError) else type(error).__name__
                    raise HueError(label) from None
                await asyncio.sleep(.2*(attempt+1))

    async def discover(self):
        lights = await self.request('GET','light')
        self.resources = {item['id']:item for item in lights}
        self.scenes = await self.request('GET','scene')
        rooms = await self.request('GET','room')
        zones = await self.request('GET','zone')
        self.groups = {}
        for group in rooms+zones:
            owners = {child['rid'] for child in group['children'] if child['rtype']=='device'}
            members = {light['id'] for light in lights if light['owner']['rid'] in owners}
            for service in group['services']:
                if service['rtype']=='grouped_light' and members:
                    self.groups[service['rid']] = members
        return [Device(name=light['metadata']['name'],driver='hue',resource_id=light['id']) for light in lights]

    async def snapshot(self,identifier,device):
        items = await self.request('GET','light/'+device.resource_id)
        if not items:
            raise HueError('Lampe introuvable.')
        raw = items[0]
        self.resources[device.resource_id] = raw
        dynamic_scene = None
        if raw.get('dynamics',{}).get('status') == 'dynamic_palette':
            self.scenes=await self.request('GET','scene')
            lights=await self.request('GET','light')
            self.resources.update({item['id']:item for item in lights})
            for scene in self.scenes:
                members = [a['target']['rid'] for a in scene.get('actions',[]) if a['target']['rtype']=='light']
                if device.resource_id in members and scene.get('status',{}).get('active')=='dynamic_palette':
                    if any(self.resources.get(member,{}).get('dynamics',{}).get('status')!='dynamic_palette'
                           and member not in self.controlled for member in members):
                        raise HueError('Scène dynamique partiellement modifiée : capture exacte indisponible.')
                    dynamic_scene = {'id':scene['id'],'members':members}
                    break
            if dynamic_scene is None:
                dynamic_scene=next((scene for scene in self.captured_scenes.values()
                    if device.resource_id in scene['members'] and all(
                        self.resources.get(member,{}).get('dynamics',{}).get('status')=='dynamic_palette'
                        or member in self.controlled for member in scene['members'])),None)
            if dynamic_scene is None:
                raise HueError('Scène dynamique active non identifiée.')
        if raw.get('timed_effects',{}).get('status','no_effect') != 'no_effect':
            raise HueError('Effet temporisé actif : capture exacte indisponible.')
        state = {'on':copy.deepcopy(raw['on'])}
        if 'dimming' in raw:
            state['dimming'] = {'brightness':raw['dimming']['brightness']}
        temperature = raw.get('color_temperature',{})
        if temperature.get('mirek_valid') and temperature.get('mirek') is not None:
            state['color_temperature'] = {'mirek':temperature['mirek']}
        elif 'color' in raw:
            state['color'] = {'xy':copy.deepcopy(raw['color']['xy'])}
        if 'gradient' in raw:
            state['gradient'] = {key:copy.deepcopy(raw['gradient'][key]) for key in ('points','mode') if key in raw['gradient']}
        if 'effects' in raw:
            state['effects'] = {'effect':raw['effects']['status']}
        if dynamic_scene:
            state['__dynamic_scene'] = dynamic_scene
            self.captured_scenes[device.resource_id]=dynamic_scene
        return state

    def payload(self,device,state:LightState):
        capabilities = self.resources.get(device.resource_id,{})
        body = {'on':{'on':state.on},'dimming':{'brightness':state.brightness},
                'dynamics':{'duration':state.transition_ms}}
        if state.color is not None:
            if state.color == [0,0,0]:
                body['on']['on'] = False
            else:
                x,y = rgb_to_xy(state.color,capabilities.get('color',{}).get('gamut'))
                body['color'] = {'xy':{'x':x,'y':y}}
        elif state.kelvin is not None:
            schema = capabilities.get('color_temperature',{}).get('mirek_schema',{})
            mirek = round(1000000/state.kelvin)
            body['color_temperature'] = {'mirek':max(schema.get('mirek_minimum',153),min(schema.get('mirek_maximum',500),mirek))}
        return body

    async def apply(self,identifier,device,state):
        await self.request('PUT','light/'+device.resource_id,self.payload(device,state))
        self.controlled.add(device.resource_id)

    async def restore(self,identifier,device,snapshot):
        future = asyncio.get_running_loop().create_future()
        self.restore_queue[identifier] = (device,snapshot,future)
        if self.restore_task is None or self.restore_task.done():
            self.restore_task = asyncio.create_task(self.flush_restore())
        await future

    async def flush_restore(self):
        await asyncio.sleep(.02)
        entries,self.restore_queue = self.restore_queue,{}
        scenes = {}
        failures = {}
        for identifier,(device,snapshot,future) in entries.items():
            try:
                await self.restore_request('light/'+device.resource_id,
                    {key:value for key,value in snapshot.items() if not key.startswith('__')})
                scene = snapshot.get('__dynamic_scene')
                if scene:
                    scenes[scene['id']] = scene
            except Exception as error:
                failures[identifier] = str(error) if isinstance(error,HueError) else type(error).__name__
        for scene_id,scene in scenes.items():
            try:
                await self.restore_request('scene/'+scene_id,{'recall':{'action':'dynamic_palette'}})
                self.invalidated.update(scene['members'])
            except Exception as error:
                for identifier,(device,snapshot,future) in entries.items():
                    if snapshot.get('__dynamic_scene',{}).get('id')==scene_id:
                        failures[identifier] = str(error) if isinstance(error,HueError) else type(error).__name__
        for identifier,(device,snapshot,future) in entries.items():
            if identifier not in failures and snapshot.get('__dynamic_scene'):
                try:
                    await self.restore_request('light/'+device.resource_id,
                        {key:snapshot[key] for key in ('on','dimming') if key in snapshot})
                except Exception as error:
                    failures[identifier] = str(error) if isinstance(error,HueError) else type(error).__name__
            if not future.done():
                if identifier in failures:
                    future.set_exception(HueError(failures[identifier]))
                else:
                    self.controlled.discard(device.resource_id)
                    self.captured_scenes.pop(device.resource_id,None)
                    future.set_result(None)
        if self.restore_queue:
            self.restore_task = asyncio.create_task(self.flush_restore())

    async def restore_request(self,path,body):
        for attempt in range(3):
            try:
                await self.request('PUT',path,body)
                return
            except HueError:
                if attempt==2:
                    raise
                await asyncio.sleep(.5*(attempt+1))

    async def identify(self,identifier,device):
        await self.request('PUT','light/'+device.resource_id,{'identify':{'action':'identify'}})

    async def apply_batch(self,items):
        remaining = dict(items)
        failures = {}
        for group,members in sorted(self.groups.items(),key=lambda item:-len(item[1])):
            lookup = {device.resource_id:key for key,(device,state) in remaining.items()}
            if not members <= set(lookup):
                continue
            keys = [lookup[member] for member in members]
            first_device,state = remaining[keys[0]]
            if any(remaining[key][1] != state for key in keys):
                continue
            body = self.payload(first_device,state)
            if state.color is not None and 'color' in body:
                point = (body['color']['xy']['x'],body['color']['xy']['y'])
                for _ in range(16):
                    for key in keys:
                        gamut = self.resources.get(remaining[key][0].resource_id,{}).get('color',{}).get('gamut')
                        if gamut:
                            from ..colors import clamp_xy
                            point = clamp_xy(point,gamut)
                body['color'] = {'xy':{'x':point[0],'y':point[1]}}
            try:
                await self.request('PUT','grouped_light/'+group,body)
                self.controlled.update(members)
            except HueError as error:
                failures.update({key:type(error).__name__ for key in keys})
            for key in keys:
                remaining.pop(key)
        for key,(device,state) in remaining.items():
            try:
                await self.apply(key,device,state)
            except HueError as error:
                failures[key] = type(error).__name__
        return failures

    async def close(self):
        await self.client.aclose()
