"""List LVar names declared in an installed aircraft package, without starting the simulator."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = {'.xml', '.js', '.html', '.json', '.cfg'}
# Behaviour templates name variables in tags such as <VAR_NAME>; RPN code reads (L:NAME, unit).
TAG = re.compile(r'<(\w*VAR\w*)>\s*([A-Za-z][A-Za-z0-9_]{2,80})\s*</\1>')
RPN = re.compile(r'\(L:([A-Za-z][A-Za-z0-9_]{2,80})\s*[,)]')
CONFIGS = [  # MSFS 2024 then 2020, Microsoft Store and Steam editions.
    ('LOCALAPPDATA', 'Packages/Microsoft.Limitless_8wekyb3d8bbwe/LocalCache/UserCfg.opt'),
    ('APPDATA', 'Microsoft Flight Simulator 2024/UserCfg.opt'),
    ('LOCALAPPDATA', 'Packages/Microsoft.FlightSimulator_8wekyb3d8bbwe/LocalCache/UserCfg.opt'),
    ('APPDATA', 'Microsoft Flight Simulator/UserCfg.opt'),
]


def package_roots() -> list[Path]:
    roots = []
    for variable, relative in CONFIGS:
        base = os.environ.get(variable)
        config = Path(base)/relative if base else None
        if not config or not config.exists():
            continue
        match = re.search(r'^InstalledPackagesPath\s+"([^"]+)"', config.read_text(encoding='utf-8', errors='ignore'), re.M)
        if match:
            roots += [Path(match.group(1))/folder for folder in ('Community', 'Official/OneStore', 'Official/Steam')]
    return [root for root in roots if root.is_dir()]


def scan(package: Path) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for path in package.rglob('*'):
        if path.suffix.lower() not in TEXT or not path.is_file() or path.stat().st_size > 30_000_000:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        names = [name for _, name in TAG.findall(text)]+RPN.findall(text)
        for name in names:
            found.setdefault(name, set()).add(path.relative_to(package).as_posix())
    return {name: sorted(files) for name, files in sorted(found.items())}


def main() -> None:
    parser = argparse.ArgumentParser(description='Recherche des LVars déclarées dans le paquet d’un avion')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--package', type=Path, help='Dossier du paquet de l’avion')
    source.add_argument('--name', help='Partie du nom du dossier du paquet, par exemple fnx-aircraft')
    parser.add_argument('--filter', default='', help='Expression régulière sur les noms, par exemple FCU|FLAP')
    parser.add_argument('--write-probe', action='store_true',
                        help='Écrire les noms filtrés dans local/discovery/probe-variables.json pour la sonde')
    args = parser.parse_args()
    if args.package:
        packages = [args.package]
    else:
        packages = sorted({path for root in package_roots() for path in root.iterdir()
                           if path.is_dir() and args.name.casefold() in path.name.casefold()})
    packages = [package for package in packages if package.is_dir()]
    if not packages:
        parser.exit(1, 'Paquet introuvable : préciser --package.\n')
    pattern = re.compile(args.filter, re.I)
    result = {}
    for package in packages:
        names = scan(package)
        result[package.name] = names
        selected = [name for name in names if pattern.search(name)]
        print(f'{package.name} : {len(names)} LVars, {len(selected)} retenues')
        for name in selected:
            print('  '+name)
    output = ROOT/'local/discovery/lvar-names.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=1), encoding='utf-8')
    print('Inventaire privé enregistré dans local/discovery/lvar-names.json')
    if args.write_probe:
        selected = sorted({name for names in result.values() for name in names if pattern.search(name)})
        if not 1 <= len(selected) <= 80:
            parser.exit(1, 'Entre 1 et 80 noms requis pour la sonde : affiner --filter.\n')
        (ROOT/'local/discovery/probe-variables.json').write_text(json.dumps(selected, indent=1), encoding='utf-8')
        print(f'{len(selected)} noms écrits dans local/discovery/probe-variables.json')


if __name__ == '__main__':
    main()
