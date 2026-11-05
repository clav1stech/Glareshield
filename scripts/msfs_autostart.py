"""Ajoute ou retire Glareshield du lancement automatique de MSFS 2024 (exe.xml).

Usage : python scripts/msfs_autostart.py install|remove|status [--exe-xml CHEMIN] [--window]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NAME='Glareshield'


def candidates():
    local=Path(os.environ.get('LOCALAPPDATA',''))
    roaming=Path(os.environ.get('APPDATA',''))
    return [local/'Packages/Microsoft.Limitless_8wekyb3d8bbwe/LocalCache/exe.xml',
            roaming/'Microsoft Flight Simulator 2024/exe.xml']


def find_exe_xml():
    for path in candidates():
        if path.parent.is_dir():
            return path
    raise SystemExit('Dossier de MSFS 2024 introuvable ; indiquer --exe-xml.')


def load(path):
    if path.exists():
        return ET.parse(path)
    root=ET.Element('SimBase.Document',{'Type':'Launch','version':'1,0'})
    for tag,text in (('Descr','Launch'),('Filename','EXE.xml'),('Disabled','False'),
                     ('Launch.ManualLoad','False')):
        ET.SubElement(root,tag).text=text
    return ET.ElementTree(root)


def entries(tree):
    return [e for e in tree.getroot().findall('Launch.Addon') if (e.findtext('Name') or '').strip()==NAME]


def build_entry(root,window=False):
    python=root/'local/.venv/Scripts/pythonw.exe'
    if not python.exists():
        raise SystemExit('Environnement absent : exécuter scripts/setup.cmd.')
    command=f'"{root/"scripts/launch.pyw"}"'+(' --window' if window else '')
    entry=ET.Element('Launch.Addon')
    for tag,text in (('Name',NAME),('Disabled','False'),('ManualLoad','False'),
                     ('Path',str(python)),('CommandLine',command),('NewConsole','False')):
        ET.SubElement(entry,tag).text=text
    return entry


def save(tree,path):
    if path.exists():
        shutil.copy2(path,path.with_name(path.name+'.glareshield.bak'))
    ET.indent(tree)
    tree.write(path,encoding='utf-8',xml_declaration=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','remove','status'])
    parser.add_argument('--exe-xml',type=Path)
    parser.add_argument('--window',action='store_true',help='Ouvrir aussi la fenêtre dédiée')
    args=parser.parse_args(argv)
    path=args.exe_xml or find_exe_xml()
    tree=load(path)
    found=entries(tree)
    if args.action=='status':
        print(f'{path} : '+('Glareshield est lancé avec MSFS.' if found else 'non configuré.'))
        return 0
    for entry in found:
        tree.getroot().remove(entry)
    if args.action=='install':
        tree.getroot().append(build_entry(ROOT,args.window))
    save(tree,path)
    print(f'{path} : '+('Glareshield sera lancé avec MSFS.' if args.action=='install' else 'entrée retirée.'))
    return 0


if __name__=='__main__':
    sys.exit(main())
