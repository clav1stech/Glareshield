"""Read-only local discovery. Installation data is saved outside Git."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

SERVICES = ("_hue._tcp.local.", "_nanoleafapi._tcp.local.",
            "_nanoleafms._tcp.local.", "_airplay._tcp.local.",
            "_raop._tcp.local.", "_matter._tcp.local.")
ROOT = Path(__file__).resolve().parents[1]


async def network(seconds: float) -> list[dict]:
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    found: dict[tuple[str, str], dict] = {}
    tasks: set[asyncio.Task] = set()
    zc = AsyncZeroconf()

    async def resolve(service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        if await info.async_request(zc.zeroconf, 3000):
            found[(service_type, name)] = {
                "service": service_type, "name": name, "server": info.server,
                "addresses": info.parsed_scoped_addresses(), "port": info.port,
                "properties": {k.decode(errors="replace"): v.decode(errors="replace")
                               if isinstance(v, bytes) else v
                               for k, v in info.properties.items()},
            }

    def changed(zeroconf, service_type, name, state_change):
        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            task = asyncio.create_task(resolve(service_type, name))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    browser = AsyncServiceBrowser(zc.zeroconf, list(SERVICES), handlers=[changed])
    try:
        await asyncio.sleep(seconds)
        if tasks:
            await asyncio.gather(*list(tasks), return_exceptions=True)
    finally:
        await browser.async_cancel()
        await zc.async_close()
    return sorted(found.values(), key=lambda item: (item["service"], item["name"]))


def audio() -> dict:
    if sys.platform != "win32":
        return {"available": False, "reason": "Windows requis"}
    import comtypes
    from pycaw.constants import DEVICE_STATE, EDataFlow
    from pycaw.pycaw import AudioUtilities

    comtypes.CoInitialize()
    try:
        devices = AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
        return {"available": True, "devices": [
            {"id": device.id, "name": device.FriendlyName} for device in devices
        ]}
    finally:
        comtypes.CoUninitialize()


async def airplay(seconds: float) -> list[dict]:
    import pyatv

    devices = await pyatv.scan(asyncio.get_running_loop(), timeout=int(seconds))
    return [{"name": device.name, "address": str(device.address),
             "identifier": device.identifier,
             "services": [{"protocol": service.protocol.name,
                           "identifier": service.identifier, "port": service.port,
                           "pairing": service.pairing.name}
                          for service in device.services]}
            for device in devices]


async def collect(seconds: float) -> dict:
    import psutil

    result = {"date": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "dependencies": {},
              "processes": [], "errors": {}}
    for package in ("fastapi", "uvicorn", "httpx", "pyyaml", "pydantic", "pyatv",
                    "pycaw", "psutil", "SimConnect", "pystray", "pillow", "zeroconf"):
        try:
            result["dependencies"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["errors"][package] = "Dépendance absente"
    for process in psutil.process_iter(["name"]):
        name = process.info["name"] or ""
        if any(term in name.lower() for term in ("altitude", "flightsimulator", "fenix", "huesync")):
            result["processes"].append(name)
    for key, outcome in zip(("network", "airplay", "audio"), await asyncio.gather(
        network(seconds), airplay(seconds), asyncio.to_thread(audio), return_exceptions=True
    )):
        if isinstance(outcome, BaseException):
            result["errors"][key] = type(outcome).__name__
        else:
            result[key] = outcome
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Découverte locale Glareshield")
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error("La durée doit être comprise entre 1 et 60 secondes.")
    result = asyncio.run(collect(args.seconds))
    destination = ROOT / "local" / "discovery" / "inventory.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)
    print("Rapport privé enregistré dans local/discovery/inventory.json")
    print(f"Services réseau : {len(result.get('network', []))}")
    print(f"Cibles AirPlay : {len(result.get('airplay', []))}")
    print(f"Sorties audio : {len(result.get('audio', {}).get('devices', []))}")
    print(f"Processus pertinents actifs : {len(result['processes'])}")
    for key, error in result["errors"].items():
        print(f"Vérification incomplète : {key} ({error})")


if __name__ == "__main__":
    main()
