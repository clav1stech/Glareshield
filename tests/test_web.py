import re
import time
from pathlib import Path
from fastapi.testclient import TestClient

from glareshield.config import load
from glareshield.web import create_app


class FixtureRuntime:
    def __init__(self):
        self.config=load(Path(__file__).resolve().parents[1]/'examples/demo.yaml')
        self.started=False
        self.stopped=False
        self.suspended=False
        self.manual={}
        self.preview=None
    async def start(self):
        self.started=True
    async def stop(self):
        self.stopped=True
    async def configure(self,config):
        self.config=config
    def status(self):
        return {'connected':True}
    async def start_preview(self,config,rule,targets,effect,value):
        self.preview=(config,rule,targets,effect,value)
    async def stop_tests(self):
        self.preview=None
        self.manual.clear()
    async def test_source(self,identifier,value,duration):
        self.manual[identifier]=(value,time.monotonic()+duration)


def test_session_token_required_for_mutations_and_config_validated():
    runtime=FixtureRuntime()
    with TestClient(create_app(runtime)) as client:
        assert runtime.started
        assert client.post('/api/suspend',json={'suspended':True}).status_code==403
        html=client.get('/').text
        token=re.search("const TOKEN='([^']+)'",html).group(1)
        headers={'x-glareshield-token':token}
        assert client.post('/api/suspend',json={'suspended':True},headers=headers).status_code==200
        assert runtime.suspended
        bad=client.get('/api/config').json()
        bad['active_scope']='missing'
        assert client.put('/api/config',json=bad,headers=headers).status_code==400
        assert runtime.config.active_scope=='primary'
        good=client.get('/api/config').json()
        good['active_scope']='extended'
        assert client.put('/api/config',json=good,headers=headers).status_code==200
        assert runtime.config.active_scope=='extended'
    assert runtime.stopped


def test_foreign_host_rejected_and_source_test_bounded():
    runtime=FixtureRuntime()
    with TestClient(create_app(runtime)) as client:
        assert client.get('/',headers={'host':'foreign.invalid'}).status_code==400
        token=re.search("const TOKEN='([^']+)'",client.get('/').text).group(1)
        headers={'x-glareshield-token':token}
        assert client.post('/api/test/source',json={'source':'warning','value':1,'seconds':90},headers=headers).status_code==400
        assert client.post('/api/test/source',json={'source':'warning','value':1,'seconds':5},headers=headers).status_code==200
        assert runtime.manual['warning'][0]==1


def test_preview_is_authenticated_fixed_duration_and_does_not_save():
    runtime=FixtureRuntime()
    with TestClient(create_app(runtime)) as client:
        before=runtime.config.model_dump(mode='json')
        assert client.post('/api/test/preview',json={'rule':'warning'}).status_code==403
        token=re.search("const TOKEN='([^']+)'",client.get('/').text).group(1)
        headers={'x-glareshield-token':token}
        assert client.post('/api/test/preview',json={'rule':'warning','seconds':30},headers=headers).status_code==422
        r=client.post('/api/test/preview',json={'rule':'warning','targets':['device:light_a']},headers=headers)
        assert r.json()=={'ok':True,'seconds':3}
        assert runtime.preview[1]=='warning'
        assert runtime.config.model_dump(mode='json')==before
        assert client.post('/api/test/stop',json={},headers=headers).status_code==200
        assert runtime.preview is None
