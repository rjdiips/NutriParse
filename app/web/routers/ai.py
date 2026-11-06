"""Model-backed routes: meal parsing and recipes."""

from fastapi import APIRouter, HTTPException, Request

from ...config import MAX_TEXT_LENGTH
from ...services.nutrition import parse_meal
from ...services.recipes import suggest_recipes
from ..dependencies import JSONBody, current_env, run_ai_feature
from ..http import json_response

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/parse")
def parse(request: Request, payload: JSONBody):
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "Describe at least one food")
    text = text.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(400, "Meal description must be 500 characters or fewer")

    env = current_env(request)
    return json_response(run_ai_feature("meal_parse", lambda: parse_meal(text, env), env))


@router.post("/leftover-alchemist")
def leftover_alchemist(request: Request, payload: JSONBody):
    ingredients = payload.get("ingredients")
    use_soon = payload.get("use_soon", "")
    if not isinstance(ingredients, str) or not ingredients.strip():
        raise HTTPException(400, "List at least one ingredient")
    if not isinstance(use_soon, str):
        raise HTTPException(400, "Use-soon note must be text")
    ingredients, use_soon = ingredients.strip(), use_soon.strip()
    if len(ingredients) > MAX_TEXT_LENGTH or len(use_soon) > MAX_TEXT_LENGTH:
        raise HTTPException(400, "Ingredients and note must be 500 characters or fewer")

    env = current_env(request)
    return json_response(
        run_ai_feature(
            "leftover_alchemist", lambda: suggest_recipes(ingredients, use_soon, env), env
        )
    )
