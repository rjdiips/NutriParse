#!/usr/bin/env python3
"""Typed settings: defaults, environment precedence, and live reload."""

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from pydantic import AliasChoices, ValidationError

    from app.config import (
        DEFAULT_COOK_TIMEOUT,
        DEFAULT_IMAGE_API_URL,
        DEFAULT_IMAGE_HEIGHT,
        DEFAULT_IMAGE_STEPS,
        DEFAULT_IMAGE_WIDTH,
        DEFAULT_LOCAL_BASE_URL,
        DEFAULT_LOCAL_MODEL,
        DEFAULT_LOCAL_TIMEOUT,
        DEFAULT_OPENROUTER_BASE_URL,
        DEFAULT_OPENROUTER_MODEL,
        DEFAULT_PARSE_TIMEOUT,
        ConfigurationError,
        Settings,
        SettingsProvider,
    )
except Exception as error:  # pragma: no cover - only without dependencies
    Settings = None
    SKIP_REASON = f"Settings dependencies are unavailable: {error}"


def settings_env_names():
    """Every environment variable name the Settings model reads.

    Derived from the model itself, so the tests do not keep a second allowlist
    that can drift from the fields.
    """
    names = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        if isinstance(field.validation_alias, AliasChoices):
            names.update(str(choice) for choice in field.validation_alias.choices)
    return names


@contextmanager
def isolated_environment(**overrides):
    """Patch only the variables Settings reads, then restore them."""
    names = settings_env_names()
    saved = {name: os.environ[name] for name in names if name in os.environ}
    for name in names:
        os.environ.pop(name, None)
    os.environ.update(overrides)
    try:
        yield
    finally:
        for name in names:
            os.environ.pop(name, None)
        os.environ.update(saved)


def write_env(path, **values):
    lines = []
    for key, value in values.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        lines.append(f"{key.upper()}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@unittest.skipUnless(Settings is not None, globals().get("SKIP_REASON", ""))
class TestSettingsDefaults(unittest.TestCase):
    def test_empty_settings_use_the_documented_defaults(self):
        with isolated_environment():
            settings = Settings(_env_file=None)
        self.assertEqual(settings.llm_provider, "openrouter")
        self.assertEqual(settings.llm_base_url, DEFAULT_LOCAL_BASE_URL)
        self.assertEqual(settings.llm_model, DEFAULT_LOCAL_MODEL)
        self.assertEqual(settings.openrouter_base_url, DEFAULT_OPENROUTER_BASE_URL)
        self.assertEqual(settings.openrouter_model, DEFAULT_OPENROUTER_MODEL)
        self.assertEqual(settings.llm_reasoning_effort, "none")
        self.assertTrue(settings.llm_json_mode)
        self.assertEqual(settings.local_image_api_url, DEFAULT_IMAGE_API_URL)
        self.assertTrue(settings.local_image_generation_enabled)
        self.assertEqual(settings.local_image_width, DEFAULT_IMAGE_WIDTH)
        self.assertEqual(settings.local_image_height, DEFAULT_IMAGE_HEIGHT)
        self.assertEqual(settings.local_image_steps, DEFAULT_IMAGE_STEPS)

    def test_blank_file_values_fall_back_but_empty_reasoning_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment():
            path = Path(tmp) / ".env"
            path.write_text(
                "LLM_PROVIDER=\n"
                "LLM_BASE_URL=\n"
                "LLM_MODEL=\n"
                "LLM_TIMEOUT=\n"
                "LLM_REASONING_EFFORT=\n"
                "LLM_JSON_MODE=\n"
                "OPENROUTER_MODEL=\n"
                "OPENROUTER_BASE_URL=\n"
                "LOCAL_IMAGE_GENERATION_ENABLED=\n"
                "LOCAL_IMAGE_WIDTH=\n"
                "LOCAL_IMAGE_HEIGHT=\n"
                "LOCAL_IMAGE_STEPS=\n",
                encoding="utf-8",
            )
            settings = Settings(_env_file=path)
        self.assertEqual(settings.llm_provider, "openrouter")
        self.assertEqual(settings.llm_base_url, DEFAULT_LOCAL_BASE_URL)
        self.assertEqual(settings.llm_model, DEFAULT_LOCAL_MODEL)
        self.assertIsNone(settings.llm_timeout)
        # An explicitly empty effort means "send no reasoning_effort key".
        self.assertEqual(settings.llm_reasoning_effort, "")
        self.assertTrue(settings.llm_json_mode)
        self.assertEqual(settings.openrouter_model, DEFAULT_OPENROUTER_MODEL)
        self.assertEqual(settings.openrouter_base_url, DEFAULT_OPENROUTER_BASE_URL)
        self.assertTrue(settings.local_image_generation_enabled)
        self.assertEqual(settings.local_image_api_url, DEFAULT_IMAGE_API_URL)
        self.assertEqual(settings.local_image_width, DEFAULT_IMAGE_WIDTH)
        self.assertEqual(settings.local_image_height, DEFAULT_IMAGE_HEIGHT)
        self.assertEqual(settings.local_image_steps, DEFAULT_IMAGE_STEPS)

    def test_image_url_blank_means_not_configured(self):
        with isolated_environment():
            settings = Settings(_env_file=None, local_image_api_url="   ")
        self.assertEqual(settings.local_image_api_url, "")
        self.assertFalse(settings.image_generation_enabled)


@unittest.skipUnless(Settings is not None, globals().get("SKIP_REASON", ""))
class TestSettingsPrecedence(unittest.TestCase):
    def test_process_environment_overrides_the_file_for_every_field(self):
        file_values = {
            "llm_provider": "local",
            "llm_base_url": "http://file-local:1/v1",
            "llm_model": "file-local-model",
            "llm_api_key": "file-local-key",
            "llm_timeout": "11",
            "llm_reasoning_effort": "file-effort",
            "llm_json_mode": False,
            "openrouter_api_key": "file-openrouter-key",
            "openrouter_model": "file-openrouter-model",
            "openrouter_base_url": "http://file-openrouter:2/v1",
            "local_image_api_url": "http://file-image:3/txt2img",
            "local_image_generation_enabled": False,
            "local_image_width": 111,
            "local_image_height": 222,
            "local_image_steps": 7,
        }
        env_values = {
            "LLM_PROVIDER": "openrouter",
            "LLM_BASE_URL": "http://env-local:1/v1",
            "LLM_MODEL": "env-local-model",
            "LLM_API_KEY": "env-local-key",
            "LLM_TIMEOUT": "22",
            "LLM_REASONING_EFFORT": "env-effort",
            "LLM_JSON_MODE": "true",
            "OPENROUTER_API_KEY": "env-openrouter-key",
            "OPENROUTER_MODEL": "env-openrouter-model",
            "OPENROUTER_BASE_URL": "http://env-openrouter:2/v1",
            "LOCAL_IMAGE_API_URL": "http://env-image:3/txt2img",
            "LOCAL_IMAGE_GENERATION_ENABLED": "true",
            "LOCAL_IMAGE_WIDTH": "333",
            "LOCAL_IMAGE_HEIGHT": "444",
            "LOCAL_IMAGE_STEPS": "9",
        }
        with tempfile.TemporaryDirectory() as tmp, isolated_environment(**env_values):
            path = Path(tmp) / ".env"
            write_env(path, **file_values)
            settings = Settings(_env_file=path)

        self.assertEqual(settings.llm_provider, "openrouter")
        self.assertEqual(settings.llm_base_url, "http://env-local:1/v1")
        self.assertEqual(settings.llm_model, "env-local-model")
        self.assertEqual(settings.llm_api_key, "env-local-key")
        self.assertEqual(settings.llm_timeout, 22.0)
        self.assertEqual(settings.llm_reasoning_effort, "env-effort")
        self.assertTrue(settings.llm_json_mode)
        self.assertEqual(settings.openrouter_api_key, "env-openrouter-key")
        self.assertEqual(settings.openrouter_model, "env-openrouter-model")
        self.assertEqual(settings.openrouter_base_url, "http://env-openrouter:2/v1")
        self.assertEqual(settings.local_image_api_url, "http://env-image:3/txt2img")
        self.assertTrue(settings.local_image_generation_enabled)
        self.assertEqual(settings.local_image_width, 333)
        self.assertEqual(settings.local_image_height, 444)
        self.assertEqual(settings.local_image_steps, 9)

    def test_the_file_is_used_when_the_process_environment_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment():
            path = Path(tmp) / ".env"
            write_env(
                path,
                llm_provider="local",
                llm_model="file-model",
                local_image_generation_enabled=False,
                local_image_width=800,
            )
            settings = Settings(_env_file=path)
        self.assertEqual(settings.llm_provider, "local")
        self.assertEqual(settings.llm_model, "file-model")
        self.assertFalse(settings.image_generation_enabled)
        self.assertEqual(settings.local_image_width, 800)

    def test_legacy_openrouter_key_aliases_are_accepted(self):
        for alias in ("OPENROUTER_TOKEN", "OPEN_ROUTER_API_KEY"):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory() as tmp:
                with isolated_environment():
                    path = Path(tmp) / ".env"
                    path.write_text(f"{alias}=file-key\n", encoding="utf-8")
                    settings = Settings(_env_file=path)
                self.assertEqual(settings.openrouter_api_key, "file-key")

    def test_process_legacy_alias_overrides_the_file_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with isolated_environment(OPENROUTER_TOKEN="env-token"):
                path = Path(tmp) / ".env"
                write_env(path, openrouter_api_key="file-key")
                settings = Settings(_env_file=path)
            self.assertEqual(settings.openrouter_api_key, "env-token")

    def test_openrouter_api_key_wins_over_the_legacy_alias(self):
        with isolated_environment(
            OPENROUTER_API_KEY="preferred",
            OPENROUTER_TOKEN="legacy",
            OPEN_ROUTER_API_KEY="older",
        ):
            settings = Settings(_env_file=None)
        self.assertEqual(settings.openrouter_api_key, "preferred")

    def test_a_blank_process_variable_does_not_wipe_the_file_value(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment(
            OPENROUTER_API_KEY=""
        ):
            path = Path(tmp) / ".env"
            write_env(path, openrouter_api_key="file-key", llm_model="file-model")
            settings = Settings(_env_file=path)
        self.assertEqual(settings.openrouter_api_key, "file-key")
        self.assertEqual(settings.llm_model, "file-model")


@unittest.skipUnless(Settings is not None, globals().get("SKIP_REASON", ""))
class TestTimeouts(unittest.TestCase):
    def test_openrouter_uses_the_feature_default(self):
        with isolated_environment():
            settings = Settings(_env_file=None)
        self.assertEqual(settings.llm(DEFAULT_PARSE_TIMEOUT).timeout, DEFAULT_PARSE_TIMEOUT)
        self.assertEqual(settings.llm(DEFAULT_COOK_TIMEOUT).timeout, DEFAULT_COOK_TIMEOUT)

    def test_local_keeps_its_own_default(self):
        with isolated_environment():
            settings = Settings(_env_file=None, llm_provider="local")
        self.assertEqual(settings.llm(DEFAULT_PARSE_TIMEOUT).timeout, DEFAULT_LOCAL_TIMEOUT)
        self.assertEqual(settings.llm(DEFAULT_COOK_TIMEOUT).timeout, DEFAULT_LOCAL_TIMEOUT)

    def test_llm_timeout_overrides_both_providers(self):
        for provider in ("openrouter", "local"):
            with self.subTest(provider=provider), isolated_environment():
                settings = Settings(
                    _env_file=None, llm_provider=provider, llm_timeout="12.5"
                )
                self.assertEqual(settings.llm(DEFAULT_PARSE_TIMEOUT).timeout, 12.5)
                self.assertEqual(settings.llm(DEFAULT_COOK_TIMEOUT).timeout, 12.5)

    def test_invalid_or_non_positive_timeouts_fall_back(self):
        for raw in ("nope", "0", "-5", "nan", "inf", ""):
            with self.subTest(raw=raw), isolated_environment():
                settings = Settings(_env_file=None, llm_timeout=raw)
                self.assertIsNone(settings.llm_timeout)
                self.assertEqual(
                    settings.llm(DEFAULT_PARSE_TIMEOUT).timeout, DEFAULT_PARSE_TIMEOUT
                )


@unittest.skipUnless(Settings is not None, globals().get("SKIP_REASON", ""))
class TestValidation(unittest.TestCase):
    def test_invalid_values_fail_at_construction(self):
        cases = {
            "llm_provider": "cloud",
            "local_image_width": "wide",
            "local_image_height": 4096,
            "local_image_steps": 0,
            "llm_json_mode": "maybe",
        }
        for field, value in cases.items():
            with self.subTest(field=field), isolated_environment():
                with self.assertRaises(ValidationError) as caught:
                    Settings(_env_file=None, **{field: value})
                self.assertIn(field, str(caught.exception))

    def test_a_bad_file_names_the_file_and_the_field(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment():
            path = Path(tmp) / ".env"
            write_env(path, llm_provider="cloud")
            with self.assertRaises(ConfigurationError) as caught:
                SettingsProvider(path)
        message = str(caught.exception)
        self.assertIn(str(path), message)
        self.assertIn("llm_provider", message)
        self.assertIn("LLM_PROVIDER", message)


@unittest.skipUnless(Settings is not None, globals().get("SKIP_REASON", ""))
class TestLiveReload(unittest.TestCase):
    def test_editing_the_file_changes_current_settings_without_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment():
            path = Path(tmp) / ".env"
            write_env(path, llm_provider="local", llm_model="first-model")
            provider = SettingsProvider(path)
            self.assertEqual(provider.current().llm_model, "first-model")

            before = path.stat().st_mtime_ns
            write_env(path, llm_provider="openrouter", llm_model="second-model")
            # Windows file timestamps are fine-grained, but pin the mtime so
            # this test never races a coarse filesystem clock.
            newer = before + 1_000_000
            os.utime(path, ns=(newer, newer))

            self.assertEqual(provider.current().llm_model, "second-model")
            self.assertEqual(provider.current().llm_provider, "openrouter")

    def test_a_missing_file_starts_with_defaults_and_can_appear_later(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment():
            path = Path(tmp) / ".env"
            provider = SettingsProvider(path)
            self.assertEqual(provider.current().llm_provider, "openrouter")

            write_env(path, llm_provider="local", llm_model="appeared")
            self.assertEqual(provider.current().llm_model, "appeared")

    def test_reload_keeps_the_previous_settings_when_the_edit_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp, isolated_environment():
            path = Path(tmp) / ".env"
            write_env(path, llm_model="good-model")
            provider = SettingsProvider(path)
            self.assertEqual(provider.current().llm_model, "good-model")

            before = path.stat().st_mtime_ns
            write_env(path, llm_provider="cloud")
            newer = before + 1_000_000
            os.utime(path, ns=(newer, newer))
            with self.assertRaises(ConfigurationError):
                provider.current()

            # Fixing the file recovers without a restart.
            before = path.stat().st_mtime_ns
            write_env(path, llm_model="recovered-model")
            newer = before + 1_000_000
            os.utime(path, ns=(newer, newer))
            self.assertEqual(provider.current().llm_model, "recovered-model")


if __name__ == "__main__":
    unittest.main()
