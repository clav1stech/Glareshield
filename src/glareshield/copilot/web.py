"""Local session routes, under the existing AI Bridge token protection."""
from fastapi import APIRouter, HTTPException
from pydantic import StrictBool

from ..model import StrictModel
from .contract import PhaseId
from .session import DeclarationInput


class SessionAction(StrictModel):
    session_id: str | None
    universe: str


class StepAction(SessionAction):
    checked: StrictBool


class PhaseAction(SessionAction):
    phase: PhaseId | None


class DeclareAction(SessionAction):
    declaration: DeclarationInput


def create_session_router(bridge):
    router = APIRouter(prefix='/api/ai/session')

    def execute(payload, operation):
        service = bridge().sessions
        try:
            service.synchronize()
            document = service.documents[service.universe]
            current_id = document.sessions[-1].id if document.sessions else None
            if payload.universe != service.universe or payload.session_id != current_id:
                raise HTTPException(409, 'Le suivi a changé : actualiser avant de réessayer.')
            return operation(service)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        except OSError:
            raise HTTPException(503, 'Écriture du suivi impossible ; dernier état conservé.') from None

    @router.get('')
    async def view():
        return bridge().sessions.view()

    @router.post('/{operation}')
    async def lifecycle(operation: str, payload: SessionAction):
        if operation not in ('start', 'resume', 'end', 'reset'):
            raise HTTPException(404, 'Action inconnue.')
        return execute(payload, lambda service: getattr(service, operation)())

    @router.put('/steps/{step_id}')
    async def step(step_id: str, payload: StepAction):
        return execute(payload, lambda service: service.set_step(step_id, payload.checked))

    @router.put('/phase')
    async def phase(payload: PhaseAction):
        return execute(payload, lambda service: service.force_phase(payload.phase))

    @router.put('/declarations')
    async def declare(payload: DeclareAction):
        return execute(payload, lambda service: service.declare(payload.declaration))

    @router.post('/declarations/{declaration_id}/revoke')
    async def revoke(declaration_id: str, payload: SessionAction):
        return execute(payload, lambda service: service.revoke(declaration_id))

    @router.post('/reminders/{reminder_id}/acknowledge')
    async def acknowledge(reminder_id: str, payload: SessionAction):
        return execute(payload, lambda service: service.acknowledge_reminder(reminder_id))

    return router
