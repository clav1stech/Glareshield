import argparse
import asyncio
import socket
import sys
import webbrowser
from pathlib import Path

import uvicorn

from .runtime import Runtime
from .web import create_app


async def serve(root,path,port,tray=True):
    # Reserve the port before connecting to any hardware.
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        listener.bind(('127.0.0.1',port))
        listener.listen(128)
        listener.setblocking(False)
    except OSError:
        listener.close()
        raise RuntimeError('Application déjà lancée ou port local indisponible.') from None
    runtime=Runtime(root,path)
    server=uvicorn.Server(uvicorn.Config(create_app(runtime),host='127.0.0.1',port=port,
        access_log=False,log_level='warning',use_colors=False))
    runtime.request_exit=lambda:setattr(server,'should_exit',True)
    icon=None
    if tray:
        import pystray
        from PIL import Image,ImageDraw
        image=Image.new('RGBA',(64,64),(16,21,31,255))
        draw=ImageDraw.Draw(image)
        draw.line([(10,42),(24,20),(32,34),(40,20),(54,42)],fill=(116,191,255,255),width=5)
        def toggle(icon,item):
            runtime.suspended=not runtime.suspended
        def quit_app(icon,item):
            server.should_exit=True
            icon.stop()
        icon=pystray.Icon('glareshield',image,'Glareshield',pystray.Menu(
            pystray.MenuItem('Ouvrir Glareshield',lambda: webbrowser.open(f'http://127.0.0.1:{port}'),default=True),
            pystray.MenuItem('Suspendre / reprendre les règles',toggle),
            pystray.MenuItem('Quitter et restaurer les lampes',quit_app)))
        icon.run_detached()
    try:
        await server.serve(sockets=[listener])
    finally:
        if icon:
            icon.stop()
        listener.close()


def main():
    parser=argparse.ArgumentParser(description='Glareshield — interface locale et moteur')
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--config',type=Path)
    parser.add_argument('--port',type=int,default=8777)
    parser.add_argument('--no-tray',action='store_true')
    args=parser.parse_args()
    root=args.root.resolve()
    stream=None
    if sys.stdout is None or sys.stderr is None:
        directory=root/'local/logs'
        directory.mkdir(parents=True,exist_ok=True)
        stream=(directory/'launcher.log').open('a',encoding='utf-8',buffering=1)
        sys.stdout=sys.stdout or stream
        sys.stderr=sys.stderr or stream
    try:
        asyncio.run(serve(root,args.config or root/'local/config.yaml',args.port,not args.no_tray))
    except KeyboardInterrupt:
        pass
    finally:
        if stream:
            stream.close()


if __name__=='__main__':
    main()
