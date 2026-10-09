"""Read only configured Windows key states, without hooks or input injection."""
import asyncio
import ctypes
import time


class KeyboardSource:
    def __init__(self,sources,update,reader=None):
        self.sources={key:source for key,source in sources.items() if source.type=='keyboard'}
        self.update=update
        self.stopping=False
        self.wake=asyncio.Event()
        if reader is None:
            reader=ctypes.windll.user32.GetAsyncKeyState
            reader.argtypes=[ctypes.c_int]
            reader.restype=ctypes.c_short
        self.reader=reader

    async def run(self):
        due={key:0 for key in self.sources}
        try:
            while not self.stopping:
                now=time.monotonic()
                values={}
                for key,source in self.sources.items():
                    if now>=due[key]:
                        values[key]=bool(self.reader(source.key_code)&0x8000)
                        due[key]=now+source.poll_ms/1000
                if values:
                    self.update(values)
                try:
                    await asyncio.wait_for(self.wake.wait(),min(source.poll_ms for source in self.sources.values())/1000)
                except TimeoutError:
                    pass
        finally:
            self.update({key:False for key in self.sources})

    def stop(self):
        self.stopping=True
        self.wake.set()
