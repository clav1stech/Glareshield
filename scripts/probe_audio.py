"""Measure process audio on every active Windows output; never record sound."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    import comtypes
    import psutil
    from pycaw.constants import DEVICE_STATE, EDataFlow
    from pycaw.pycaw import AudioUtilities, AudioSession
    from pycaw.api.audiopolicy import IAudioSessionControl2
    from pycaw.api.endpointvolume import IAudioMeterInformation

    parser = argparse.ArgumentParser(description='Niveaux audio par processus sur toutes les sorties')
    parser.add_argument('--seconds',type=float,default=10)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error('Durée requise entre 1 et 300 secondes.')
    results = {}
    errors = []
    comtypes.CoInitialize()
    try:
        devices = AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
        end = time.monotonic()+args.seconds
        while time.monotonic() < end:
            for device in devices:
                try:
                    sessions = device.AudioSessionManager.GetSessionEnumerator()
                    for index in range(sessions.GetCount()):
                        control = sessions.GetSession(index).QueryInterface(IAudioSessionControl2)
                        session = AudioSession(control)
                        process = session.Process
                        if process is None:
                            continue
                        meter = control.QueryInterface(IAudioMeterInformation)
                        name = process.name()
                        key = (device.id, name)
                        item = results.setdefault(key, {'output_id':device.id,
                            'output_name':device.FriendlyName,'process':name,'peak':0.0})
                        item['peak'] = max(item['peak'],float(meter.GetPeakValue()))
                except (OSError, comtypes.COMError, psutil.Error) as error:
                    label = type(error).__name__
                    if label not in errors:
                        errors.append(label)
            time.sleep(.1)
    finally:
        comtypes.CoUninitialize()
    path = ROOT/'local/discovery/audio-sessions.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'sessions':list(results.values()),'errors':errors},
                               ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)
    print(f'Sessions mesurées : {len(results)} ; erreurs : {len(errors)}')
    print('Rapport privé : local/discovery/audio-sessions.json')


if __name__ == '__main__':
    main()
