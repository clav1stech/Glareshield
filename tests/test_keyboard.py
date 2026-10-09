import asyncio
from glareshield.keyboard import KeyboardSource
from glareshield.model import Source


async def test_only_configured_key_is_read_and_release_is_reported():
    calls=[]
    pressed=[True]
    def reader(code):
        calls.append(code)
        return -32768 if pressed[0] else 0
    messages=[]
    source=KeyboardSource({'ptt':Source(type='keyboard',key_code=65)},messages.append,reader)
    task=asyncio.create_task(source.run())
    await asyncio.sleep(.05)
    pressed[0]=False
    await asyncio.sleep(.05)
    source.stop()
    await task
    assert set(calls)=={65}
    assert any(m['ptt'] for m in messages)
    assert messages[-1]=={'ptt':False}
