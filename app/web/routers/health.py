"""Liveness endpoint used by local checks and deployment probes."""

from fastapi import APIRouter

from ..http import json_response

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return json_response({"status": "ok"})
