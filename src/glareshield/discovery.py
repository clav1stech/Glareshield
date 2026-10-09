"""Resolve stable controller identities through mDNS, including DHCP changes."""
import asyncio
import ipaddress
import json

SERVICES=['_hue._tcp.local.','_nanoleafapi._tcp.local.']


async def network(seconds=2,cache_path=None):
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser,AsyncServiceInfo,AsyncZeroconf
    found={}
    tasks=set()
    zc=AsyncZeroconf()
    async def resolve(service_type,name):
        info=AsyncServiceInfo(service_type,name)
        if await info.async_request(zc.zeroconf,2000):
            properties={key.decode():value.decode() if isinstance(value,bytes) else value for key,value in info.properties.items()}
            addresses=[address for address in info.parsed_addresses() if ipaddress.ip_address(address).version==4]
            identifier=properties.get('bridgeid') or properties.get('eui64') or properties.get('id')
            if identifier and addresses:
                found[identifier.casefold()]={'host':addresses[0],'port':info.port}
    def changed(zeroconf,service_type,name,state_change):
        if state_change in (ServiceStateChange.Added,ServiceStateChange.Updated):
            task=asyncio.create_task(resolve(service_type,name))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    browser=AsyncServiceBrowser(zc.zeroconf,SERVICES,handlers=[changed])
    try:
        await asyncio.sleep(seconds)
        if tasks:
            await asyncio.gather(*list(tasks),return_exceptions=True)
    finally:
        await browser.async_cancel()
        await zc.async_close()
    if cache_path is not None and cache_path.exists():
        try:
            cached=json.loads(cache_path.read_text(encoding='utf-8'))
            for service in cached.get('network',[]):
                if service['service'] not in SERVICES:
                    continue
                properties=service['properties']
                identifier=properties.get('bridgeid') or properties.get('eui64') or properties.get('id')
                addresses=[value for value in service['addresses'] if ipaddress.ip_address(value).version==4]
                if identifier and addresses:
                    found.setdefault(identifier.casefold(),{'host':addresses[0],'port':service['port']})
        except (OSError,ValueError,KeyError):
            pass
    return found
