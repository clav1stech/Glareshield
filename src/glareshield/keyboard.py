"""Read only configured Windows key states, without hooks or input injection."""
import asyncio
import ctypes


class KeyboardSource:
    def __init__(self,sources,update,reader=None):
        self.sources={key:source for key,source in sources.items() if source.type=='keyboard'}
        self.update=update
        self.stopping=False
        if reader is None:
            reader=ctypes.windll.user32.GetAsyncKeyState
            reader.argtypes=[ctypes.c_int]
            reader.restype=ctypes.c_short
        self.reader=reader

    async def run(self):
        try:
            while not self.stopping:
                self.update({key:bool(self.reader(source.key_code)&0x8000) for key,source in self.sources.items()})
                await asyncio.sleep(.02)
        finally:
            self.update({key:False for key in self.sources})

    def stop(self):
        self.stopping=True
