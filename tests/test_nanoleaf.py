import json
import httpx
import pytest

from glareshield.drivers.nanoleaf import NanoleafDriver,NanoleafError
from glareshield.model import Device,LightState


@pytest.mark.parametrize('mode,effect',[('hs',''),('ct',''),('effect','Fixture scene')])
async def test_restore_original_color_mode_and_effect(mode,effect):
    calls=[]
    state={'on':{'value':False},'brightness':{'value':34},'hue':{'value':127},
        'sat':{'value':65},'ct':{'value':2800},'colorMode':mode}
    def handler(request):
        assert request.headers['Connection']=='close'
        calls.append(request)
        if request.method=='GET':
            return httpx.Response(200,text=json.dumps(state) if request.url.path.endswith('/state') else effect)
        return httpx.Response(204)
    driver=NanoleafDriver('fixture.invalid','fixture-token',transport=httpx.MockTransport(handler))
    device=Device(name='Fixture')
    try:
        snapshot=await driver.snapshot('a',device)
        await driver.apply('a',device,LightState(color=[255,0,0]))
        await driver.restore('a',device,snapshot)
        assert json.loads(calls[-1].content)=={'on':{'value':False}}
        restored=json.loads(calls[-2].content)
        assert restored['on']=={'value':False}
        assert restored['brightness']=={'value':34}
        if mode=='effect':
            assert json.loads(calls[-3].content)=={'select':effect}
            assert 'hue' not in restored
        elif mode=='ct':
            assert restored['ct']=={'value':2800} and 'hue' not in restored
        else:
            assert restored['hue']=={'value':127} and 'ct' not in restored
    finally:
        await driver.close()


async def test_token_never_appears_in_failure():
    driver=NanoleafDriver('fixture.invalid','fixture-sensitive-token',transport=httpx.MockTransport(lambda request:httpx.Response(401)))
    try:
        with pytest.raises(NanoleafError) as error:
            await driver.request('GET','state')
        assert 'fixture-sensitive-token' not in str(error.value)
    finally:
        await driver.close()


@pytest.mark.parametrize('off',[LightState(on=False),LightState(on=False,brightness=80,kelvin=2700),LightState(color=[0,0,0])])
async def test_off_does_not_reactivate_firmware_through_brightness(off):
    state={'on':True,'brightness':15,'ct':2700}
    def handler(request):
        body=json.loads(request.content)
        for key,value in body.items():
            state[key]=value['value']
        # Model the observed Essentials behaviour: brightness writes power on.
        if 'brightness' in body:
            state['on']=True
        return httpx.Response(204)
    driver=NanoleafDriver('fixture.invalid','fixture-token',transport=httpx.MockTransport(handler))
    try:
        await driver.apply('a',Device(name='Fixture'),off)
        assert state=={'on':False,'brightness':15,'ct':2700}
    finally:
        await driver.close()


async def test_restore_off_snapshot_after_firmware_power_on_side_effect():
    current={'on':True,'brightness':100,'ct':3000}
    original={'on':{'value':False},'brightness':{'value':34},'ct':{'value':2800},'colorMode':'ct'}
    def handler(request):
        body=json.loads(request.content)
        for key,value in body.items():
            current[key]=value['value']
        if 'brightness' in body:
            current['on']=True
        return httpx.Response(204)
    driver=NanoleafDriver('fixture.invalid','fixture-token',transport=httpx.MockTransport(handler))
    try:
        await driver.restore('a',Device(name='Fixture'),{'state':original,'effect':''})
        assert current=={'on':False,'brightness':34,'ct':2800}
    finally:
        await driver.close()
