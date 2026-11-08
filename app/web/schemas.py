"""Pydantic request and response models for the HTTP API.

These models are the contract behind ``/docs`` and ``/openapi.json``. Request
models are deliberately permissive: the store and the service layer still own
the domain rules and their user-facing messages ("Meal must be one of…"), so a
Pydantic validation failure only means the JSON shape itself was wrong.
"""

from pydantic import BaseModel, ConfigDict, Field


class ApiError(BaseModel):
    """The single error envelope every route returns."""

    error: str


class HealthResponse(BaseModel):
    status: str


class RuntimeConfigResponse(BaseModel):
    """Effective provider and per-feature timeouts the browser should wait for."""

    provider: str
    model: str
    parse_timeout_ms: int
    cook_timeout_ms: int
    image_timeout_ms: int


# --------------------------------------------------------------- requests


class EntryIn(BaseModel):
    """One journal row as a client sends it. The store assigns the id."""

    name: str = ""
    portion: str = ""
    calories: float = 0
    protein: float = 0
    carbs: float = 0
    fat: float = 0
    meal: str = "snack"
    date: str | None = None


class EntriesRequest(BaseModel):
    entries: list[EntryIn] = Field(default_factory=list)


class GoalRequest(BaseModel):
    calorie_goal: float | None = None


class ParseRequest(BaseModel):
    text: str = ""


class RecipeRequest(BaseModel):
    ingredients: str = ""
    use_soon: str = ""


class ImageRequest(BaseModel):
    title: str = ""
    description: str = ""


# -------------------------------------------------------------- responses


class EntryOut(BaseModel):
    """A stored row. Legacy rows may carry numeric ids or extra fields."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)

    id: str = ""
    name: str = ""
    portion: str = ""
    calories: float = 0
    protein: float = 0
    carbs: float = 0
    fat: float = 0
    meal: str = "snack"
    date: str = ""


class JournalDocument(BaseModel):
    calorie_goal: int
    entries: list[EntryOut] = Field(default_factory=list)
    updated_at: str | None = None


class ParsedItem(BaseModel):
    name: str
    portion: str = ""
    calories: float
    protein: float
    carbs: float
    fat: float


class MacroTotals(BaseModel):
    calories: float = 0
    protein: float = 0
    carbs: float = 0
    fat: float = 0


class CallMeta(BaseModel):
    provider: str = ""
    model: str = ""
    elapsed_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ParseResponse(BaseModel):
    items: list[ParsedItem]
    totals: MacroTotals
    meta: CallMeta


class RecipeNutrition(BaseModel):
    calories: float
    protein: float
    carbs: float
    fat: float


class RecipeOut(BaseModel):
    title: str
    description: str
    ingredients_used: list[str] = Field(default_factory=list)
    pantry_extras: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    servings: int
    nutrition: RecipeNutrition
    image: str | None = None
    image_pending: bool = False
    image_unavailable: bool = False


class RecipeResponse(BaseModel):
    recipes: list[RecipeOut]
    meta: CallMeta


class ImageResponse(BaseModel):
    image: str
