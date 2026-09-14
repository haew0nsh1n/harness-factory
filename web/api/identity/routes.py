from fastapi import APIRouter, Depends

from web.api.identity.dependencies import get_actor
from web.api.identity.models import Actor

router = APIRouter(prefix="/api", tags=["identity"])


@router.get("/whoami")
def whoami(actor: Actor = Depends(get_actor)) -> dict[str, object]:
    return {
        "ok": True,
        "actor": {
            "organization_id": actor.organization_id,
            "subject_id": actor.subject_id,
            "roles": sorted(actor.roles),
        },
    }
