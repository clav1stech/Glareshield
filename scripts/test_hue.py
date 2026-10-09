"""Measure a configured Hue test and restore every captured state."""
import argparse
import asyncio
import ipaddress
import json
import time
from pathlib import Path

from glareshield.config import atomic_write
from glareshield.drivers.hue import HueDriver
from glareshield.model import Device,LightState

ROOT=Path(__file__).resolve().parents[1]


async def main(seconds):
    inventory=json.loads((ROOT/'local/discovery/inventory.json').read_text(encoding='utf-8'))
    bridge=next(d for d in inventory['network'] if d['service']=='_hue._tcp.local.')
    identifier=bridge['properties']['bridgeid']
    host=next(a for a in bridge['addresses'] if ipaddress.ip_address(a).version==4)
    key=json.loads((ROOT/'local/secrets/hue.json').read_text(encoding='utf-8'))[identifier]['username']
    driver=HueDriver(host,key,ROOT/'local/secrets'/f'hue-{identifier}.pem')
    checkpoint=ROOT/'local/state/hue-test-snapshots.json'
    snapshots={}
    devices={}
    measurements=[]
    report=None
    try:
        devices={d.resource_id:d for d in await driver.discover()}
        if checkpoint.exists():
            snapshots=json.loads(checkpoint.read_text(encoding='utf-8'))
            for resource,entry in list(snapshots.items()):
                await driver.restore(resource,Device.model_validate(entry['device']),entry['state'])
                del snapshots[resource]
                atomic_write(checkpoint,json.dumps(snapshots))
        for resource,device in devices.items():
            snapshots[resource]={'device':device.model_dump(mode='json'),
                                 'state':await driver.snapshot(resource,device)}
            atomic_write(checkpoint,json.dumps(snapshots))
        await driver.identify(next(iter(devices)),next(iter(devices.values())))
        start=time.monotonic()
        count=0
        while time.monotonic()-start < seconds:
            wanted=start+count*.5
            await asyncio.sleep(max(0,wanted-time.monotonic()))
            state=LightState(color=[255,0,0],brightness=100 if count%2==0 else 15)
            sent=time.monotonic()
            failures=await driver.apply_batch({key:(device,state) for key,device in devices.items()})
            measurements.append({'scheduled_s':count*.5,'started_s':sent-start,
                                 'duration_s':time.monotonic()-sent,'errors':len(failures)})
            if failures:
                raise RuntimeError('Erreur de commande Hue ; restauration nécessaire.')
            count+=1
        report={'seconds':seconds,'devices':len(devices),'commands':len(driver.command_times),
                'measurements':measurements}
        atomic_write(ROOT/'local/discovery/hue-rate-test.json',json.dumps(report,indent=2))
        print('Mesure terminée ; rapport privé local/discovery/hue-rate-test.json')
    finally:
        errors=0
        entries=list(snapshots.items())
        outcomes=await asyncio.gather(*(driver.restore(resource,Device.model_validate(entry['device']),entry['state'])
                                       for resource,entry in entries),return_exceptions=True)
        for (resource,entry),outcome in zip(entries,outcomes):
            if not isinstance(outcome,BaseException):
                del snapshots[resource]
                atomic_write(checkpoint,json.dumps(snapshots))
            else:
                errors+=1
        if report is not None:
            report['api_diagnostics']=driver.diagnostics
            report['restore_errors']=[str(outcome) if isinstance(outcome,Exception) else type(outcome).__name__
                for outcome in outcomes if isinstance(outcome,BaseException)]
            atomic_write(ROOT/'local/discovery/hue-rate-test.json',json.dumps(report,indent=2))
        await driver.close()
        print('Restauration complète.' if not errors else f'Restauration à reprendre : {errors} appareils.')
        if errors:
            raise RuntimeError('Snapshots conservés pour reprise de la restauration.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Test Hue : clignotement rouge 1 Hz puis restauration')
    parser.add_argument('--seconds',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.seconds<=300:
        parser.error('Durée entre 1 et 300 secondes requise.')
    asyncio.run(main(args.seconds))
