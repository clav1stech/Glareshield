import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from glareshield.aibridge.config import AIBridgeSettings, LVarEntry
from glareshield.aibridge.presets import PRESETS, apply_preset
from glareshield.config import load

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fenix_example_configuration_is_valid():
    config = load(ROOT/'examples/fenix-a320.yaml')
    assert config.sources['dome'].name == 'S_OH_INT_LT_DOME'
    assert all(device.driver == 'mock' for device in config.devices.values())


def test_preset_adds_missing_lvars_once_and_keeps_existing_entries():
    existing = LVarEntry(key='efis1_fd', name='I_FCU_EFIS1_FD', label='FD personnalisé', validated=True)
    settings, added = apply_preset(AIBridgeSettings(lvars=[existing]), 'fenix-a320')
    assert added == len(PRESETS['fenix-a320']['lvars'])-1
    kept = next(item for item in settings.lvars if item.key == 'efis1_fd')
    assert kept.label == 'FD personnalisé' and kept.validated
    assert not any(item.validated for item in settings.lvars if item.key != 'efis1_fd')
    assert {'flaps_handle_index', 'spoilers_armed'} <= set(settings.disabled)
    again, added = apply_preset(settings, 'fenix-a320')
    assert added == 0 and again == settings
    with pytest.raises(ValueError):
        apply_preset(settings, 'unknown')


def test_find_lvars_reads_behaviour_tags_and_rpn(tmp_path):
    package = tmp_path/'demo-aircraft'
    (package/'model').mkdir(parents=True)
    (package/'model/behavior.xml').write_text(
        '<UseTemplate><VAR_NAME>S_DEMO_SWITCH</VAR_NAME><VAR_NAME_BUTTON>I_DEMO_LIGHT</VAR_NAME_BUTTON>'
        '<Code>(L:#VAR_NAME#) (L:N_DEMO_LEVEL, number)</Code></UseTemplate>', encoding='utf-8')
    (package/'model/texture.png').write_bytes(b'\x89PNG(L:IGNORED_BINARY,')
    names = script('find_lvars').scan(package)
    assert names == {'I_DEMO_LIGHT': ['model/behavior.xml'], 'N_DEMO_LEVEL': ['model/behavior.xml'],
                     'S_DEMO_SWITCH': ['model/behavior.xml']}


def test_probe_validates_simvar_list_before_connecting(tmp_path):
    bad = tmp_path/'simvars.json'
    bad.write_text(json.dumps([['PLANE ALTITUDE']]), encoding='utf-8')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/probe_simulator.py'), '--simvars-file', str(bad),
                             '--variables-file', str(tmp_path/'missing.json')], capture_output=True, text=True)
    assert result.returncode == 2 and 'illisible' in result.stderr
    empty = tmp_path/'empty.json'
    empty.write_text('[]', encoding='utf-8')
    result = subprocess.run([sys.executable, str(ROOT/'scripts/probe_simulator.py'), '--simvars-file', str(bad),
                             '--variables-file', str(empty)], capture_output=True, text=True)
    assert result.returncode == 2 and 'paire' in result.stderr
