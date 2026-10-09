"""Isolate the blocking SimConnect DLL in a supervised, read-only process."""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import time


def worker(sources,pipe,stop):
    connection=None
    try:
        from SimConnect import SimConnect,Request
        class ObservedSimConnect(SimConnect):
            def handle_id_event(self,event):
                super().handle_id_event(event)
                if event.uEventID==self.dll.EventID.EVENT_SIM_PAUSED:
                    self.paused=bool(event.dwData)
                elif event.uEventID==self.dll.EventID.EVENT_SIM_START:
                    self.running=bool(event.dwData)
        connection=ObservedSimConnect()
        for event,name in ((connection.dll.EventID.EVENT_SIM_PAUSED,b'Pause_EX1'),
                           (connection.dll.EventID.EVENT_SIM_START,b'Sim')):
            connection.dll.UnsubscribeFromSystemEvent(connection.hSimConnect,event)
            if not connection.IsHR(connection.dll.SubscribeToSystemEvent(connection.hSimConnect,event,name),0):
                raise ConnectionError()
        requests={key:Request((('L:'+source['name'].removeprefix('L:')).encode('ascii'),b'Number'),
            connection,_time=source['poll_ms']) for key,source in sources.items() if source['type']=='lvar'}
        while not stop.is_set() and not connection.quit:
            values={key:request.get() for key,request in requests.items()}
            for key,source in sources.items():
                if source['type']=='simulator_state':
                    values[key]=connection.paused if source['name']=='paused' else connection.running
            pipe.send({'connected':bool(connection.ok and connection.running),
                'paused':bool(connection.paused),'values':values})
            stop.wait(.05)
    except Exception as error:
        try:
            pipe.send({'error':type(error).__name__})
        except (OSError,EOFError):
            pass
    finally:
        if connection:
            connection.exit()
        pipe.close()


class SimulatorSource:
    def __init__(self,sources,update,*,worker_target=worker,heartbeat_s=15):
        self.sources={key:value.model_dump(mode='json') for key,value in sources.items()
            if value.type in ('lvar','simulator_state')}
        if any(not value['name'] for value in self.sources.values()):
            raise ValueError('Nom de variable requis pour les sources simulateur.')
        self.update=update
        self.worker_target=worker_target
        self.heartbeat_s=heartbeat_s
        self.process=None
        self.stopping=False
        self.error=None

    async def run(self):
        delay=1
        context=mp.get_context('spawn')
        while not self.stopping:
            parent,child=context.Pipe(duplex=False)
            stop=context.Event()
            process=context.Process(target=self.worker_target,args=(self.sources,child,stop),daemon=True)
            self.process=process
            process.start()
            child.close()
            last=time.monotonic()
            try:
                while not self.stopping and process.is_alive():
                    while parent.poll():
                        message=parent.recv()
                        last=time.monotonic()
                        if 'error' in message:
                            self.error=message['error']
                        else:
                            self.error=None
                            self.update(message)
                            delay=1
                    if time.monotonic()-last>self.heartbeat_s:
                        self.error='Délai de connexion dépassé'
                        break
                    await asyncio.sleep(.05)
            except (EOFError,OSError):
                self.error='Connexion interrompue'
            finally:
                stop.set()
                await asyncio.to_thread(process.join,1)
                if process.is_alive():
                    process.terminate()
                    await asyncio.to_thread(process.join,2)
                parent.close()
                process.close()
                self.process=None
                self.update({'connected':False,'paused':False,'values':{key:None for key in self.sources}})
            if not self.stopping:
                for _ in range(delay*10):
                    if self.stopping:
                        break
                    await asyncio.sleep(.1)
                delay=min(30,delay*2)

    def stop(self):
        self.stopping=True
