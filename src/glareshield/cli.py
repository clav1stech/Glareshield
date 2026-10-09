import argparse
import asyncio
import tempfile
from pathlib import Path

from .config import load
from .drivers.mock import MockDriver
from .engine import Engine


async def demo(configuration_path):
    configuration = load(configuration_path)
    if any(device.driver != "mock" for device in configuration.devices.values()):
        raise ValueError("La démonstration nécessite exclusivement des appareils simulés.")
    driver = MockDriver(configuration.devices)
    with tempfile.TemporaryDirectory() as directory:
        engine = Engine(configuration,{"mock":driver},Path(directory)/"snapshots.json")
        engine.connected = True
        engine.values = {"dome":1,"warning":0,"caution":0,"contact":False}
        try:
            for label,values in (("Ambiance",{}),("Caution",{"caution":1}),
                                 ("Warning",{"warning":1}),
                                 ("Retour à Caution",{"warning":0}),
                                 ("Retour à l’ambiance courante",{"caution":0,"dome":2})):
                engine.values.update(values)
                await engine.step()
                print(label,":",engine.winners)
            configuration.active_scope = "extended"
            engine.values["warning"] = 1
            await engine.step()
            print("Portée étendue :",engine.winners)
        finally:
            await engine.shutdown()
        print("Restauration :", "réussie" if not engine.snapshots else "incomplète")


def main():
    parser = argparse.ArgumentParser(description="Glareshield")
    parser.add_argument("command",choices=["demo"])
    parser.add_argument("--config",type=Path,default=Path("examples/demo.yaml"))
    args = parser.parse_args()
    asyncio.run(demo(args.config))


if __name__ == "__main__":
    main()
