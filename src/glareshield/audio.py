"""Process peak meters on all render endpoints, with debounce and cooldown."""
import asyncio
import threading
import time


class AudioDetector:
    def __init__(self,source):
        self.source=source
        self.above_since=None
        self.until=0
        self.next_event=0

    def sample(self,peak,now):
        if peak>=self.source.threshold:
            if self.above_since is None:
                self.above_since=now
            if now-self.above_since>=self.source.min_ms/1000 and now>=self.next_event:
                self.until=now+self.source.hold_s
                self.next_event=now+max(self.source.cooldown_s,self.source.hold_s)
        else:
            self.above_since=None
        return now<self.until


class AudioSource:
    def __init__(self,sources,update):
        self.sources={key:source for key,source in sources.items() if source.type=='audio_process'}
        self.update=update
        self.stopping=threading.Event()
        self.levels={}
        self.error=None

    async def run(self):
        loop=asyncio.get_running_loop()
        await asyncio.to_thread(self.measure,loop)

    def measure(self,loop):
        import comtypes
        import psutil
        from pycaw.constants import DEVICE_STATE,EDataFlow
        from pycaw.pycaw import AudioUtilities,AudioSession
        from pycaw.api.audiopolicy import IAudioSessionControl2
        from pycaw.api.endpointvolume import IAudioMeterInformation
        detectors={key:AudioDetector(source) for key,source in self.sources.items()}
        due={key:0 for key in self.sources}
        process_names={name.casefold() for source in self.sources.values() for name in source.process_names}
        meters=[]
        refresh=0
        comtypes.CoInitialize()
        try:
            while not self.stopping.is_set():
                now=time.monotonic()
                if now>=refresh:
                    meters=[]
                    try:
                        for device in AudioUtilities.GetAllDevices(EDataFlow.eRender.value,DEVICE_STATE.ACTIVE.value):
                            try:
                                sessions=device.AudioSessionManager.GetSessionEnumerator()
                                for index in range(sessions.GetCount()):
                                    control=sessions.GetSession(index).QueryInterface(IAudioSessionControl2)
                                    process=AudioSession(control).Process
                                    if process:
                                        name=process.name().casefold()
                                        if name in process_names:
                                            meters.append((name,control.QueryInterface(IAudioMeterInformation)))
                            except (OSError,comtypes.COMError,psutil.Error):
                                continue
                        self.error=None
                    except Exception as error:
                        self.error=type(error).__name__
                    refresh=now+1
                peaks={}
                for name,meter in meters:
                    try:
                        peaks[name]=max(peaks.get(name,0),float(meter.GetPeakValue()))
                    except (OSError,comtypes.COMError):
                        continue
                values={}
                levels={}
                for key,source in self.sources.items():
                    if now<due[key]:
                        continue
                    due[key]=now+source.poll_ms/1000
                    peak=max((peaks.get(name.casefold(),0) for name in source.process_names),default=0)
                    levels[key]=peak
                    values[key]=detectors[key].sample(peak,now)
                self.levels.update(levels)
                if values:
                    loop.call_soon_threadsafe(self.update,values)
                self.stopping.wait(min(source.poll_ms for source in self.sources.values())/1000)
        finally:
            comtypes.CoUninitialize()
            loop.call_soon_threadsafe(self.update,{key:False for key in self.sources})

    def stop(self):
        self.stopping.set()
