"""Journal CRUD routes. Every mutation returns the whole updated document."""

from fastapi import APIRouter, Depends, HTTPException, Request

from ...journal import store
from ..dependencies import json_body, require_same_origin, write_journal
from ..schemas import ApiError, EntriesRequest, GoalRequest, JournalDocument

router = APIRouter(prefix="/api/journal", tags=["journal"])

_BODY_ERRORS = {
    400: {"model": ApiError},
    413: {"model": ApiError},
    415: {"model": ApiError},
    503: {"model": ApiError},
}
_DOCUMENT = {
    "response_model": JournalDocument,
    "response_model_exclude_none": True,
    "responses": _BODY_ERRORS,
}


@router.get("", **_DOCUMENT)
def read_journal(request: Request):
    try:
        return store.load(request.app.state.store_path)
    except store.StoreError as error:
        raise HTTPException(500, str(error)) from error


@router.post("/entries", dependencies=[Depends(json_body)], **_DOCUMENT)
def add_journal_entries(request: Request, payload: EntriesRequest):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.add_entries(
            request.app.state.store_path,
            [entry.model_dump() for entry in payload.entries],
        ),
    )


@router.post("/goal", dependencies=[Depends(json_body)], **_DOCUMENT)
def set_journal_goal(request: Request, payload: GoalRequest):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.set_goal(request.app.state.store_path, payload.calorie_goal),
    )


@router.put("/entries/{entry_id}", dependencies=[Depends(json_body)], **_DOCUMENT)
def update_journal_entry(entry_id: str, request: Request, payload: EntriesRequest):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.update_entry(
            request.app.state.store_path,
            entry_id,
            [entry.model_dump() for entry in payload.entries],
        ),
        missing_is_404=True,
    )


@router.delete("/entries/{entry_id}", **_DOCUMENT)
def delete_journal_entry(entry_id: str, request: Request):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.delete_entry(request.app.state.store_path, entry_id),
        missing_is_404=True,
    )
