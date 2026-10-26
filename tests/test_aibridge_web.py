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
        context = client.get('/api/ai/context?level=full', headers=headers).json()
        assert context['data_origin'] == 'simulation_scenario'
        assert context['telemetry']['position']['altitude_msl']['value'] == 35000
        assert context['flight_plan']['waypoints']
        assert client.get('/api/ai/context?level=everything', headers=headers).status_code == 422
        chat = client.get('/api/ai/chat', headers=headers).json()
        assert chat['chars'] == len(chat['text']) and '```json' in chat['text']
        exported = client.post('/api/ai/export', json={'level': 'briefing'}, headers=headers).json()
        assert exported['path'].startswith('local/exports/') and (tmp_path/exported['path']).exists()
        assert client.put('/api/ai/notes', json={'text': 'STAR DEMO2B'}, headers=headers).status_code == 200
        assert client.get('/api/ai/context?level=flight', headers=headers).json()['pilot_notes']['text'] == 'STAR DEMO2B'
        assert client.put('/api/ai/notes', json={'text': 'x'*2001}, headers=headers).status_code == 400
        assert client.get('/api/ai/notes').status_code == 403
        assert client.get('/api/ai/context', headers=headers).json()['level'] == 'flight'
        assert client.get('/api/ai/presets', headers=headers).json()[0]['id'] == 'fenix-a320'
        assert client.post('/api/ai/presets/fenix-a320', json={}, headers=headers).json()['added'] == 12
        assert client.post('/api/ai/presets/fenix-a320', json={}, headers=headers).json()['added'] == 0
        assert client.post('/api/ai/presets/unknown', json={}, headers=headers).status_code == 400
        assert client.post('/api/ai/simbrief/clear', json={}, headers=headers).status_code == 200
        assert client.get('/api/ai/plan', headers=headers).json()['plan'] is None


def test_simbrief_refresh_without_identifier_is_explicit(tmp_path):
    runtime, client, headers = client_and_headers(tmp_path)
    with client:
        response = client.post('/api/ai/simbrief/refresh', json={}, headers=headers)
        assert response.status_code == 502 and 'identifiant' in response.json()['detail']


def test_ivao_routes_are_token_protected_disabled_by_default_and_validated(tmp_path):
    import httpx
    runtime, client, headers = client_and_headers(tmp_path)
    requests = []

    def network(request):
        requests.append(request.url.path)
        if request.url.path.endswith('whazzup'):
            return httpx.Response(200, json={'updatedAt': '2026-10-26T06:00:00Z', 'clients': {'atcs': [
                {'callsign': 'XXNC_TWR', 'atcSession': {'frequency': 118.7, 'position': 'TWR'},
                 'lastTrack': {'latitude': 43.66, 'longitude': 7.22}}]}})
        return httpx.Response(200, json=[{'airportIcao': 'XXNC', 'metar': 'XXNC 260600Z 09006KT CAVOK 20/12 Q1015',
                                          'taf': 'XXNC 260500Z 2606/2712 09008KT CAVOK'}])
    runtime.ai.ivao.transport = httpx.MockTransport(network)
    with client:
        assert client.get('/api/ai/ivao').status_code == 403
        page = client.get('/api/ai/ivao', headers=headers).json()
        assert page['enabled'] is False and page['view'] is None
        assert 'ivao' not in client.get('/api/ai/context?level=full', headers=headers).json()
        assert client.post('/api/ai/ivao/refresh', json={}, headers=headers).status_code == 400
        assert client.get('/api/ai/ivao/airport/XXNC', headers=headers).status_code == 400
        settings = client.get('/api/ai/settings', headers=headers).json()
        bad = {**settings, 'ivao': {**settings['ivao'], 'enabled': True, 'whazzup_interval_s': 5}}
        assert client.put('/api/ai/settings', json=bad, headers=headers).status_code == 400
        good = {**settings, 'ivao': {**settings['ivao'], 'enabled': True, 'airports': ['xxnc']}}
        assert client.put('/api/ai/settings', json=good, headers=headers).status_code == 200
        assert runtime.ai.ivao.task is None and requests == []
        refreshed = client.post('/api/ai/ivao/refresh', json={}, headers=headers).json()
        assert {item['result'] for item in refreshed['results'].values()} == {'fetched'}
        assert refreshed['view']['controllers'][0]['callsign'] == 'XXNC_TWR'
        again = client.post('/api/ai/ivao/refresh', json={}, headers=headers).json()
        assert {item['result'] for item in again['results'].values()} == {'skipped'} and len(requests) == 3
        lookup = client.get('/api/ai/ivao/airport/xxnc', headers=headers).json()
        assert lookup['weather']['airports'][0]['metar']['status'] == 'published'
        assert client.get('/api/ai/ivao/airport/XX1', headers=headers).status_code == 400
        context = client.get('/api/ai/context?level=briefing', headers=headers).json()
        assert context['ivao']['weather']['airports'][0]['icao'] == 'XXNC'
        assert client.get('/api/ai/status', headers=headers).json()['ivao']['feeds']['whazzup'] == 'current'
