#!/usr/bin/env python3
"""Runtime configuration for NutriParse.

Paths and request limits are module constants. Every runtime setting is parsed
once into :class:`Settings` by ``pydantic-settings``, so the server treats the
local environment file and the process environment the same way and fails at
startup, not mid-request, when a value is wrong.

``SettingsProvider`` keeps the mtime-based live reload used by the web app:
editing ``.env`` changes the next request without restarting the server.
"""

import math
import threading
from pathlib import Path
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    ValidationError,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

BASE_DIR = Path(__file__).resolve().parent.parent
HOST = "localhost"
PORT = 8100
ENV_FILE = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "llm.log"
IMAGE_LOG_FILE = LOG_DIR / "image_generation.log"

MAX_REQUEST_BYTES = 16 * 1024
MAX_TEXT_LENGTH = 500
MAX_MEAL_ITEMS = 15
RECIPE_COUNT = 3
MIN_RECIPE_STEPS = 4
MAX_RECIPE_STEPS = 6

DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "qwen3.5:4b"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
DEFAULT_IMAGE_API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
DEFAULT_IMAGE_WIDTH = 640
DEFAULT_IMAGE_HEIGHT = 480
DEFAULT_IMAGE_STEPS = 20
IMAGE_TIMEOUT = 240.0

# Timeouts used when LLM_TIMEOUT is absent or invalid. OpenRouter's values
# follow the original per-feature defaults; a cold local model gets longer.
DEFAULT_PARSE_TIMEOUT = 30.0
DEFAULT_COOK_TIMEOUT = 45.0
DEFAULT_LOCAL_TIMEOUT = 180.0

_PROVIDERS = {"openrouter", "local"}


class ConfigurationError(ValueError):
    """Settings could not be parsed; the message names the source file."""


class _NonEmptyEnvironmentSource(PydanticBaseSettingsSource):
    """Treat a blank process variable as unset so it cannot wipe a file value.

    Blank values inside the environment file stay meaningful (an empty
    ``LLM_REASONING_EFFORT`` means "send no reasoning_effort key").
    """

    def __init__(self, source: PydanticBaseSettingsSource):
        super().__init__(source.settings_cls)
        self._source = source

    def get_field_value(self, field, field_name):
        return self._source.get_field_value(field, field_name)

    def __call__(self):
        return {
            key: value
            for key, value in self._source().items()
            if not (isinstance(value, str) and not value.strip())
        }


class LLMConfig(BaseModel):
    """The active provider after defaults and ``LLM_TIMEOUT`` are applied."""

    provider: Literal["openrouter", "local"]
    base_url: str
    model: str
    api_key: str
    timeout: float
    label: str


class Settings(BaseSettings):
    """Every runtime setting, read from ``.env`` and the process environment.

    Process environment variables take priority over the local environment
    file, and the field names map to upper-case environment variables
    (``llm_provider`` -> ``LLM_PROVIDER``).
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    llm_provider: Literal["openrouter", "local"] = "openrouter"
    llm_base_url: str = DEFAULT_LOCAL_BASE_URL
    llm_model: str = DEFAULT_LOCAL_MODEL
    llm_api_key: str = ""
    # Invalid or non-positive values are dropped here, so resolving a provider
    # falls back to its documented default instead of failing a request.
    llm_timeout: float | None = None
    llm_reasoning_effort: str = "none"
    llm_json_mode: bool = True

    # Legacy OpenRouter key names stay accepted, in their original order.
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "OPENROUTER_API_KEY", "OPENROUTER_TOKEN", "OPEN_ROUTER_API_KEY"
        ),
    )
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL
    openrouter_base_url: str = DEFAULT_OPENROUTER_BASE_URL

    local_image_api_url: str = DEFAULT_IMAGE_API_URL
    local_image_generation_enabled: bool = True
    local_image_timeout: float = Field(default=IMAGE_TIMEOUT, gt=0)
    local_image_width: int = Field(default=DEFAULT_IMAGE_WIDTH, ge=64, le=2048)
    local_image_height: int = Field(default=DEFAULT_IMAGE_HEIGHT, ge=64, le=2048)
    local_image_steps: int = Field(default=DEFAULT_IMAGE_STEPS, ge=1, le=100)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            _NonEmptyEnvironmentSource(env_settings),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _provider(cls, value):
        provider = str(value or "").strip().lower()
        if not provider:
            return "openrouter"
        if provider not in _PROVIDERS:
            raise ValueError("LLM_PROVIDER must be 'openrouter' or 'local'")
        return provider

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def _local_base_url(cls, value):
        return str(value or "").strip().rstrip("/") or DEFAULT_LOCAL_BASE_URL

    @field_validator("openrouter_base_url", mode="before")
    @classmethod
    def _openrouter_base_url(cls, value):
        return (
            str(value or "").strip().rstrip("/") or DEFAULT_OPENROUTER_BASE_URL
        )

    @field_validator("llm_model", mode="before")
    @classmethod
    def _local_model(cls, value):
        return str(value or "").strip() or DEFAULT_LOCAL_MODEL

    @field_validator("openrouter_model", mode="before")
    @classmethod
    def _openrouter_model(cls, value):
        return str(value or "").strip() or DEFAULT_OPENROUTER_MODEL

    @field_validator("llm_api_key", "openrouter_api_key", mode="before")
    @classmethod
    def _api_key(cls, value):
        return str(value or "").strip()

    @field_validator("llm_timeout", mode="before")
    @classmethod
    def _timeout(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(timeout) or timeout <= 0:
            return None
        return timeout

    @field_validator("llm_reasoning_effort", mode="before")
    @classmethod
    def _reasoning_effort(cls, value):
        if value is None:
            return "none"
        # An explicit empty value is meaningful: send no reasoning_effort key.
        return str(value).strip()

    @field_validator("llm_json_mode", "local_image_generation_enabled", mode="before")
    @classmethod
    def _boolean(cls, value, info):
        if value is None or (isinstance(value, str) and not value.strip()):
            return True
        return value

    @field_validator(
        "local_image_width", "local_image_height", "local_image_steps", mode="before"
    )
    @classmethod
    def _image_number(cls, value, info):
        if value is None or (isinstance(value, str) and not value.strip()):
            return {
                "local_image_width": DEFAULT_IMAGE_WIDTH,
                "local_image_height": DEFAULT_IMAGE_HEIGHT,
                "local_image_steps": DEFAULT_IMAGE_STEPS,
            }[info.field_name]
        return value

    @field_validator("local_image_api_url", mode="before")
    @classmethod
    def _image_url(cls, value):
        # A blank URL means "not configured", which keeps the image route's
        # distinct "unavailable" message; an absent value uses the default.
        return str(value or "").strip()

    @property
    def image_generation_enabled(self) -> bool:
        """Whether Cook should ask for generated images at all."""
        return self.local_image_generation_enabled and bool(self.local_image_api_url)

    def llm(self, default_timeout: float) -> LLMConfig:
        """Return the active provider, with ``LLM_TIMEOUT`` overriding defaults.

        ``default_timeout`` is the caller's OpenRouter value; a local provider
        keeps its longer 180-second default unless ``LLM_TIMEOUT`` overrides it.
        """
        timeout = self.llm_timeout
        if timeout is None:
            timeout = (
                DEFAULT_LOCAL_TIMEOUT
                if self.llm_provider == "local"
                else float(default_timeout)
            )
        if self.llm_provider == "local":
            return LLMConfig(
                provider="local",
                base_url=self.llm_base_url,
                model=self.llm_model,
                api_key=self.llm_api_key,
                timeout=timeout,
                label="Local model",
            )
        return LLMConfig(
            provider="openrouter",
            base_url=self.openrouter_base_url,
            model=self.openrouter_model,
            api_key=self.openrouter_api_key,
            timeout=timeout,
            label="OpenRouter",
        )


class SettingsProvider:
    """Load settings from one file, reloading when that file changes.

    The previously loaded values are kept in memory, but an invalid edit
    makes :meth:`current` raise a :class:`ConfigurationError` naming the file
    until it is fixed. Startup goes through the same path, so a bad value is
    reported immediately rather than during an AI call.
    """

    def __init__(self, env_file: Path | str = ENV_FILE):
        self.env_file = Path(env_file)
        self._lock = threading.Lock()
        self._settings = self._load()
        self._mtime = self._file_mtime()

    def current(self) -> Settings:
        """Return settings, reloading the file first if its mtime changed."""
        if self._file_mtime() == self._mtime:
            return self._settings
        with self._lock:
            mtime = self._file_mtime()
            if mtime != self._mtime:
                self._settings = self._load()
                self._mtime = mtime
        return self._settings

    def reload(self) -> Settings:
        """Force a reload, regardless of the recorded mtime (used by tests)."""
        with self._lock:
            self._settings = self._load()
            self._mtime = self._file_mtime()
        return self._settings

    def _load(self) -> Settings:
        try:
            return Settings(_env_file=self.env_file)
        except ValidationError as error:
            raise ConfigurationError(
                f"Invalid settings in {self.env_file}:\n{error}"
            ) from error

    def _file_mtime(self):
        try:
            return self.env_file.stat().st_mtime_ns
        except OSError:
            return None
