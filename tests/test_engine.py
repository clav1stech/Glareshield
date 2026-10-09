import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from glareshield.config import Configuration, load, save
from glareshield.drivers.mock import MockDriver
from glareshield.effects import condition_matches, render
from glareshield.engine import Engine
from glareshield.model import Condition, LightState

ROOT = Path(__file__).resolve().parents[1]


async def test_per_device_layering_with_independent_assignments(tmp_path):
    config=load(ROOT/'examples/demo.yaml')
    config.rules[0].targets=['device:light_a','device:light_b']
    next(r for r in config.rules if r.id=='caution').targets=['device:light_b']
    next(r for r in config.rules if r.id=='contact').targets=['device:light_b']
    next(r for r in config.rules if r.id=='dome').targets=['device:light_a']
    driver=MockDriver(config.devices)
    clock=[0.0]
    engine=Engine(config,{'mock':driver},tmp_path/'snapshots.json',clock=lambda:clock[0])
    engine.connected=True
    engine.values.update(warning=1,caution=1,contact=True,dome=2)
    await engine.step()
    assert engine.winners=={'light_a':'warning','light_b':'warning'}
    clock[0]=.3
    await engine.step()
    assert driver.states['light_a']['kelvin']==3000
    assert driver.states['light_b']['color']==[0,200,255]
    engine.values['warning']=0
    await engine.step()
    assert engine.winners=={'light_a':'dome','light_b':'caution'}
    await engine.shutdown()


async def test_retry_delays_follow_settings(setup):
    config,driver,engine,clock=setup
    config.settings.retry_initial_s=2
    config.settings.retry_max_s=3
    async def fail():
        raise OSError()
    await engine.call('light_a',fail)
    assert engine.next_retry['light_a']==2
    clock[0]=2
    await engine.call('light_a',fail)
    assert engine.next_retry['light_a']==5


def test_settings_validate_limits_and_retry_order():
    from glareshield.model import Settings
    for values in ({'ui_refresh_ms':0},{'test_duration_s':31},
                   {'retry_initial_s':10,'retry_max_s':5}, {'discovery_interval_s':0}):
        with pytest.raises(ValidationError):
            Settings(**values)


async def test_running_sound_stops_when_its_rule_ends(setup):
    config,driver,engine,_=setup
    config.active_scope='extended'
    engine.connected=True
    started=asyncio.Event()
    cancelled=asyncio.Event()
    async def play(identifier,device,effect):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    driver.play=play
    engine.values['warning']=1
    await engine.step()
    await asyncio.wait_for(started.wait(),1)
    engine.values['warning']=0
    await engine.step()
    await asyncio.wait_for(cancelled.wait(),1)
    await engine.shutdown()


@pytest.fixture
def setup(tmp_path):
    config = load(ROOT/'examples/demo.yaml')
    driver = MockDriver(config.devices)
    clock = [0.0]
    engine = Engine(config,{'mock':driver},tmp_path/'snapshots.json',clock=lambda:clock[0])
    engine.values = {'dome':1,'warning':0,'caution':0,'contact':False}
    return config,driver,engine,clock


async def test_cold_start_leaves_lights_untouched(setup):
    _,driver,engine,_ = setup
    await engine.step()
    assert driver.commands == []
    assert not engine.snapshot_path.exists()


async def test_priority_and_current_dome_restore(setup):
    _,driver,engine,_ = setup
    engine.connected = True
    engine.values.update(warning=1,caution=1,contact=True)
    await engine.step()
    assert engine.winners['light_a'] == 'warning'
    engine.values['warning'] = 0
    await engine.step()
    assert engine.winners['light_a'] == 'caution'
    engine.values['caution'] = 0
    await engine.step()
    assert engine.winners['light_a'] == 'contact'
    engine.values.update(contact=False,dome=2)
    await engine.step()
    assert driver.states['light_a']['brightness'] == 80
    assert engine.winners['light_a'] == 'dome'
    engine.connected = False
    await engine.step()
    assert driver.states['light_a']['brightness'] == 42
    assert engine.snapshots == {}


async def test_scope_switch_restores_departing_devices_and_filters_audio(setup):
    config,driver,engine,_ = setup
    engine.connected = True
    engine.values['warning'] = 1
    await engine.step()
    assert not [c for c in driver.commands if c['operation']=='sound']
    config.active_scope = 'extended'
    await engine.step()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert engine.winners['light_b'] == 'warning'
    assert [c for c in driver.commands if c['operation']=='sound'][0]['device'] == 'sound_a'
    config.active_scope = 'primary'
    await engine.step()
    assert driver.states['light_b'] == config.devices['light_b'].initial_state.model_dump(mode='json')
    await engine.shutdown()


async def test_pause_suspends_dome_but_preserves_alert(setup):
    _,driver,engine,_ = setup
    engine.connected = True
    await engine.step()
    engine.paused = True
    await engine.step()
    assert driver.states['light_a']['brightness'] == 42
    engine.values['warning'] = 1
    await engine.step()
    assert engine.winners['light_a'] == 'warning'


@pytest.mark.parametrize('value,brightness,on',[(0,100,False),(1,15,True),(2,80,True),(9,42,True),(None,42,True)])
async def test_dome_values_and_missing_value(setup,value,brightness,on):
    _,driver,engine,_ = setup
    engine.connected = True
    engine.values['dome'] = value
    await engine.step()
    assert driver.states['light_a']['brightness'] == brightness
    assert driver.states['light_a']['on'] == on


async def test_unchanged_state_and_threshold_suppress_commands(setup):
    _,driver,engine,_ = setup
    engine.connected = True
    await engine.step()
    count = len(driver.commands)
    await engine.step()
    assert len(driver.commands) == count
    previous = LightState(brightness=50,color=[10,20,30])
    engine.last['light_a'] = previous
    assert not engine.differs('light_a',LightState(brightness=52,color=[10,20,30]))
    assert engine.differs('light_a',LightState(brightness=53,color=[10,20,30]))


async def test_rate_limit_defers_commands_fairly(setup):
    config,driver,engine,clock = setup
    config.settings.driver_rates['mock'] = 1
    engine = Engine(config,{'mock':driver},engine.snapshot_path,clock=lambda:clock[0])
    engine.connected = True
    config.active_scope = 'extended'
    engine.values['warning'] = 1
    await engine.step()
    assert len([c for c in driver.commands if c['operation']=='apply']) == 1
    clock[0] = .6
    await engine.step()
    assert len([c for c in driver.commands if c['operation']=='apply']) == 1
    clock[0] = 1
    await engine.step()
    assert set(engine.winners) == {'light_a','light_b'}


async def test_device_failure_does_not_stop_other_devices(setup):
    config,driver,engine,clock = setup
    config.active_scope = 'extended'
    driver.unreachable.add('light_a')
    engine.connected = True
    engine.values['warning'] = 1
    await engine.step()
    assert engine.errors['light_a'] == 'ConnectionError'
    assert engine.winners['light_b'] == 'warning'
    driver.unreachable.clear()
    clock[0] = 2
    await engine.step()
    assert 'light_a' not in engine.errors
    assert engine.winners['light_a'] == 'warning'
    await engine.shutdown()


async def test_snapshot_is_persisted_before_first_command_and_recovers(setup):
    config,driver,engine,_ = setup
    original_apply = driver.apply
    async def checked_apply(identifier,device,state):
        persisted = json.loads(engine.snapshot_path.read_text(encoding='utf-8'))
        assert identifier in persisted
        await original_apply(identifier,device,state)
    driver.apply = checked_apply
    engine.connected = True
    engine.values['warning'] = 1
    await engine.step()
    assert driver.states['light_a']['color'] == [255,0,0]
    recovered = Engine(config,{'mock':driver},engine.snapshot_path)
    await recovered.recover()
    assert driver.states['light_a']['brightness'] == 42
    assert json.loads(engine.snapshot_path.read_text(encoding='utf-8')) == {}


async def test_unreachable_restore_remains_persisted_for_next_attempt(setup):
    _,driver,engine,clock = setup
    engine.connected = True
    await engine.step()
    driver.unreachable.add('light_a')
    await engine.shutdown()
    assert 'light_a' in engine.snapshots
    assert 'light_a' in json.loads(engine.snapshot_path.read_text(encoding='utf-8'))
    driver.unreachable.clear()
    clock[0] = 3
    engine.connected = False
    await engine.step()
    assert not engine.snapshots


def test_selectors_nested_groups_and_exclusions(setup):
    config,_,_,_ = setup
    config.active_scope = 'extended'
    assert config.select(['scope:active','exclude:device:light_a']) == {'light_b','sound_a'}
    assert config.select(['group:extended','exclude:group:primary']) == {'light_b','sound_a'}


@pytest.mark.parametrize('change',[
    lambda c:c['groups'].update(loop=['group:loop']),
    lambda c:c.update(active_scope='missing'),
    lambda c:c['rules'][0].update(targets=['device:missing']),
    lambda c:c['rules'][0]['condition'].update(source='missing'),
    lambda c:c['effects']['warning_light'].update(period_s=.1),
    lambda c:c['effects']['warning_light'].update(color=[256,0,0]),
    lambda c:c['devices']['light_a'].update(token='must-not-be-configured-here'),
    lambda c:c['settings']['driver_rates'].update(mock=0),
])
def test_invalid_configuration_is_rejected(setup,change):
    config,_,_,_ = setup
    payload = config.model_dump(mode='json')
    change(payload)
    with pytest.raises(ValidationError):
        Configuration.model_validate(payload)


def test_config_save_preserves_last_valid_and_scope(setup,tmp_path):
    config,_,_,_ = setup
    path = tmp_path/'config.yaml'
    save(path,config)
    original = path.read_bytes()
    config.active_scope = 'extended'
    save(path,config)
    assert load(path).active_scope == 'extended'
    assert path.with_suffix('.last-valid.yaml').read_bytes() == original
    broken = config.model_copy(update={'active_scope':'missing'})
    current = path.read_bytes()
    with pytest.raises(ValidationError):
        save(path,broken)
    assert path.read_bytes() == current


def test_structured_conditions_and_pulse_expiration(setup):
    config,_,_,_ = setup
    condition = Condition(op='all',conditions=[Condition(source='warning',op='eq',value=1),
                                             Condition(source='caution',op='eq',value=0)])
    assert condition_matches(condition,{'warning':1,'caution':0})
    assert not condition_matches(condition,{'warning':1})
    from glareshield.model import BlinkEffect
    assert render(BlinkEffect(type='pulse',color=[0,200,255],period_s=1.5,cycles=3),4.5) is None
    assert render(config.effects['warning_light'],.3).brightness == 15


async def test_failed_snapshot_write_prevents_control(setup,monkeypatch):
    _,driver,engine,_ = setup
    engine.connected = True
    def fail():
        raise PermissionError('Storage unavailable')
    monkeypatch.setattr(engine,'persist',fail)
    await engine.step()
    assert driver.commands == []
    assert engine.snapshots == {}
    assert engine.errors['light_a'] == 'PermissionError'


async def test_sound_repeat_and_retry(setup):
    config,driver,engine,clock = setup
    config.active_scope = 'extended'
    engine.connected = True
    engine.values['warning'] = 1
    async def tick():
        await engine.step()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    driver.unreachable.add('sound_a')
    await tick()
    assert not [c for c in driver.commands if c['operation']=='sound']
    driver.unreachable.clear()
    clock[0] = 1
    await tick()
    assert len([c for c in driver.commands if c['operation']=='sound']) == 1
    clock[0] = 9
    await tick()
    assert len([c for c in driver.commands if c['operation']=='sound']) == 1
    clock[0] = 11
    await tick()
    assert len([c for c in driver.commands if c['operation']=='sound']) == 2
    await engine.shutdown()


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    path = tmp_path/'invalid.yaml'
    path.write_text('active_scope: primary\nactive_scope: extended\n',encoding='utf-8')
    with pytest.raises(ValueError,match='dupliquée'):
        load(path)


async def test_grouped_driver_captures_every_state_before_commands(setup):
    config,driver,engine,clock = setup
    config.active_scope = 'extended'
    engine.connected = True
    engine.values['warning'] = 1
    batches=[]
    async def apply_batch(items):
        checkpoint=json.loads(engine.snapshot_path.read_text(encoding='utf-8'))
        assert set(items) <= set(checkpoint)
        batches.append(set(items))
        for key,(device,state) in items.items():
            await driver.apply(key,device,state)
        return {}
    driver.apply_batch=apply_batch
    await engine.step()
    assert batches==[{'light_a','light_b'}]
    await engine.shutdown()


async def test_warning_over_caution_with_atc_background_then_dome(setup):
    config,driver,engine,clock=setup
    engine.connected=True
    engine.values.update(warning=1,caution=1,contact=True,dome=2)
    await engine.step()
    assert driver.states['light_a']['color']==[255,0,0]
    assert engine.background_winners['light_a']=='contact'
    clock[0]=.3
    await engine.step()
    assert driver.states['light_a']['color']==[0,200,255]
    assert engine.winners['light_a']=='warning'
    engine.values['warning']=0
    clock[0]=.5
    await engine.step()
    assert driver.states['light_a']['color']==[255,140,0]
    clock[0]=.8
    await engine.step()
    assert driver.states['light_a']['color']==[0,200,255]
    engine.values['contact']=False
    await engine.step()
    assert driver.states['light_a']['kelvin']==3000
    engine.values['caution']=0
    await engine.step()
    assert engine.winners['light_a']=='dome'
