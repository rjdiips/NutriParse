"""Journal CRUD routes. Every mutation returns the whole updated document."""

from fastapi import APIRouter, HTTPException, Request

from ...journal import store
from ..dependencies import JSONBody, require_same_origin, write_journal
from ..http import json_response

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("")
def read_journal(request: Request):
    try:
        document = store.load(request.app.state.store_path)
    except store.StoreError as error:
        raise HTTPException(500, str(error)) from error
    return json_response(document)


@router.post("/entries")
def add_journal_entries(request: Request, payload: JSONBody):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.add_entries(request.app.state.store_path, payload.get("entries")),
    )


@router.post("/goal")
def set_journal_goal(request: Request, payload: JSONBody):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.set_goal(request.app.state.store_path, payload.get("calorie_goal")),
    )


@router.put("/entries/{entry_id}")
def update_journal_entry(entry_id: str, request: Request, payload: JSONBody):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.update_entry(
            request.app.state.store_path, entry_id, payload.get("entries")
        ),
        missing_is_404=True,
    )


@router.delete("/entries/{entry_id}")
def delete_journal_entry(entry_id: str, request: Request):
    require_same_origin(request)
    return write_journal(
        request,
        lambda: store.delete_entry(request.app.state.store_path, entry_id),
        missing_is_404=True,
    )
