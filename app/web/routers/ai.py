"""Model-backed routes: meal parsing and recipes."""

from fastapi import APIRouter, Depends, HTTPException

from ...config import MAX_TEXT_LENGTH, Settings
from ...services.nutrition import parse_meal
from ...services.recipes import suggest_recipes
from ..dependencies import current_settings, json_body, run_ai_feature
from ..schemas import ApiError, ParseRequest, ParseResponse, RecipeRequest, RecipeResponse

router = APIRouter(prefix="/api", tags=["ai"])

_AI_ERRORS = {
    400: {"model": ApiError},
    413: {"model": ApiError},
    415: {"model": ApiError},
    502: {"model": ApiError},
}


@router.post(
    "/parse",
    response_model=ParseResponse,
    responses=_AI_ERRORS,
    dependencies=[Depends(json_body)],
)
def parse(
    payload: ParseRequest,
    settings: Settings = Depends(current_settings),
):
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "Describe at least one food")
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(400, "Meal description must be 500 characters or fewer")

    return run_ai_feature(
        "meal_parse", lambda: parse_meal(text, settings), settings
    )


@router.post(
    "/leftover-alchemist",
    response_model=RecipeResponse,
    responses=_AI_ERRORS,
    dependencies=[Depends(json_body)],
)
def leftover_alchemist(
    payload: RecipeRequest,
    settings: Settings = Depends(current_settings),
):
    ingredients = payload.ingredients.strip()
    use_soon = payload.use_soon.strip()
    if not ingredients:
        raise HTTPException(400, "List at least one ingredient")
    if len(ingredients) > MAX_TEXT_LENGTH or len(use_soon) > MAX_TEXT_LENGTH:
        raise HTTPException(400, "Ingredients and note must be 500 characters or fewer")

    return run_ai_feature(
        "leftover_alchemist",
        lambda: suggest_recipes(ingredients, use_soon, settings),
        settings,
    )
