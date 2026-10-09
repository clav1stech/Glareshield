import asyncio


class RoutedDriver:
    def __init__(self,controllers):
        self.controllers=controllers

    @property
    def invalidated(self):
        result=set()
        for driver in self.controllers.values():
            values=getattr(driver,'invalidated',set())
            result.update(values)
            values.clear()
        return result

    def driver(self,device):
        return self.controllers[device.controller]

    async def snapshot(self,identifier,device):
        return await self.driver(device).snapshot(identifier,device)

    async def apply(self,identifier,device,state):
        return await self.driver(device).apply(identifier,device,state)

    async def restore(self,identifier,device,state):
        return await self.driver(device).restore(identifier,device,state)

    async def identify(self,identifier,device):
        return await self.driver(device).identify(identifier,device)

    async def play(self,identifier,device,effect):
        return await self.driver(device).play(identifier,device,effect)

    async def apply_batch(self,items):
        groups={}
        for key,(device,state) in items.items():
            groups.setdefault(device.controller,{})[key]=(device,state)
        failures={}
        for controller,group in groups.items():
            driver=self.controllers[controller]
            if hasattr(driver,'apply_batch'):
                failures.update(await driver.apply_batch(group))
            else:
                results=await asyncio.gather(*(driver.apply(key,device,state) for key,(device,state) in group.items()),return_exceptions=True)
                failures.update({key:type(result).__name__ for key,result in zip(group,results) if isinstance(result,BaseException)})
        return failures

    async def close(self):
        await asyncio.gather(*(driver.close() for driver in self.controllers.values()),return_exceptions=True)
