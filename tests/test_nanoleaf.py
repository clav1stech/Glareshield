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
        restored=json.loads(calls[-1].content)
        assert restored['on']=={'value':False}
        assert restored['brightness']=={'value':34}
        if mode=='effect':
            assert json.loads(calls[-2].content)=={'select':effect}
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
