import asyncio
import time
from pathlib import Path

from glareshield.model import Source
from glareshield.simulator import SimulatorSource


def reconnect_worker(sources,pipe,stop):
    marker=Path(sources['fixture']['name'])
    number=int(marker.read_text())+1 if marker.exists() else 1
    marker.write_text(str(number))
    pipe.send({'connected':True,'paused':number==2,'values':{'fixture':number}})
    if number==1:
        pipe.close()
        return
    while not stop.wait(.05):
        pipe.send({'connected':True,'paused':True,'values':{'fixture':number}})
    pipe.close()


def blocked_worker(sources,pipe,stop):
    time.sleep(60)


async def test_disconnection_clears_values_and_automatically_reconnects(tmp_path):
    messages=[]
    source=SimulatorSource({'fixture':Source(type='lvar',name=str(tmp_path/'counter'))},
        messages.append,worker_target=reconnect_worker)
    task=asyncio.create_task(source.run())
    try:
        async with asyncio.timeout(15):
            while not any(m['values'].get('fixture')==2 for m in messages):
                await asyncio.sleep(.05)
    finally:
        source.stop()
        await task
    assert any(not m['connected'] and m['values']['fixture'] is None for m in messages)
    assert any(m['connected'] and m['paused'] for m in messages)
    assert source.process is None


async def test_blocking_dll_does_not_block_shutdown():
    source=SimulatorSource({},lambda m:None,worker_target=blocked_worker,heartbeat_s=.2)
    task=asyncio.create_task(source.run())
    await asyncio.sleep(.1)
    source.stop()
    await asyncio.wait_for(task,5)
    assert source.process is None
