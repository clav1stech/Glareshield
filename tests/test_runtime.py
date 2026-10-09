import asyncio
import time
from pathlib import Path

from glareshield.config import load,save
from glareshield.runtime import Runtime


async def test_live_config_change_restores_and_persists_scope(tmp_path):
    config=load(Path(__file__).resolve().parents[1]/'examples/demo.yaml')
    path=tmp_path/'local/config.yaml'
    save(path,config)
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        runtime.manual['warning']=(1,time.monotonic()+5)
        await asyncio.sleep(.2)
        assert runtime.engine.winners['light_a']=='warning'
        previous_driver=runtime.engine.drivers['mock']
        replacement=runtime.config.model_copy(deep=True)
        replacement.active_scope='extended'
        await runtime.configure(replacement)
        assert load(path).active_scope=='extended'
        assert previous_driver.states['light_a']==config.devices['light_a'].initial_state.model_dump(mode='json')
        assert runtime.engine.snapshots=={}
        assert runtime.manual=={}
    finally:
        await runtime.stop()


async def test_manual_value_expires_instead_of_sticking(tmp_path):
    path=tmp_path/'local/config.yaml'
    save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        runtime.manual['warning']=(1,time.monotonic()+.2)
        await asyncio.sleep(.15)
        assert runtime.engine.winners['light_a']=='warning'
        await asyncio.sleep(.3)
        assert not runtime.manual and runtime.engine.values['warning'] is None
        assert not runtime.engine.snapshots
    finally:
        await runtime.stop()


async def test_scope_change_preserves_engine_and_source_connection(tmp_path):
    path=tmp_path/'local/config.yaml'
    save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        engine=runtime.engine
        engine.values['warning']=1
        await engine.step()
        original=engine.snapshots['light_a']
        await runtime.change_scope('extended')
        assert runtime.engine is engine and engine.connected
        assert engine.snapshots['light_a']==original
        assert engine.winners['light_b']=='warning'
        assert load(path).active_scope=='extended'
    finally:
        await runtime.stop()
