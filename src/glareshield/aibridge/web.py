"""Local HTTP routes of AI Bridge; every route requires the session token."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..model import StrictModel
from .config import AIBridgeSettings
from .scenario import PHASES
from .simbrief import OFPError

PHASE_NAMES = tuple(name for name, _, _ in PHASES)

Level = Literal['essential', 'detailed']


class ExportRequest(StrictModel):
    level: Level = 'essential'


class ScenarioRequest(StrictModel):
    active: bool
    phase: Literal[PHASE_NAMES] | None = None


def create_router(bridge, changed=None) -> APIRouter:
    router = APIRouter(prefix='/api/ai')

    @router.get('/status')
    async def status():
        return bridge().status()

    @router.get('/context')
    async def context(level: Level = 'essential'):
        return bridge().snapshot(level)

    @router.get('/chat')
    async def chat(level: Level = 'essential'):
        text = bridge().chat(level)
        return {'text': text, 'chars': len(text)}

    @router.get('/variables')
    async def variables():
        return bridge().available_variables()

    @router.get('/plan')
    async def plan():
        return bridge().flight_plan()

    @router.get('/settings')
    async def settings():
        return bridge().settings.model_dump(mode='json')

    @router.put('/settings')
    async def save_settings(payload: dict):
        try:
            checked = AIBridgeSettings.model_validate(payload)
        except (ValidationError, ValueError) as error:
            fields = ', '.join('.'.join(str(part) for part in item['loc']) for item in error.errors()) \
                if isinstance(error, ValidationError) else ''
            raise HTTPException(400, 'Réglages refusés'+(' : '+fields if fields else '.')) from None
        bridge().save(checked)
        if changed:
            await changed()
        return {'ok': True}

    @router.post('/simbrief/refresh')
    async def refresh():
        try:
            await bridge().refresh_plan()
        except OFPError as error:
            raise HTTPException(502, str(error)) from None
        return bridge().flight_plan()

    @router.post('/simbrief/demo')
    async def demo_plan():
        bridge().load_demo_plan()
        return bridge().flight_plan()

    @router.post('/simbrief/clear')
    async def clear_plan():
        bridge().plan.clear()
        return {'ok': True}

    @router.post('/scenario')
    async def scenario(payload: ScenarioRequest):
        bridge().set_scenario(payload.active, payload.phase)
        return {'ok': True}

    @router.post('/export')
    async def export(payload: ExportRequest):
        path = bridge().export(payload.level)
        return {'ok': True, 'path': path.relative_to(bridge().root).as_posix()}

    return router
