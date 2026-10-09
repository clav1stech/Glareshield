import re
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
    async def start(self):
        self.started=True
    async def stop(self):
        self.stopped=True
    async def configure(self,config):
        self.config=config
    def status(self):
        return {'connected':True}


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
