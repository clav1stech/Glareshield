"""Read configured simulator variables without writing simulator state."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sample(variables: list[str], seconds: float, destination: str) -> None:
    from SimConnect import SimConnect, Request

    class ObservedSimConnect(SimConnect):
        def handle_id_event(self,event):
            super().handle_id_event(event)
            if event.uEventID == self.dll.EventID.EVENT_SIM_PAUSED:
                self.paused = bool(event.dwData)
            elif event.uEventID == self.dll.EventID.EVENT_SIM_START:
                self.running = bool(event.dwData)

    connection = ObservedSimConnect()
    for event,name in ((connection.dll.EventID.EVENT_SIM_PAUSED,b'Pause_EX1'),
                       (connection.dll.EventID.EVENT_SIM_START,b'Sim')):
        connection.dll.UnsubscribeFromSystemEvent(connection.hSimConnect,event)
        result = connection.dll.SubscribeToSystemEvent(connection.hSimConnect,event,name)
        if not connection.IsHR(result,0):
            connection.exit()
            raise ConnectionError('Abonnement aux événements du simulateur refusé.')
    requests = {name: Request((('L:'+name).encode('ascii'), b'Number'),
                              connection, _time=100) for name in variables}
    records = []
    previous = None
    try:
        end = time.monotonic()+seconds
        while time.monotonic() < end and connection.quit == 0:
            values = {name: request.get() for name, request in requests.items()}
            values['simulator_paused'] = connection.paused
            values['simulator_running'] = connection.running
            if values != previous:
                records.append({'elapsed_s': round(seconds-(end-time.monotonic()), 2),
                                'values': values})
                previous = values
                output = Path(destination)
                output.parent.mkdir(parents=True,exist_ok=True)
                temp = output.with_suffix('.tmp')
                temp.write_text(json.dumps({'connected': connection.ok, 'observations': records},
                                           indent=2),encoding='utf-8')
                for attempt in range(20):
                    try:
                        temp.replace(output)
                        break
                    except PermissionError:
                        if attempt == 19:
                            raise
                        time.sleep(.05)
            time.sleep(.1)
    finally:
        connection.exit()


def main() -> None:
    parser = argparse.ArgumentParser(description='Sonde Fenix en lecture seule')
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--variables-file', type=Path,
                        default=ROOT/'local/discovery/probe-variables.json')
    args = parser.parse_args()
    variables = json.loads(args.variables_file.read_text(encoding='utf-8'))
    if not isinstance(variables,list) or not variables or not all(isinstance(v,str) for v in variables):
        parser.error('Une liste non vide de noms de variables est requise.')
    if not 1 <= args.seconds <= 300:
        parser.error('Durée requise entre 1 et 300 secondes.')
    output = ROOT/'local/discovery/simulator-observations.json'
    process = multiprocessing.Process(target=sample,args=(variables,args.seconds,str(output)))
    process.start()
    process.join(args.seconds+15)
    if process.is_alive():
        process.terminate()
        process.join(5)
        parser.exit(1,'Connexion ou lecture du simulateur : délai dépassé.\n')
    if process.exitcode:
        parser.exit(1,'Sonde indisponible : vérifier que le Fenix est chargé dans MSFS.\n')
    print('Observations privées enregistrées dans local/discovery/simulator-observations.json')


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
