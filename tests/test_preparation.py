"""Preparation UI uses a disposable root, simulated lamps and a fake SimConnect source."""
import asyncio
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

import glareshield.runtime as runtime_module
from glareshield.aibridge.config import AIBridgeSettings, save_settings
from glareshield.config import load, save
from glareshield.web import create_app


ROOT = Path(__file__).resolve().parents[1]


class FakeSimulator:
    def __init__(self, sources, update, **kwargs):
        self.update = update
        self.error = None
        self.stopping = False

    def set_telemetry(self, definitions):
        pass

    async def run(self):
        while not self.stopping:
            self.update({'connected': True, 'paused': False, 'values': {},
                         'telemetry': {'on_ground': (True, time.time()),
                                       'altitude_msl': (500, time.time())}})
            await asyncio.sleep(.05)

    def stop(self):
        self.stopping = True


def fixture_runtime(root):
    path = root/'local/config.yaml'
    save(path, load(ROOT/'examples/demo.yaml'))
    save_settings(root/'local/ai-bridge.yaml', AIBridgeSettings(enabled=True, simbrief_user='demo-pilot'))
    runtime = runtime_module.Runtime(root, path)
    # No OS overlay is needed in the test server.
    runtime.overlay = type('Overlay', (), {'show': lambda *args: None, 'close': lambda *args: None})()
    data = json.loads((ROOT/'src/glareshield/aibridge/demo_ofp.json').read_text(encoding='utf-8'))
    runtime.ai.plan.transport = httpx.MockTransport(lambda request: httpx.Response(200, json=data))
    return runtime


def token_headers(client):
    token = re.search("const TOKEN='([^']+)'", client.get('/').text).group(1)
    return {'x-glareshield-token': token}


def identity(runtime):
    return {'engine': id(runtime.engine), 'simulator': id(runtime.simulator),
            'drivers': [id(driver) for driver in runtime.engine.drivers.values()],
            'tasks': [id(task) for task in runtime.tasks]}


def test_display_and_readonly_navigation_preserve_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_module, 'SimulatorSource', FakeSimulator)
    runtime = fixture_runtime(tmp_path)
    with TestClient(create_app(runtime)) as client:
        headers = token_headers(client)
        before = identity(runtime)
        assert client.get('/api/display').json() == {'theme': 'auto', 'text_size': 'standard'}
        for theme in ('light', 'dark', 'auto'):
            settings = {'theme': theme, 'text_size': 'extra'}
            assert client.put('/api/display', json=settings).status_code == 403
            assert client.put('/api/display', json=settings, headers=headers).json() == settings
            assert client.get('/api/display').json() == settings
            for endpoint in ('/api/status', '/api/config', '/api/ai/status', '/api/ai/plan',
                             '/api/ai/context', '/api/ai/settings', '/api/ai/variables', '/api/ai/ivao'):
                assert client.get(endpoint, headers=headers).status_code == 200
        assert client.put('/api/display', json={'theme': 'invalid'}, headers=headers).status_code == 422
        assert identity(runtime) == before
        assert runtime.status()['simulator']['connected'] is True
        assert client.get('/static/copilot.js').status_code == 200
        assert client.get('/static/index.html').status_code == 404
    assert json.loads((tmp_path/'local/display.json').read_text()) == {'theme': 'auto', 'text_size': 'extra'}
    (tmp_path/'local/display.json').write_text('{invalid', encoding='utf-8')
    with TestClient(create_app(runtime)) as client:
        assert client.get('/api/display').json() == {'theme': 'auto', 'text_size': 'standard'}


def test_mock_lighting_never_claims_simconnect_connection(tmp_path):
    path = tmp_path/'local/config.yaml'
    save(path, load(ROOT/'examples/demo.yaml'))
    runtime = runtime_module.Runtime(tmp_path, path)
    with TestClient(create_app(runtime)):
        assert runtime.engine.connected is True
        assert runtime.status()['simulator'] == {
            'enabled': False, 'connected': False, 'paused': False, 'stale': False, 'error': None}


def test_simulator_error_and_stale_observation_are_exposed(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_module, 'SimulatorSource', FakeSimulator)
    runtime = fixture_runtime(tmp_path)
    with TestClient(create_app(runtime)):
        runtime.simulator_observation = ({'connected': True}, time.monotonic()-30)
        assert runtime.status()['simulator']['stale'] is True
        runtime.simulator.error = 'FixtureError'
        assert runtime.status()['simulator']['error'] == 'FixtureError'


def test_preparation_statuses_and_navigation_contract():
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the UI status tests.')
    result = subprocess.run([node, 'tests/test_preparation_ui.cjs'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout+result.stderr


if __name__ == '__main__':
    # Manual/browser QA: no installed configuration or real driver is read.
    import tempfile
    import uvicorn
    runtime_module.SimulatorSource = FakeSimulator
    roots = ROOT/'local/test-roots'
    roots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='preparation-', dir=roots) as directory:
        runtime = fixture_runtime(Path(directory))
        app = create_app(runtime)

        @app.get('/test/identity')
        async def runtime_identity():
            return identity(runtime)

        uvicorn.run(app, host='127.0.0.1', port=18762, log_level='warning')
