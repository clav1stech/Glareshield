"""Isolate the blocking SimConnect DLL in a supervised, read-only process."""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import time


class TelemetryPoller:
    """Poll AI Bridge variables between lighting reads, on the worker thread itself.

    The SimConnect DLL is not called from a second thread: concurrent requests on the
    same handle crashed the worker on a real installation.
    """

    def __init__(self,request_factory,clock=time.time,per_cycle=1):
        self.request_factory=request_factory
        self.clock=clock
        self.per_cycle=per_cycle
        self.definitions={}
        self.requests={}
        self.due={}
        self.results={}
        self.errors={}

    def configure(self,definitions):
        self.definitions=dict(definitions)
        self.due={key:self.due.get(key,0) for key in self.definitions}

    def poll_once(self,limit=None):
        now=time.monotonic()
        pending=sorted((self.due.get(key,0),key) for key in self.definitions if self.due.get(key,0)<=now)
        for _,key in pending[:self.per_cycle if limit is None else limit]:
            definition=self.definitions[key]
            request=self.requests.get(key)
            if request is None or request.definition!=(definition['name'],definition['unit']):
                request=self.request_factory(definition['name'],definition['unit'])
                self.requests[key]=request
            value=request.get()
            self.due[key]=time.monotonic()+definition['interval_ms']/1000
            if value is None:
                self.errors[key]='Aucune donnée reçue'
            else:
                if isinstance(value,bytes):
                    value=value.decode('utf-8','replace').rstrip('\0')
                self.results[key]=(value,self.clock())
                self.errors.pop(key,None)

    def drain(self):
        results,self.results=self.results,{}
        return results,dict(self.errors)


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
        lighting={'L:'+source['name'].removeprefix('L:'):key for key,source in sources.items() if source['type']=='lvar'}
        shared={}
        def request_factory(name,unit):
            request=Request((name.encode('ascii'),unit.encode('ascii')),connection,_time=0)
            request.definition=(name,unit)
            return request
        poller=TelemetryPoller(request_factory)
        while not stop.is_set() and not connection.quit:
            values={key:request.get() for key,request in requests.items()}
            for key,source in sources.items():
                if source['type']=='simulator_state':
                    values[key]=connection.paused if source['name']=='paused' else connection.running
            message={'connected':bool(connection.ok and connection.running),
                'paused':bool(connection.paused),'values':values}
            while pipe.poll():
                command=pipe.recv()
                if isinstance(command,dict) and 'telemetry' in command:
                    definitions=command['telemetry']
                    # Reuse lighting reads of the same LVar instead of a second request.
                    shared={key:lighting[d['name']] for key,d in definitions.items()
                            if d['origin']=='lvar' and d['name'] in lighting}
                    poller.configure({key:d for key,d in definitions.items() if key not in shared})
            if poller.definitions or shared:
                # Lighting values above are read first; telemetry adds at most one read per cycle.
                poller.poll_once()
                telemetry,errors=poller.drain()
                now=time.time()
                for key,source in shared.items():
                    if values.get(source) is not None:
                        telemetry[key]=(values[source],now)
                if telemetry:
                    message['telemetry']=telemetry
                if errors:
                    message['telemetry_errors']=errors
            pipe.send(message)
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
    def __init__(self,sources,update,*,worker_target=worker,heartbeat_s=15,telemetry=None):
        self.sources={key:value.model_dump(mode='json') for key,value in sources.items()
            if value.type in ('lvar','simulator_state')}
        self.telemetry=dict(telemetry or {})
        self.commands=None
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
            parent,child=context.Pipe()
            stop=context.Event()
            process=context.Process(target=self.worker_target,args=(self.sources,child,stop),daemon=True)
            self.process=process
            process.start()
            child.close()
            self.commands=parent
            if self.telemetry:
                parent.send({'telemetry':self.telemetry})
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
                self.commands=None
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

    def set_telemetry(self,definitions):
        """Change AI Bridge requests without reconnecting or touching lighting sources."""
        self.telemetry=dict(definitions)
        if self.commands is not None:
            try:
                self.commands.send({'telemetry':self.telemetry})
            except (OSError,EOFError,ValueError):
                pass

    def stop(self):
        self.stopping=True
