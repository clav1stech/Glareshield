"""Reject private paths or known installation data in the Git index."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'.gitignore','README.md','requirements.txt',
           'AGENTS.md','CHANGELOG.md','docs/versioning.md','scripts/version.py',
           'tests/test_version.py','.github/workflows/version.yml',
           'docs/architecture.md','docs/privacy.md','docs/discovery.md',
           'scripts/discover.py','scripts/pair_lights.py','scripts/probe_audio.py',
           'scripts/probe_simulator.py','scripts/setup.cmd','scripts/check_public.py',
           'tests/test_privacy.py','tests/test_engine.py','tests/test_hue.py',
           'scripts/test_hue.py','pyproject.toml','examples/demo.yaml',
           'src/glareshield/__init__.py','src/glareshield/model.py',
           'src/glareshield/config.py','src/glareshield/colors.py',
           'src/glareshield/effects.py','src/glareshield/engine.py','src/glareshield/cli.py',
           'src/glareshield/drivers/__init__.py','src/glareshield/drivers/base.py',
           'src/glareshield/drivers/mock.py','src/glareshield/drivers/hue.py',
           'src/glareshield/drivers/nanoleaf.py','src/glareshield/drivers/airplay.py',
           'src/glareshield/drivers/routed.py','src/glareshield/static/index.html',
           'src/glareshield/app.py','src/glareshield/runtime.py','src/glareshield/web.py',
           'src/glareshield/setup.py','src/glareshield/discovery.py','src/glareshield/simulator.py',
           'src/glareshield/audio.py','src/glareshield/keyboard.py','src/glareshield/sounds.py',
           'scripts/start.cmd','scripts/test_nanoleaf.py','tests/test_nanoleaf.py',
           'tests/test_simulator.py','tests/test_audio.py','tests/test_keyboard.py',
           'tests/test_web.py','tests/test_runtime.py'}


def identifiers(value, sensitive=False):
    if isinstance(value,dict):
        for key,child in value.items():
            yield from identifiers(child,key in {'name','server','addresses','identifier','id',
                'bridgeid','eui64','deviceid','output_id','output_name','serialNo'})
    elif isinstance(value,list):
        for child in value:
            yield from identifiers(child,sensitive)
    elif sensitive and isinstance(value,str) and len(value) >= 8:
        yield value.casefold()


def main():
    def git(*args):
        return subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}',*args],
                                       cwd=ROOT,stderr=subprocess.DEVNULL)
    paths = git('ls-files','-z').decode('utf-8').split('\0')
    needles = set()
    for filename in (ROOT/'local/discovery').glob('*.json'):
        try:
            needles.update(identifiers(json.loads(filename.read_text(encoding='utf-8-sig'))))
        except (ValueError,OSError):
            raise SystemExit('Audit interrompu : un rapport privé est illisible.')
    secrets = ROOT/'local/secrets'
    for filename in secrets.glob('*.json'):
        def strings(value):
            if isinstance(value,dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value,list):
                for child in value:
                    yield from strings(child)
            elif isinstance(value,str) and len(value) >= 12:
                yield value.casefold()
        needles.update(strings(json.loads(filename.read_text(encoding='utf-8'))))
    failures = []
    for name in filter(None,paths):
        if name not in ALLOWED:
            failures.append((name,'chemin non autorisé'))
            continue
        data = git('show',f':{name}').decode('utf-8-sig')
        if any(needle in data.casefold() for needle in needles):
            failures.append((name,'donnée privée détectée'))
        if re.search(r'(?i)(?:[A-Z]:[\\/]Users[\\/]|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',data):
            failures.append((name,'chemin personnel ou clé privée'))
        if re.search(r'\b(?:192\.168\.(?:\d{1,3}\.)\d{1,3}|10\.(?:\d{1,3}\.){2}\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})\b',data):
            failures.append((name,'adresse de réseau privé'))
    if failures:
        for name,reason in failures:
            print(f'Refus : {name} ({reason})')
        raise SystemExit(1)
    print(f'Audit réussi : {len(list(filter(None,paths)))} fichiers publics ; aucune donnée privée connue détectée.')


if __name__ == '__main__':
    main()
