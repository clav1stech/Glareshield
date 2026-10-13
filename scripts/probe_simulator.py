"""Read configured simulator variables without writing simulator state."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sample(variables: list[str], simvars: list[tuple[str, str]], seconds: float, destination: str) -> None:
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
    # Standard SimVars are recorded as "A:NAME" to keep them apart from LVars.
    requests.update({'A:'+name: Request((name.encode('ascii'), unit.encode('ascii')), connection, _time=100)
                     for name, unit in simvars})
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


def read_list(path: Path, parser, kind: str):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        parser.error(f'Liste {kind} illisible : {path}')
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description='Sonde du simulateur en lecture seule (LVars et SimVars)')
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--variables-file', type=Path,
                        help='Liste JSON de noms de LVars (défaut : local/discovery/probe-variables.json)')
    parser.add_argument('--simvars-file', type=Path,
                        help='Liste JSON de SimVars, chacune ["NOM", "unité"] (défaut : local/discovery/probe-simvars.json)')
    args = parser.parse_args()
    variables, simvars = [], []
    lvar_path = args.variables_file or ROOT/'local/discovery/probe-variables.json'
    simvar_path = args.simvars_file or ROOT/'local/discovery/probe-simvars.json'
    if args.variables_file or lvar_path.exists():
        variables = read_list(lvar_path, parser, 'de LVars')
        if not isinstance(variables,list) or not all(isinstance(v,str) and v for v in variables):
            parser.error('Une liste de noms de LVars est requise.')
    if args.simvars_file or simvar_path.exists():
        raw = read_list(simvar_path, parser, 'de SimVars')
        if not isinstance(raw,list) or not all(isinstance(v,list) and len(v) == 2 and all(isinstance(p,str) and p for p in v)
                                              for v in raw):
            parser.error('Chaque SimVar doit être une paire ["NOM", "unité"].')
        simvars = [tuple(v) for v in raw]
    if not variables and not simvars:
        parser.error('Aucune variable à lire : fournir une liste de LVars ou de SimVars.')
    if not 1 <= args.seconds <= 300:
        parser.error('Durée requise entre 1 et 300 secondes.')
    output = ROOT/'local/discovery/simulator-observations.json'
    process = multiprocessing.Process(target=sample,args=(variables,simvars,args.seconds,str(output)))
    process.start()
    process.join(args.seconds+15)
    if process.is_alive():
        process.terminate()
        process.join(5)
        parser.exit(1,'Connexion ou lecture du simulateur : délai dépassé.\n')
    if process.exitcode:
        parser.exit(1,'Sonde indisponible : vérifier que l’avion est chargé dans MSFS.\n')
    print('Observations privées enregistrées dans local/discovery/simulator-observations.json')


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
