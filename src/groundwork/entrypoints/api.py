"""HTTP entrypoint.

`POST /harmonize` runs the harmonization flow of the pack in `GROUNDWORK_PACK`. There is
no authentication yet: the service must not be exposed beyond localhost (docs/security.md).
Errors groundwork raises on purpose come back with their message and a status that names
who failed: 404 an unknown contact, 502 the agent or the model, 500 the pack or anything
else; a draft that is not a valid request is a 422.
"""

import functools
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from groundwork.core.domain.errors import (
    AgentError,
    GroundworkError,
    ModelError,
    NotFoundError,
    PackError,
)
from groundwork.core.domain.harmonize import Decision, HarmonizedEmail, HarmonizeRequest
from groundwork.core.services.harmonize import HarmonizeFlow, harmonize
from groundwork.entrypoints.wiring import build_flow

PACK_ENV = "GROUNDWORK_PACK"
DEFAULT_PACK = "acme"
PACKS_DIR = Path("client_packs")
DOMAINS_DIR = Path("domains")
TRACES_DIR = Path("traces")
VAR_DIR = Path("var")

app = FastAPI(title="groundwork")


class HarmonizeResponse(BaseModel):
    """What a run returns: the email, the decision and the name of its trace."""

    model_config = ConfigDict(frozen=True)

    email: HarmonizedEmail
    decision: Decision
    trace_id: str


@functools.cache
def default_flow() -> HarmonizeFlow:
    """The flow of the served pack, built once. A bad pack is a `PackError` at first use."""
    pack = os.environ.get(PACK_ENV, DEFAULT_PACK)
    return build_flow(PACKS_DIR / pack, DOMAINS_DIR, TRACES_DIR, VAR_DIR)


def get_flow() -> HarmonizeFlow:
    try:
        return default_flow()
    except GroundworkError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/harmonize")
def harmonize_endpoint(
    request: HarmonizeRequest, flow: Annotated[HarmonizeFlow, Depends(get_flow)]
) -> HarmonizeResponse:
    """Rewrite a draft for a contact and route it: send, queue for approval, or block."""
    try:
        outcome = harmonize(flow, request)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AgentError, ModelError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (PackError, GroundworkError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return HarmonizeResponse(
        email=outcome.email, decision=outcome.decision, trace_id=outcome.trace_id
    )
