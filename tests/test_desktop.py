"""Exercise desktop startup against a real local server, without any hardware."""
import asyncio
from io import BytesIO
from pathlib import Path
import socket
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from glareshield import app, desktop


def test_app_window_uses_private_profile_and_configured_port(tmp_path, monkeypatch):
    browser = Path('browser/msedge.exe')
    monkeypatch.setattr(desktop, 'find_browser', lambda: browser)
    commands = []
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda command: commands.append(command))
    monkeypatch.setattr(desktop.webbrowser, 'open', lambda url: pytest.fail('Unexpected browser fallback'))
    root = tmp_path / 'root with spaces'
    desktop.open_window(root, 18763)
    command, = commands
    assert command[0] == str(browser)
    assert '--app=http://127.0.0.1:18763' in command
    assert f'--user-data-dir={root / "local/browser/18763"}' in command
    assert (root / 'local/browser/18763').is_dir()


@pytest.mark.parametrize('missing', [True, False])
def test_unavailable_browser_falls_back_without_stopping_engine(tmp_path, monkeypatch, missing):
    monkeypatch.setattr(desktop, 'find_browser', lambda: None if missing else Path('missing.exe'))
    def failed_launch(command):
        raise OSError('Fixture browser failure')
    monkeypatch.setattr(desktop.subprocess, 'Popen', failed_launch)
    opened = []
    monkeypatch.setattr(desktop.webbrowser, 'open', opened.append)
    desktop.open_window(tmp_path, 18763)
    assert opened == ['http://127.0.0.1:18763']


def test_edge_is_preferred_to_chrome_in_standard_install_locations(tmp_path, monkeypatch):
    edge = tmp_path / 'Microsoft/Edge/Application/msedge.exe'
    edge.parent.mkdir(parents=True)
    edge.touch()
    monkeypatch.setattr(desktop, 'os', SimpleNamespace(name='nt', environ={'ProgramFiles': str(tmp_path)}))
    monkeypatch.setattr(desktop.shutil, 'which', lambda name: 'chrome.exe' if name == 'chrome' else None)
    assert desktop.find_browser() == edge


class LocalRuntime:
    def __init__(self, root, path):
        self.started = self.stopped = False

    async def start(self):
        await asyncio.sleep(.1)
        self.started = True

    async def stop(self):
        self.stopped = True


async def test_window_opens_after_server_is_ready_and_icon_is_served(tmp_path, monkeypatch):
    runtime = LocalRuntime(tmp_path, None)
    monkeypatch.setattr(app, 'Runtime', lambda *args: runtime)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    opened = []
    def open_window(root, actual_port):
        assert runtime.started and root == tmp_path and actual_port == port
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
            page = client.get('/')
            assert page.status_code == 200 and 'href="/favicon.ico"' in page.text
            response = client.get('/favicon.ico')
            assert response.status_code == 200
            icon = Image.open(BytesIO(response.content))
            assert icon.format == 'ICO'
            assert icon.ico.sizes() == {(16, 16), (32, 32), (48, 48), (64, 64)}
        opened.append(root)
        runtime.request_exit()
    monkeypatch.setattr(app, 'open_window', open_window)
    await asyncio.wait_for(app.serve(tmp_path, None, port, tray=False, window=True), 5)
    assert opened == [tmp_path] and runtime.stopped


async def test_port_in_use_never_connects_hardware_or_opens_window(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'Runtime', lambda *args: pytest.fail('Hardware must not start'))
    monkeypatch.setattr(app, 'open_window', lambda *args: pytest.fail('Window must not open'))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        with pytest.raises(RuntimeError, match='déjà lancée'):
            await app.serve(tmp_path, None, listener.getsockname()[1], tray=False, window=True)


async def test_failed_startup_does_not_open_window_or_leave_pending_task(tmp_path, monkeypatch):
    runtime = LocalRuntime(tmp_path, None)
    async def fail():
        raise RuntimeError('Fixture startup failure')
    runtime.start = fail
    monkeypatch.setattr(app, 'Runtime', lambda *args: runtime)
    monkeypatch.setattr(app, 'open_window', lambda *args: pytest.fail('Window must not open'))
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    before = asyncio.all_tasks()
    with pytest.raises(SystemExit):
        async with asyncio.timeout(5):
            await app.serve(tmp_path, None, port, tray=False, window=True)
    assert asyncio.all_tasks() == before
