import asyncio
import functools
import time
from pathlib import Path

from glareshield.aibridge.config import AIBridgeSettings
from glareshield.config import load, save
from glareshield.model import Source
from glareshield.runtime import Runtime
import glareshield.runtime as runtime_module
from glareshield.simulator import SimulatorSource, TelemetryPoller

DEMO = Path(__file__).resolve().parents[1]/'examples/demo.yaml'


class FakeRequest:
    def __init__(self, name, unit, values, calls):
        self.definition = (name, unit)
        self.values = values
        self.calls = calls

    def get(self):
        self.calls.append(self.definition[0])
        return self.values.get(self.definition[0])


def test_poller_reads_one_variable_per_cycle_and_respects_intervals():
    calls = []
    values = {'PLANE ALTITUDE': 1000.0, 'TITLE': b'Demo\0'}
    poller = TelemetryPoller(lambda name, unit: FakeRequest(name, unit, values, calls))
    poller.configure({'alt': {'name': 'PLANE ALTITUDE', 'unit': 'feet', 'interval_ms': 60000},
                      'title': {'name': 'TITLE', 'unit': 'String', 'interval_ms': 60000},
                      'missing': {'name': 'UNKNOWN VAR', 'unit': 'number', 'interval_ms': 60000}})
    poller.poll_once()
    # Lighting reads come first; telemetry adds a single read per cycle.
    assert len(calls) == 1
    for _ in range(4):
        poller.poll_once()
    assert sorted(calls) == ['PLANE ALTITUDE', 'TITLE', 'UNKNOWN VAR']
    results, errors = poller.drain()
    assert results['alt'][0] == 1000.0 and results['title'][0] == 'Demo'
    assert errors == {'missing': 'Aucune donnée reçue'}
    assert poller.drain()[0] == {}
    poller.configure({})
    poller.poll_once()
    assert len(calls) == 3


def telemetry_worker(sources, pipe, stop):
    definitions = {}
    while not stop.wait(.02):
        while pipe.poll():
            definitions = pipe.recv()['telemetry']
        pipe.send({'connected': True, 'paused': False, 'values': {'fixture': 1},
                   'telemetry': {key: (len(key), time.time()) for key in definitions}})
    pipe.close()


async def test_source_sends_and_updates_telemetry_requests_without_reconnecting():
    messages = []
    source = SimulatorSource({'fixture': Source(type='lvar', name='DEMO')}, messages.append,
                             worker_target=telemetry_worker, telemetry={'alt': {'name': 'PLANE ALTITUDE'}})
    task = asyncio.create_task(source.run())
    try:
        async with asyncio.timeout(15):
            while not any('alt' in m.get('telemetry', {}) for m in messages):
                await asyncio.sleep(.05)
            process = source.process
            source.set_telemetry({'speed': {'name': 'AIRSPEED INDICATED'}})
            while not any('speed' in m.get('telemetry', {}) for m in messages):
                await asyncio.sleep(.05)
            assert source.process is process
            assert 'alt' not in messages[-1].get('telemetry', {})
    finally:
        source.stop()
        await task


def make_runtime(tmp_path, monkeypatch, *, lighting_sources=True, enabled=True):
    monkeypatch.setattr(runtime_module, 'SimulatorSource',
                        functools.partial(SimulatorSource, worker_target=telemetry_worker))
    config = load(DEMO)
    if lighting_sources:
        config.sources['warning'] = Source(type='lvar', name='DEMO_WARNING')
    path = tmp_path/'local/config.yaml'
    save(path, config)
    if enabled:
        (tmp_path/'local/ai-bridge.yaml').write_text('enabled: true\n', encoding='utf-8')
    return Runtime(tmp_path, path)


async def wait_for(predicate):
    async with asyncio.timeout(15):
        while not predicate():
            await asyncio.sleep(.05)


async def test_lighting_test_values_never_reach_ai_snapshot(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, monkeypatch)
    await runtime.start()
    try:
        await wait_for(lambda: runtime.ai.live.samples)
        runtime.manual['warning'] = (1, time.monotonic()+5)
        await asyncio.sleep(.2)
        assert runtime.engine.values['warning'] == 1
        document = runtime.ai.snapshot('full')
        assert 'warning' not in str(document['telemetry'].keys())
        assert document['data_origin'] == 'simconnect'
        assert document['telemetry']['speed']['ias'] == {'label': 'Vitesse indiquée', 'value': 3, 'unit': 'kt',
            'status': 'observed', 'age_s': document['telemetry']['speed']['ias']['age_s'],
            'source': 'SimVar AIRSPEED INDICATED', 'verification': 'msfs_sdk'}
        assert len(runtime.sources) == 1
    finally:
        await runtime.stop()


async def test_ai_only_connection_keeps_lighting_independent_of_simulator(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, monkeypatch, lighting_sources=False)
    await runtime.start()
    try:
        assert runtime.simulator is not None and not runtime.lighting_simulator
        assert runtime.engine.connected
        await wait_for(lambda: runtime.ai.live.connected)
        runtime.simulator_update({'connected': False, 'paused': True, 'values': {}})
        assert runtime.engine.connected and not runtime.engine.paused
        engine = runtime.engine
        runtime.ai.save(AIBridgeSettings(enabled=False))
        await runtime.ai_settings_changed()
        assert runtime.simulator is None and runtime.sources == [] and runtime.engine is engine
        runtime.ai.save(AIBridgeSettings(enabled=True))
        await runtime.ai_settings_changed()
        assert runtime.simulator is not None and runtime.engine is engine
    finally:
        await runtime.stop()


async def test_disabled_bridge_preserves_original_startup(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, monkeypatch, lighting_sources=False, enabled=False)
    await runtime.start()
    try:
        assert runtime.simulator is None and runtime.sources == [] and runtime.engine.connected
    finally:
        await runtime.stop()
