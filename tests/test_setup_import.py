import json
import pytest

from glareshield import discovery, setup
from glareshield.config import Configuration
from glareshield.model import Device


class FakeRuntime:
    def __init__(self, root):
        self.root = root
        self.config = Configuration(scopes={'default': []}, active_scope='default')
        self.applied = None

    async def configure(self, configuration):
        self.applied = configuration


class FakeHue:
    def __init__(self, host, username, certificate):
        pass

    async def discover(self):
        return [Device(name='Bandeau fictif', driver='hue', resource_id='res-1')]

    async def close(self):
        pass


class BrokenNanoleaf:
    closed = False

    def __init__(self, host, token, port):
        pass

    async def discover(self):
        raise RuntimeError('ConnectTimeout')

    async def close(self):
        BrokenNanoleaf.closed = True


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    secrets = tmp_path / 'local/secrets'
    secrets.mkdir(parents=True)
    (secrets / 'hue.json').write_text(json.dumps({'hue-bridge': {'username': 'x'}}), encoding='utf-8')
    (secrets / 'nanoleaf.json').write_text(json.dumps({'nano-panel': {'auth_token': 'y'}}), encoding='utf-8')

    async def network(cache_path=None):
        return {'hue-bridge': {'host': '192.0.2.1'}, 'nano-panel': {'host': '192.0.2.2', 'port': 16021}}

    monkeypatch.setattr(discovery, 'network', network)
    monkeypatch.setattr(setup, 'HueDriver', FakeHue)
    monkeypatch.setattr(setup, 'NanoleafDriver', BrokenNanoleaf)
    BrokenNanoleaf.closed = False
    return FakeRuntime(tmp_path)


async def test_unreachable_controller_does_not_block_the_others(runtime):
    result = await setup.import_devices(runtime)
    assert result['devices'] == 1
    assert len(result['errors']) == 1
    assert '(nanoleaf) : RuntimeError' in result['errors'][0]
    assert [c.type for c in runtime.applied.controllers.values()] == ['hue']
    assert BrokenNanoleaf.closed


async def test_all_controllers_failing_reports_the_cause(runtime, monkeypatch):
    class BrokenHue(FakeHue):
        async def discover(self):
            raise RuntimeError('boom')

    monkeypatch.setattr(setup, 'HueDriver', BrokenHue)
    with pytest.raises(RuntimeError, match='Aucun contrôleur joignable'):
        await setup.import_devices(runtime)
    assert runtime.applied is None
