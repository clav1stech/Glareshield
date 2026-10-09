"""Change one paired controller briefly, restore and verify its original state."""
import asyncio
import ipaddress
import json
from pathlib import Path

from glareshield.config import atomic_write
from glareshield.drivers.nanoleaf import NanoleafDriver
from glareshield.model import Device,LightState

ROOT=Path(__file__).resolve().parents[1]


async def main():
    inventory=json.loads((ROOT/'local/discovery/inventory.json').read_text(encoding='utf-8'))
    keys=json.loads((ROOT/'local/secrets/nanoleaf.json').read_text(encoding='utf-8'))
    candidates=[d for d in inventory['network'] if d['service']=='_nanoleafapi._tcp.local.'
        and (d['properties'].get('eui64') or d['properties'].get('id')) in keys]
    if len(candidates)!=1:
        raise RuntimeError('Sélection non unique parmi les contrôleurs appairés.')
    controller=candidates[0]
    identifier=controller['properties'].get('eui64') or controller['properties']['id']
    host=next(a for a in controller['addresses'] if ipaddress.ip_address(a).version==4)
    driver=NanoleafDriver(host,keys[identifier]['auth_token'],controller['port'])
    checkpoint=ROOT/'local/state/nanoleaf-test-snapshots.json'
    snapshot=None
    device=Device(name='Test',driver='nanoleaf')
    try:
        if checkpoint.exists():
            pending=json.loads(checkpoint.read_text(encoding='utf-8'))
            if pending:
                await driver.restore(identifier,device,pending)
                atomic_write(checkpoint,'{}')
        await driver.discover()
        snapshot=await driver.snapshot(identifier,device)
        atomic_write(checkpoint,json.dumps(snapshot))
        await driver.apply(identifier,device,LightState(color=[255,0,0],brightness=60))
        await asyncio.sleep(3)
    finally:
        try:
            if snapshot:
                await driver.restore(identifier,device,snapshot)
                restored=await driver.snapshot(identifier,device)
                before,after=snapshot['state'],restored['state']
                fields=['on','brightness','colorMode']
                fields+=['ct'] if before['colorMode']=='ct' else ['hue','sat'] if before['colorMode']=='hs' else []
                if any(before[key]!=after[key] for key in fields) or snapshot['effect']!=restored['effect']:
                    raise RuntimeError('Écart de restauration ; snapshot conservé.')
                atomic_write(checkpoint,'{}')
                print('Couleur et restauration Nanoleaf vérifiées.')
        finally:
            await driver.close()


if __name__=='__main__':
    asyncio.run(main())
