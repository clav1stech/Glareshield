import asyncio
import time
from pathlib import Path

from ..model import Device


class AirPlayDriver:
    def __init__(self,identifier,sound_directory):
        self.identifier=identifier
        self.sound_directory=Path(sound_directory).resolve()
        self.target=None
        self.lock=asyncio.Lock()
        self.timings=[]
        self.connection=None

    async def discover(self):
        import pyatv
        from pyatv.const import Protocol
        devices=await pyatv.scan(asyncio.get_running_loop(),timeout=3,protocol=Protocol.RAOP)
        candidates=[device for device in devices if any(
            value.replace(':','').casefold()==self.identifier.replace(':','').casefold()
            for value in device.all_identifiers)]
        if len(candidates)!=1:
            raise ConnectionError('Cible AirPlay non découverte de façon unique.')
        self.target=candidates[0]
        return [Device(name=self.target.name,driver='airplay',kind='audio',stable_id=self.identifier)]

    async def play(self,identifier,device,effect):
        import pyatv
        from pyatv.const import Protocol
        path=(self.sound_directory/effect.file).resolve()
        if not path.is_relative_to(self.sound_directory) or not path.is_file():
            raise ValueError('Son absent du dossier local des sons.')
        async with self.lock:
            started=time.monotonic()
            if self.target is None:
                await self.discover()
            connection=None
            try:
                connection=await pyatv.connect(self.target,asyncio.get_running_loop(),protocol=Protocol.RAOP)
                self.connection=connection
                await connection.audio.set_volume(effect.volume*100)
                ready=time.monotonic()
                await connection.stream.stream_file(str(path))
                self.timings.append({'prepare_s':ready-started,'total_s':time.monotonic()-started})
            except Exception:
                self.target=None
                raise RuntimeError('Diffusion AirPlay interrompue.') from None
            finally:
                if connection:
                    tasks=connection.close()
                    if tasks:
                        await asyncio.gather(*tasks,return_exceptions=True)
                self.connection=None

    async def close(self):
        if self.connection:
            tasks=self.connection.close()
            if tasks:
                await asyncio.gather(*tasks,return_exceptions=True)
            self.connection=None
