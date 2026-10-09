"""Local setup actions, invoked explicitly from the interface."""
import asyncio
import hashlib
import json
import sys
import subprocess
from pathlib import Path

from .config import Configuration
from .model import Controller
from .drivers.hue import HueDriver
from .drivers.nanoleaf import NanoleafDriver


async def command(root,script,*arguments,timeout=100):
    executable=Path(sys.executable)
    if executable.name.casefold()=='pythonw.exe':
        executable=executable.with_name('python.exe')
    options={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
    process=await asyncio.create_subprocess_exec(str(executable),str(root/'scripts'/script),*arguments,
        cwd=root,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,**options)
    try:
        await asyncio.wait_for(process.communicate(),timeout)
        if process.returncode:
            raise RuntimeError('Opération échouée : vérifier le matériel et la fenêtre d’appairage.')
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def import_devices(runtime):
    from .discovery import network
    addresses=await network(cache_path=runtime.root/'local/discovery/inventory.json')
    config=runtime.config.model_dump(mode='json')
    count=0
    for kind in ('hue','nanoleaf'):
        path=runtime.root/'local/secrets'/f'{kind}.json'
        if not path.exists():
            continue
        credentials=json.loads(path.read_text(encoding='utf-8'))
        for stable,key in credentials.items():
            endpoint=addresses.get(stable.casefold())
            if not endpoint:
                continue
            identifier=next((name for name,value in config['controllers'].items() if value['stable_id']==stable),
                'controller_'+hashlib.sha256(stable.encode()).hexdigest()[:8])
            config['controllers'][identifier]={'type':kind,'stable_id':stable}
            if kind=='hue':
                driver=HueDriver(endpoint['host'],key['username'],runtime.root/'local/secrets'/f'hue-{stable}.pem')
            else:
                driver=NanoleafDriver(endpoint['host'],key['auth_token'],endpoint['port'])
            try:
                devices=await driver.discover()
                members=[]
                for device in devices:
                    existing=next((name for name,value in config['devices'].items() if value.get('controller')==identifier
                        and (value.get('resource_id')==device.resource_id or kind=='nanoleaf')),None)
                    name=existing or 'device_'+hashlib.sha256((stable+str(device.resource_id)).encode()).hexdigest()[:10]
                    device.controller=identifier
                    config['devices'][name]=device.model_dump(mode='json')
                    members.append(name)
                    count+=1
                config['groups'].setdefault('group_'+identifier,members)
            finally:
                await driver.close()
    await runtime.configure(Configuration.model_validate(config))
    return count
