"""Version policy and release notes using only Git and the Python standard library."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import tomllib

ROOT=Path(__file__).resolve().parents[1]
VERSION=re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z')
APP_SCRIPTS={'scripts/setup.cmd','scripts/start.cmd','scripts/discover.py',
             'scripts/pair_lights.py','scripts/probe_audio.py','scripts/probe_simulator.py'}


def parse(value):
    match=VERSION.fullmatch(value)
    if match is None:
        raise ValueError('Version attendue : x.y.z, sans zéro initial.')
    return tuple(map(int,match.groups()))


def current(text):
    value=tomllib.loads(text)['project']['version']
    parse(value)
    return value


def next_version(value,level,major_requested=False):
    x,y,z=parse(value)
    if level=='major':
        if not major_requested:
            raise ValueError('Une version majeure exige une demande explicite : --major-requested.')
        return f'{x+1}.0.0'
    if level=='minor':
        return f'{x}.{y+1}.0'
    if level=='patch':
        return f'{x}.{y}.{z+1}'
    raise ValueError('Choisir patch, minor ou major.')


def git(*args,root=ROOT):
    return subprocess.check_output(['git',*args],cwd=root,encoding='utf-8',stderr=subprocess.PIPE).strip()


def project_at(ref,root=ROOT):
    return git('show',f'{ref}:pyproject.toml',root=root)


def runtime_metadata(text):
    document=tomllib.loads(text)
    project={k:v for k,v in document.get('project',{}).items() if k not in
             {'version','description','readme','authors','maintainers','classifiers','urls','license','license-files'}}
    return project,document.get('build-system'),document.get('tool',{}).get('setuptools')


def app_changed(paths,old,new):
    return any((p.startswith('src/') and not p.endswith('.md')) or p.startswith('examples/')
               or p=='requirements.txt' or p in APP_SCRIPTS for p in paths) or (
                   'pyproject.toml' in paths and runtime_metadata(old)!=runtime_metadata(new))


def release_notes(text,version):
    parse(version)
    match=re.search(r'^## \['+re.escape(version)+r'\][^\n]*\n(.*?)(?=^## |\Z)',text,re.M|re.S)
    if match is None or not match.group(1).strip():
        raise ValueError('Entrée de CHANGELOG.md manquante pour '+version+'.')
    return match.group(1).strip()+'\n'


def transition(old,new,changed,major_requested=False):
    previous,following=parse(old),parse(new)
    if following<previous:
        raise ValueError('La version ne peut pas reculer.')
    if changed and following==previous:
        raise ValueError('Modification de l’application : incrémenter z ou y avant publication.')
    if following[0]>previous[0] and not major_requested:
        raise ValueError('Version majeure sans trailer Glareshield-Major-Requested: true.')


def check(base='HEAD',root=ROOT,working=True,major_requested=False,no_app_change=None):
    base=git('rev-parse','--verify','--end-of-options',base+'^{commit}',root=root)
    old=project_at(base,root)
    new=(root/'pyproject.toml').read_text(encoding='utf-8') if working else project_at('HEAD',root)
    paths=git('diff','--name-only',base,*([] if working else ['HEAD']),root=root).splitlines()
    if working:
        paths+=git('ls-files','--others','--exclude-standard',root=root).splitlines()
    changed=app_changed(paths,old,new)
    major=major_requested if working else False
    if working and no_app_change:
        changed=False
    if not working:
        commits=git('rev-list','--no-merges',base+'..HEAD',root=root).splitlines()
        significant=[]
        for commit in commits:
            message=git('show','-s','--format=%B',commit,root=root)
            major|=bool(re.search(r'^Glareshield-Major-Requested: true\s*$',message,re.M))
            parent=git('rev-parse',commit+'^',root=root)
            touched=git('diff','--name-only',parent,commit,root=root).splitlines()
            if app_changed(touched,project_at(parent,root),project_at(commit,root)):
                significant.append(not bool(re.search(r'^Glareshield-No-App-Change: \S[^\n]*$',message,re.M)))
        if changed and significant and not any(significant):
            changed=False
    transition(current(old),current(new),changed,major)
    if current(old)!=current(new):
        release_notes((root/'CHANGELOG.md').read_text(encoding='utf-8'),current(new))
    return current(new),changed


def check_tag(tag,root=ROOT):
    if not tag.startswith('v'):
        raise ValueError('Tag attendu : vX.Y.Z.')
    value=current((root/'pyproject.toml').read_text(encoding='utf-8'))
    if tag!='v'+value:
        raise ValueError('Le tag ne correspond pas à project.version.')
    release_notes((root/'CHANGELOG.md').read_text(encoding='utf-8'),value)
    previous=[]
    for item in git('tag','--merged','HEAD','--list','v*',root=root).splitlines():
        try:
            if parse(item[1:])<parse(value):
                previous.append(item)
        except ValueError:
            continue
    if previous:
        check(max(previous,key=lambda t:parse(t[1:])),root,working=False)
    return value


def bump(root,level,summary,major_requested=False):
    path=root/'pyproject.toml'
    text=path.read_text(encoding='utf-8')
    old=current(text)
    value=next_version(old,level,major_requested)
    journal=root/'CHANGELOG.md'
    log=journal.read_text(encoding='utf-8')
    if re.search(r'^## \['+re.escape(value)+r'\]',log,re.M):
        raise ValueError('Cette version existe déjà dans CHANGELOG.md.')
    lines=summary.splitlines()
    if len(lines)!=1 or not summary.strip():
        raise ValueError('Résumé court requis, sur une ligne.')
    replaced,count=re.subn(r'(?m)^version\s*=\s*"'+re.escape(old)+r'"\s*$',f'version = "{value}"',text,count=1)
    if count!=1 or current(replaced)!=value:
        raise ValueError('Déclaration de version non reconnue ; aucun fichier modifié.')
    date=datetime.now(timezone.utc).date().isoformat()
    entry=f'## [{value}] - {date}\n\n- {summary.strip()}\n\n'
    if major_requested and level=='major':
        entry+='Version majeure explicitement demandée par l’utilisateur.\n\n'
    position=log.find('## [')
    if position<0:
        raise ValueError('Structure de CHANGELOG.md non reconnue.')
    journal.write_text(log[:position]+entry+log[position:],encoding='utf-8')
    path.write_text(replaced,encoding='utf-8')
    return value


def main():
    parser=argparse.ArgumentParser(description='Politique x.y.z de Glareshield')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('current')
    commands.add_parser('notes')
    validation=commands.add_parser('check')
    validation.add_argument('--base')
    validation.add_argument('--tag')
    validation.add_argument('--major-requested',action='store_true')
    validation.add_argument('--no-app-change',help='Justification locale à reprendre dans le trailer du commit')
    change=commands.add_parser('bump')
    change.add_argument('level',choices=['patch','minor','major'])
    change.add_argument('--summary',required=True)
    change.add_argument('--major-requested',action='store_true')
    args=parser.parse_args()
    try:
        if args.command=='current':
            print(current((ROOT/'pyproject.toml').read_text(encoding='utf-8')))
        elif args.command=='notes':
            print(release_notes((ROOT/'CHANGELOG.md').read_text(encoding='utf-8'),current((ROOT/'pyproject.toml').read_text(encoding='utf-8'))),end='')
        elif args.command=='bump':
            print(bump(ROOT,args.level,args.summary,args.major_requested))
        elif args.tag:
            print('Tag valide : '+check_tag(args.tag))
        else:
            if args.base and (args.major_requested or args.no_app_change):
                raise ValueError('Les exceptions locales ne remplacent pas les trailers des commits en CI.')
            value,changed=check(args.base or 'HEAD',working=args.base is None,
                                major_requested=args.major_requested,no_app_change=args.no_app_change)
            print(f'Version valide : {value} ; modification application : {changed}.')
    except (ValueError,KeyError,subprocess.CalledProcessError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':
    main()
