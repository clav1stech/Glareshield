import argparse
import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

import uvicorn

from .runtime import Runtime
from .web import create_app
from .desktop import application_icon,open_window

RESTART_ENV='GLARESHIELD_RESTARTED'


async def open_when_ready(server,root,port):
    while not server.started:
        await asyncio.sleep(.05)
    await asyncio.to_thread(open_window,root,port)


async def serve(root,path,port,tray=True,window=False):
    # Reserve the port before connecting to any hardware.
    # Après « Redémarrer », l'ancienne instance libère le port quelques instants plus tard.
    for attempt in range(50 if os.environ.get(RESTART_ENV) else 1):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            listener.bind(('127.0.0.1',port))
            listener.listen(128)
            listener.setblocking(False)
            break
        except OSError:
            listener.close()
            if attempt==49 or not os.environ.get(RESTART_ENV):
                raise RuntimeError('Application déjà lancée ou port local indisponible.') from None
            await asyncio.sleep(.1)
    runtime=Runtime(root,path)
    server=uvicorn.Server(uvicorn.Config(create_app(runtime),host='127.0.0.1',port=port,
        access_log=False,log_level='warning',use_colors=False))
    restart=[False]
    runtime.request_exit=lambda:setattr(server,'should_exit',True)
    def request_restart():
        restart[0]=True
        server.should_exit=True
    runtime.request_restart=request_restart
    icon=None
    if tray:
        import pystray
        image=application_icon()
        def toggle(icon,item):
            runtime.suspended=not runtime.suspended
        def quit_app(icon,item):
            server.should_exit=True
            icon.stop()
        icon=pystray.Icon('glareshield',image,'Glareshield',pystray.Menu(
            pystray.MenuItem('Ouvrir Glareshield',lambda: open_window(root,port),default=True),
            pystray.MenuItem('Suspendre / reprendre les règles',toggle),
            pystray.MenuItem('Quitter et restaurer les lampes',quit_app)))
        icon.run_detached()
    opening=asyncio.create_task(open_when_ready(server,root,port)) if window else None
    try:
        await server.serve(sockets=[listener])
    finally:
        if opening:
            opening.cancel()
            await asyncio.gather(opening,return_exceptions=True)
        if icon:
            icon.stop()
        listener.close()
    return restart[0]


def relaunch(root,path,port,tray):
    """Démarre une nouvelle instance détachée ; la fenêtre ouverte se reconnecte d'elle-même."""
    command=[sys.executable,'-m','glareshield.app','--root',str(root),'--config',str(path),'--port',str(port)]
    if not tray:
        command.append('--no-tray')
    package=str(Path(__file__).resolve().parents[1])
    environment={**os.environ,RESTART_ENV:'1','PYTHONPATH':os.pathsep.join(filter(None,[package,os.environ.get('PYTHONPATH')]))}
    flags=(subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW) if os.name=='nt' else 0
    subprocess.Popen(command,cwd=root,env=environment,creationflags=flags,close_fds=True,
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def main():
    parser=argparse.ArgumentParser(description='Glareshield — interface locale et moteur')
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--config',type=Path)
    parser.add_argument('--port',type=int,default=8777)
    parser.add_argument('--no-tray',action='store_true')
    parser.add_argument('--window',action='store_true',help='Ouvrir une fenêtre dédiée après le démarrage')
    args=parser.parse_args()
    root=args.root.resolve()
    stream=None
    if sys.stdout is None or sys.stderr is None:
        directory=root/'local/logs'
        directory.mkdir(parents=True,exist_ok=True)
        stream=(directory/'launcher.log').open('a',encoding='utf-8',buffering=1)
        sys.stdout=sys.stdout or stream
        sys.stderr=sys.stderr or stream
    path=args.config or root/'local/config.yaml'
    restart=False
    try:
        restart=asyncio.run(serve(root,path,args.port,not args.no_tray,args.window))
    except KeyboardInterrupt:
        pass
    finally:
        if stream:
            stream.close()
    if restart:
        relaunch(root,path,args.port,not args.no_tray)


if __name__=='__main__':
    main()
