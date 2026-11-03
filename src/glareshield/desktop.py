"""Open the local UI as a browser app, with its own private browser profile."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import webbrowser


def application_icon():
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (64, 64), (16, 21, 31, 255))
    ImageDraw.Draw(image).line([(10, 42), (24, 20), (32, 34), (40, 20), (54, 42)],
                              fill=(116, 191, 255, 255), width=5)
    return image


def find_browser() -> Path | None:
    if os.name != 'nt':
        return None
    # Prefer Edge (included with Windows), then Chrome. Never use a personal profile.
    for executable, relative in (
        ('msedge', 'Microsoft/Edge/Application/msedge.exe'),
        ('chrome', 'Google/Chrome/Application/chrome.exe'),
    ):
        found = shutil.which(executable)
        if found:
            return Path(found)
        for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
            directory = os.environ.get(variable)
            if directory:
                candidate = Path(directory) / relative
                if candidate.is_file():
                    return candidate
    return None


def open_window(root: Path, port: int) -> None:
    url = f'http://127.0.0.1:{port}'
    browser = find_browser()
    if browser:
        try:
            profile = root / 'local' / 'browser' / str(port)
            profile.mkdir(parents=True, exist_ok=True)
            subprocess.Popen([
                str(browser), f'--app={url}', f'--user-data-dir={profile}',
                '--no-first-run', '--no-default-browser-check',
                '--disable-background-mode', '--hide-crash-restore-bubble',
                '--window-size=1280,900',
            ])
            return
        except OSError:
            logging.getLogger(__name__).exception('Ouverture de la fenêtre dédiée impossible.')
    logging.getLogger(__name__).warning('Fenêtre dédiée indisponible ; ouverture dans le navigateur par défaut.')
    try:
        webbrowser.open(url)
    except (OSError, webbrowser.Error):
        logging.getLogger(__name__).exception('Ouverture du navigateur impossible.')
