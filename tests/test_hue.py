import asyncio
import json
import httpx
import pytest

from glareshield.colors import rgb_to_hs,rgb_to_xy
from glareshield.drivers.hue import HueDriver,HueError
from glareshield.model import Device,LightState


def light(identifier):
    return {'id':identifier,'owner':{'rid':'fixture-owner'},'metadata':{'name':'Fixture'},
            'on':{'on':False},'dimming':{'brightness':25},
            'color':{'xy':{'x':.3,'y':.3}},
            'color_temperature':{'mirek':400,'mirek_valid':True},
            'effects':{'status':'no_effect'}}


async def test_snapshot_apply_restore_and_identify(tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        if request.method=='GET':
            return httpx.Response(200,json={'data':[light('fixture-a')],'errors':[]})
        return httpx.Response(200,json={'data':[],'errors':[]})
    driver = HueDriver('fixture.invalid','fixture-key',tmp_path/'unused.pem',transport=httpx.MockTransport(handler),rate=1000)
    device = Device(name='Fixture',driver='hue',resource_id='fixture-a')
    try:
        snapshot = await driver.snapshot('a',device)
        assert snapshot['on']=={'on':False}
        assert snapshot['color_temperature']=={'mirek':400}
        assert 'color' not in snapshot
        await driver.apply('a',device,LightState(color=[255,0,0],brightness=70))
        await driver.identify('a',device)
        await driver.restore('a',device,snapshot)
        import json
        assert json.loads(requests[-1].content)==snapshot
        assert requests[-2].url.path.endswith('/light/fixture-a')
        assert requests[0].headers['hue-application-key']=='fixture-key'
    finally:
        await driver.close()


@pytest.mark.parametrize('status',[401,429,500])
async def test_http_errors_do_not_expose_credentials(tmp_path,status):
    driver = HueDriver('fixture.invalid','fixture-sensitive-key',tmp_path/'unused.pem',
        transport=httpx.MockTransport(lambda request:httpx.Response(status)),rate=1000)
    try:
        with pytest.raises(HueError) as caught:
            await driver.request('GET','light')
        assert 'fixture-sensitive-key' not in str(caught.value)
    finally:
        await driver.close()


async def test_timeout_and_api_error(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout('fixture-sensitive-key')
    driver = HueDriver('fixture.invalid','fixture-sensitive-key',tmp_path/'unused.pem',transport=httpx.MockTransport(timeout))
    try:
        with pytest.raises(HueError,match='ReadTimeout'):
            await driver.request('GET','light')
    finally:
        await driver.close()


async def test_group_command_only_for_complete_homogeneous_membership(tmp_path):
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200,json={'data':[],'errors':[]})
    driver=HueDriver('fixture.invalid','fixture-key',tmp_path/'unused.pem',transport=httpx.MockTransport(handler),rate=1000)
    a=Device(name='A',driver='hue',resource_id='fixture-a')
    b=Device(name='B',driver='hue',resource_id='fixture-b')
    driver.groups={'fixture-group':{'fixture-a','fixture-b'}}
    state=LightState(color=[255,0,0])
    try:
        assert await driver.apply_batch({'a':(a,state),'b':(b,state)}) == {}
        assert paths==['/clip/v2/resource/grouped_light/fixture-group']
        paths.clear()
        await driver.apply_batch({'a':(a,state)})
        assert paths==['/clip/v2/resource/light/fixture-a']
    finally:
        await driver.close()


def test_color_reference_values():
    assert rgb_to_hs([255,0,0])==(0,100)
    assert rgb_to_hs([0,255,0])==(120,100)
    assert rgb_to_hs([0,0,255])==(240,100)
    assert rgb_to_xy([255,0,0])==pytest.approx((.7006,.2993),abs=.0002)
    assert rgb_to_xy([0,0,0])==(0,0)


async def test_dynamic_scene_recalled_once_and_invalidates_all_members(tmp_path):
    calls=[]
    def handler(request):
        calls.append((request.url.path,json.loads(request.content)))
        return httpx.Response(200,json={'data':[],'errors':[]})
    driver=HueDriver('fixture.invalid','fixture-key',tmp_path/'unused.pem',transport=httpx.MockTransport(handler),rate=1000)
    scene={'id':'fixture-scene','members':['fixture-a','fixture-b']}
    snapshot={'on':{'on':True},'dimming':{'brightness':40},'__dynamic_scene':scene}
    try:
        await asyncio.gather(*(driver.restore(key,Device(name=key,resource_id=key),snapshot) for key in scene['members']))
        recalls=[body for path,body in calls if path.endswith('/scene/fixture-scene')]
        assert recalls==[{'recall':{'action':'dynamic_palette'}}]
        assert driver.invalidated==set(scene['members'])
        assert all('__dynamic_scene' not in body for path,body in calls)
    finally:
        await driver.close()


async def test_dynamic_background_can_be_captured_when_other_members_are_owned(tmp_path):
    a,b=light('fixture-a'),light('fixture-b')
    for item in (a,b):
        item['dynamics']={'status':'dynamic_palette'}
    scene={'id':'fixture-scene','status':{'active':'dynamic_palette'},
        'actions':[{'target':{'rid':key,'rtype':'light'}} for key in ('fixture-a','fixture-b')]}
    def handler(request):
        path=request.url.path
        if request.method=='PUT':
            a['dynamics']['status']='none'
            scene['status']['active']='inactive'
            return httpx.Response(200,json={'data':[],'errors':[]})
        data=[scene] if path.endswith('/scene') else [a] if path.endswith('/fixture-a') else [b] if path.endswith('/fixture-b') else [a,b]
        return httpx.Response(200,json={'data':data,'errors':[]})
    driver=HueDriver('fixture.invalid','fixture-key',tmp_path/'unused.pem',transport=httpx.MockTransport(handler),rate=1000)
    da,db=Device(name='A',resource_id='fixture-a'),Device(name='B',resource_id='fixture-b')
    try:
        await driver.snapshot('a',da)
        await driver.apply('a',da,LightState(on=False))
        snapshot=await driver.snapshot('b',db)
        assert snapshot['__dynamic_scene']['id']=='fixture-scene'
    finally:
        await driver.close()
