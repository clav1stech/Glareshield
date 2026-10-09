from __future__ import annotations

import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Configuration
from .model import LightState
from .setup import command,import_devices


def create_app(runtime):
    token=secrets.token_urlsafe(32)
    @asynccontextmanager
    async def lifespan(app):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()
    app=FastAPI(title='Glareshield',lifespan=lifespan,docs_url=None,redoc_url=None)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

    @app.middleware('http')
    async def local_mutations(request:Request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-glareshield-token',''),token):
                return JSONResponse({'detail':'Session locale invalide.'},status_code=403)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.get('/',response_class=HTMLResponse)
    async def index():
        return (Path(__file__).parent/'static/index.html').read_text(encoding='utf-8').replace('__TOKEN__',token)

    @app.get('/api/status')
    async def status():
        return runtime.status()

    @app.get('/api/config')
    async def configuration():
        return runtime.config.model_dump(mode='json')

    @app.put('/api/config')
    async def configure(payload:dict):
        try:
            checked=Configuration.model_validate(payload)
            await runtime.configure(checked)
            return {'ok':True}
        except Exception as error:
            message='Configuration refusée : '+type(error).__name__
            if hasattr(error,'errors'):
                message+=' ; '+', '.join('.'.join(str(part) for part in item['loc']) for item in error.errors())
            raise HTTPException(400,message) from None

    @app.post('/api/suspend')
    async def suspend(payload:dict):
        runtime.suspended=bool(payload.get('suspended'))
        return {'ok':True}

    @app.post('/api/scope')
    async def scope(payload:dict):
        value=payload.get('scope')
        if value not in runtime.config.scopes:
            raise HTTPException(400,'Portée inconnue.')
        await runtime.change_scope(value)
        return {'ok':True}

    @app.post('/api/shutdown')
    async def shutdown():
        runtime.request_exit()
        return {'ok':True}

    @app.post('/api/test/source')
    async def source_test(payload:dict):
        identifier=payload.get('source')
        value=payload.get('value')
        duration=payload.get('seconds',runtime.config.settings.test_duration_s)
        if identifier not in runtime.config.sources or not isinstance(value,(bool,int,float)) or not isinstance(duration,(int,float)) or not 1<=duration<=30:
            raise HTTPException(400,'Source ou durée invalide.')
        runtime.manual[identifier]=(value,time.monotonic()+duration)
        return {'ok':True}

    @app.post('/api/identify/{identifier}')
    async def identify(identifier:str):
        device=runtime.config.devices.get(identifier)
        if device is None or device.kind!='light':
            raise HTTPException(400,'Lampe inconnue.')
        async with runtime.engine.lock:
            if identifier in runtime.engine.snapshots:
                raise HTTPException(409,'Suspendre les règles avant de repérer cette lampe.')
            driver=runtime.engine.drivers.get(device.driver)
            if driver is None:
                raise HTTPException(503,'Pilote indisponible.')
            try:
                # Persist before any temporary identification command.
                if not await runtime.engine.capture(identifier):
                    raise RuntimeError()
                await driver.identify(identifier,device)
            finally:
                if identifier in runtime.engine.snapshots:
                    await runtime.engine.restore_one(identifier)
        return {'ok':True}

    @app.get('/api/sounds')
    async def sounds():
        return [path.name for path in (runtime.root/'local/sounds').glob('*.wav')]

    @app.post('/api/setup/discover')
    async def discover():
        try:
            await command(runtime.root,'discover.py','--seconds','3',timeout=30)
            import json
            inventory=json.loads((runtime.root/'local/discovery/inventory.json').read_text(encoding='utf-8'))
            return {'services':len(inventory.get('network',[])),'airplay':len(inventory.get('airplay',[]))}
        except Exception:
            raise HTTPException(503,'Découverte indisponible.') from None

    @app.post('/api/setup/pair')
    async def pair(payload:dict):
        driver=payload.get('driver')
        model=payload.get('model')
        if driver not in ('hue','nanoleaf') or (model is not None and not isinstance(model,str)):
            raise HTTPException(400,'Pilote invalide.')
        args=[driver,'--seconds','90']
        if model:
            args+=['--model',model]
        try:
            await command(runtime.root,'pair_lights.py',*args)
            return {'ok':True}
        except Exception:
            raise HTTPException(503,'Appairage échoué : vérifier la sélection et la fenêtre physique d’appairage.') from None

    @app.post('/api/setup/import')
    async def import_paired():
        try:
            return {'devices':await import_devices(runtime)}
        except Exception:
            raise HTTPException(503,'Import indisponible ; configuration précédente conservée si la validation échoue.') from None

    @app.post('/api/test/sound/{identifier}')
    async def sound_test(identifier:str,payload:dict):
        effect=runtime.config.effects.get(payload.get('effect'))
        device=runtime.config.devices.get(identifier)
        if device is None or device.kind!='audio' or getattr(effect,'type',None)!='sound':
            raise HTTPException(400,'Appareil ou effet sonore invalide.')
        if identifier not in runtime.config.select(['scope:active']):
            raise HTTPException(409,'Cette sortie est hors de la portée active.')
        success,_=await runtime.engine.call(identifier,lambda:runtime.engine.drivers[device.driver].play(identifier,device,effect),timeout=runtime.config.settings.sound_timeout_s)
        if not success:
            raise HTTPException(503,'Diffusion indisponible.')
        return {'ok':True}

    return app
