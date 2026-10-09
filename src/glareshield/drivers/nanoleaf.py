from __future__ import annotations

import asyncio
import httpx

from ..colors import rgb_to_hs
from ..model import Device, LightState


class NanoleafError(RuntimeError):
    pass


class NanoleafDriver:
    def __init__(self,host,token,port=16021,*,transport=None):
        self.client=httpx.AsyncClient(base_url=f'http://{host}:{port}/api/v1/{token}/',
            headers={'Connection':'close'},timeout=3,trust_env=False,transport=transport)
        self.lock=asyncio.Lock()
        self.capabilities={}

    async def request(self,method,path,body=None,text=False):
        async with self.lock:
            try:
                response=await self.client.request(method,path,json=body)
                response.raise_for_status()
                if text:
                    return response.text.strip().strip('"')
                return response.json() if response.content else None
            except (httpx.HTTPError,ValueError) as error:
                # Never include the URL: the token is a path component.
                raise NanoleafError(type(error).__name__) from None

    async def discover(self):
        # Some Essentials firmware rejects a trailing slash on the root.
        try:
            response=await self.client.get(str(self.client.base_url).rstrip('/'))
            response.raise_for_status()
            info=response.json()
        except (httpx.HTTPError,ValueError) as error:
            raise NanoleafError(type(error).__name__) from None
        self.capabilities=await self.request('GET','state')
        return [Device(name=info['name'],driver='nanoleaf',resource_id=info.get('serialNo'))]

    async def snapshot(self,identifier,device):
        state=await self.request('GET','state')
        effect=await self.request('GET','effects/select',text=True)
        if state.get('colorMode') not in ('hs','ct','effect'):
            raise NanoleafError('Mode couleur non restaurable.')
        if state.get('colorMode')=='effect' and not effect:
            raise NanoleafError('Effet actif non identifié.')
        self.capabilities=state
        return {'state':state,'effect':effect}

    def bound(self,key,value):
        bounds=self.capabilities.get(key,{})
        return max(bounds.get('min',0),min(bounds.get('max',value),value))

    async def apply(self,identifier,device,state:LightState):
        body={'on':{'value':state.on},'brightness':{'value':self.bound('brightness',round(state.brightness))}}
        if state.color is not None:
            if state.color==[0,0,0]:
                body['on']['value']=False
            else:
                hue,saturation=rgb_to_hs(state.color)
                body['hue']={'value':hue}
                body['sat']={'value':saturation}
        elif state.kelvin is not None:
            body['ct']={'value':self.bound('ct',state.kelvin)}
        await self.request('PUT','state',body)

    async def restore(self,identifier,device,snapshot):
        state=snapshot['state']
        body={key:{'value':state[key]['value']} for key in ('on','brightness')}
        if state['colorMode']=='effect':
            await self.request('PUT','effects',{'select':snapshot['effect']})
        else:
            keys=('ct',) if state['colorMode']=='ct' else ('hue','sat')
            body.update({key:{'value':state[key]['value']} for key in keys})
        await self.request('PUT','state',body)

    async def identify(self,identifier,device):
        original=await self.snapshot(identifier,device)
        try:
            await self.apply(identifier,device,LightState(color=[255,255,255],brightness=50))
            await asyncio.sleep(.5)
        finally:
            await self.restore(identifier,device,original)

    async def close(self):
        await self.client.aclose()
