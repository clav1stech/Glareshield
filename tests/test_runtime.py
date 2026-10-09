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
        replacement.sources['warning'].poll_ms=200
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


async def test_independent_assignments_apply_without_recreating_sources(tmp_path):
    path=tmp_path/'local/config.yaml'
    save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        engine=runtime.engine
        tasks=list(runtime.tasks)
        engine.values.update(warning=1,dome=2)
        await engine.step()
        replacement=runtime.config.model_copy(deep=True)
        for rule in replacement.rules:
            if rule.id=='warning':
                rule.targets=['device:light_b']
            if rule.id=='dome':
                rule.targets=['device:light_a']
        await runtime.configure(replacement)
        assert runtime.engine is engine and runtime.tasks==tasks
        assert engine.connected
        assert engine.winners=={'light_a':'dome','light_b':'warning'}
        assert engine.drivers['mock'].states['light_a']['brightness']==80
        await runtime.change_scope('extended')
        assert engine.winners=={'light_a':'dome','light_b':'warning'}
        replacement=runtime.config.model_copy(deep=True)
        next(r for r in replacement.rules if r.id=='warning').targets=[]
        await runtime.configure(replacement)
        assert engine.winners=={'light_a':'dome'}
        assert 'light_b' not in engine.snapshots
        assert engine.drivers['mock'].states['light_b']==replacement.devices['light_b'].initial_state.model_dump(mode='json')
        assert next(r for r in load(path).rules if r.id=='warning').targets==[]
    finally:
        await runtime.stop()


async def test_invalid_routing_keeps_configuration_and_connections(tmp_path):
    import pytest
    from pydantic import ValidationError
    path=tmp_path/'local/config.yaml'
    config=save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        engine=runtime.engine
        candidate=runtime.config.model_copy(deep=True)
        candidate.rules[0].targets=['device:unknown']
        with pytest.raises(ValidationError):
            await runtime.configure(candidate)
        assert runtime.engine is engine and load(path)==config
    finally:
        await runtime.stop()


async def test_preview_expires_to_current_cockpit_without_saving_or_reconnecting(tmp_path):
    path=tmp_path/'local/config.yaml'
    config=save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        engine=runtime.engine
        tasks=list(runtime.tasks)
        engine.values['dome']=1
        await engine.step()
        snapshot=engine.snapshots['light_a']
        draft=config.model_copy(deep=True)
        draft.effects['dome_light'].map['2'].brightness=66
        await runtime.start_preview(draft,'dome',value=2)
        assert engine.drivers['mock'].states['light_a']['brightness']==66
        assert runtime.preview and engine.snapshots['light_a']==snapshot
        assert load(path)==config and runtime.config==config
        assert runtime.engine is engine and runtime.tasks==tasks and engine.connected
        # Pilot changes the real source during the preview; expiry must use it.
        engine.values['dome']=0
        await asyncio.sleep(3.2)
        assert runtime.preview is None and engine.config==config
        assert engine.drivers['mock'].states['light_a']['on'] is False
        assert load(path)==config and runtime.tasks==tasks
    finally:
        await runtime.stop()


async def test_preview_restores_outside_scope_and_respects_live_warning(tmp_path):
    path=tmp_path/'local/config.yaml'
    config=save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        engine=runtime.engine
        engine.values['warning']=1
        await engine.step()
        await runtime.start_preview(config,'dome',targets=['device:light_a','device:light_b'],value=2)
        assert engine.winners['light_a']=='warning'
        assert engine.drivers['mock'].states['light_b']['brightness']==80
        assert 'light_b' in engine.snapshots
        await runtime.stop_tests()
        assert runtime.preview is None and engine.winners['light_a']=='warning'
        assert engine.drivers['mock'].states['light_b']==config.devices['light_b'].initial_state.model_dump(mode='json')
        assert 'light_b' not in engine.snapshots
    finally:
        await runtime.stop()


async def test_invalid_preview_leaves_active_configuration_untouched(tmp_path):
    import pytest
    path=tmp_path/'local/config.yaml'
    config=save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        for targets,value in (([],1),(['device:light_a'],99)):
            with pytest.raises(ValueError):
                await runtime.start_preview(config,'dome',targets=targets,value=value)
        changed=config.model_copy(deep=True)
        changed.sources['warning'].poll_ms=200
        with pytest.raises(ValueError):
            await runtime.start_preview(changed,'warning')
        assert runtime.preview is None and runtime.engine.config==config
        assert load(path)==config
    finally:
        await runtime.stop()


async def test_stopping_source_test_removes_mock_injected_value(tmp_path):
    path=tmp_path/'local/config.yaml'
    save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        runtime.manual['warning']=(1,time.monotonic()+3)
        await asyncio.sleep(.15)
        assert runtime.engine.winners['light_a']=='warning'
        await runtime.stop_tests()
        assert not runtime.manual and runtime.engine.values['warning'] is None
        assert not runtime.engine.snapshots
    finally:
        await runtime.stop()


async def test_three_second_preview_expires_even_with_slow_render_setting(tmp_path):
    path=tmp_path/'local/config.yaml'
    config=load(Path(__file__).resolve().parents[1]/'examples/demo.yaml')
    config.settings.render_hz=.1
    save(path,config)
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        await asyncio.sleep(.01)
        await runtime.start_preview(config,'dome',value=2)
        assert runtime.preview
        await asyncio.sleep(3.2)
        assert runtime.preview is None and not runtime.engine.snapshots
        await runtime.test_source('warning',1,1)
        assert runtime.engine.values['warning']==1
        await asyncio.sleep(1.2)
        assert runtime.engine.values['warning'] is None and not runtime.engine.snapshots
    finally:
        await asyncio.wait_for(runtime.stop(),1)


async def test_preview_while_suspended_does_not_reactivate_normal_rules(tmp_path):
    path=tmp_path/'local/config.yaml'
    config=save(path,load(Path(__file__).resolve().parents[1]/'examples/demo.yaml'))
    runtime=Runtime(tmp_path,path)
    await runtime.start()
    try:
        runtime.suspended=True
        runtime.engine.values['warning']=1
        await runtime.engine.shutdown()
        await runtime.start_preview(config,'dome',value=2)
        assert runtime.engine.winners['light_a'].startswith('preview_')
        assert runtime.engine.drivers['mock'].states['light_a']['brightness']==80
        await runtime.stop_tests()
        assert runtime.suspended and not runtime.engine.snapshots
        assert runtime.engine.drivers['mock'].states['light_a']==config.devices['light_a'].initial_state.model_dump(mode='json')
        assert load(path)==config
    finally:
        await runtime.stop()
