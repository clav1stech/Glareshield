from copy import deepcopy

from ..model import Device, LightState, SoundEffect


class MockDriver:
    def __init__(self, devices: dict[str,Device]):
        self.devices = devices
        self.states = {key: device.initial_state.model_dump(mode="json") for key,device in devices.items()}
        self.commands: list[dict] = []
        self.unreachable: set[str] = set()

    def check(self, identifier):
        if identifier in self.unreachable:
            raise ConnectionError("Appareil simulé injoignable.")

    async def discover(self):
        return list(self.devices.values())

    async def snapshot(self, identifier, device):
        self.check(identifier)
        return deepcopy(self.states[identifier])

    async def apply(self, identifier, device, state: LightState):
        self.check(identifier)
        self.states[identifier] = state.model_dump(mode="json")
        self.commands.append({"device":identifier,"operation":"apply","state":deepcopy(self.states[identifier])})

    async def restore(self, identifier, device, snapshot):
        self.check(identifier)
        self.states[identifier] = deepcopy(snapshot)
        self.commands.append({"device":identifier,"operation":"restore"})

    async def identify(self, identifier, device):
        self.check(identifier)
        self.commands.append({"device":identifier,"operation":"identify"})

    async def play(self, identifier, device, effect: SoundEffect):
        self.check(identifier)
        self.commands.append({"device":identifier,"operation":"sound","file":effect.file,"volume":effect.volume})
