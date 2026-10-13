import re
from pathlib import Path

from fastapi.testclient import TestClient

from glareshield.aibridge.service import AIBridge
from glareshield.config import load
from glareshield.web import create_app


class FixtureRuntime:
    def __init__(self, root):
        self.root = root
        self.config = load(Path(__file__).resolve().parents[1]/'examples/demo.yaml')
        self.ai = AIBridge(root)
        self.changes = 0
        import asyncio
        self.configuration_lock = asyncio.Lock()

    async def start(self):
        pass

    async def stop(self):
        pass

    async def ai_settings_changed(self):
        self.changes += 1

    def status(self):
        return {'connected': True}


def client_and_headers(tmp_path):
    runtime = FixtureRuntime(tmp_path)
    client = TestClient(create_app(runtime))
    token = re.search("const TOKEN='([^']+)'", client.get('/').text).group(1)
    return runtime, client, {'x-glareshield-token': token}


def test_flight_data_requires_session_token_even_for_reads(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    with client:
        for path in ('status', 'context', 'chat', 'variables', 'plan', 'settings'):
            assert client.get('/api/ai/'+path).status_code == 403
            assert client.get('/api/ai/'+path, headers=headers).status_code == 200
        assert client.get('/api/ai/context', headers={**headers, 'host': 'foreign.invalid'}).status_code == 400


def test_static_assets_are_whitelisted(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    with client:
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/static/ai.js').headers['content-type'].startswith('text/javascript')
        assert client.get('/static/app.css').status_code == 200
        assert client.get('/static/index.html').status_code == 404
        assert client.get('/static/..%2Fweb.py').status_code == 404


def test_settings_scenario_plan_and_export_flow(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    with client:
        settings = client.get('/api/ai/settings', headers=headers).json()
        assert settings['enabled'] is False
        bad = client.put('/api/ai/settings', json={**settings, 'disabled': ['unknown']}, headers=headers)
        assert bad.status_code == 400 and runtime.changes == 0
        assert client.put('/api/ai/settings', json={**settings, 'enabled': True,
                          'simbrief_user': 'demo-pilot'}, headers=headers).status_code == 200
        assert runtime.changes == 1 and (tmp_path/'local/ai-bridge.yaml').exists()
        assert client.post('/api/ai/scenario', json={'active': True, 'phase': 'cruise'}, headers=headers).status_code == 200
        assert client.post('/api/ai/scenario', json={'active': True, 'phase': 'unknown'}, headers=headers).status_code == 422
        assert client.post('/api/ai/simbrief/demo', json={}, headers=headers).json()['plan']['nature'] == 'planned'
        context = client.get('/api/ai/context?level=detailed', headers=headers).json()
        assert context['data_origin'] == 'simulation_scenario'
        assert context['telemetry']['position']['altitude_msl']['value'] == 35000
        assert context['flight_plan']['waypoints']
        assert client.get('/api/ai/context?level=everything', headers=headers).status_code == 422
        chat = client.get('/api/ai/chat', headers=headers).json()
        assert chat['chars'] == len(chat['text']) and '```json' in chat['text']
        exported = client.post('/api/ai/export', json={'level': 'essential'}, headers=headers).json()
        assert exported['path'].startswith('local/exports/') and (tmp_path/exported['path']).exists()
        assert client.post('/api/ai/simbrief/clear', json={}, headers=headers).status_code == 200
        assert client.get('/api/ai/plan', headers=headers).json()['plan'] is None


def test_simbrief_refresh_without_identifier_is_explicit(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    with client:
        response = client.post('/api/ai/simbrief/refresh', json={}, headers=headers)
        assert response.status_code == 502 and 'identifiant' in response.json()['detail']
