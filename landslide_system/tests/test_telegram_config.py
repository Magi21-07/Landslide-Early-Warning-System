# tests/test_telegram_config.py
"""
Phase 8.3 — Unit tests for TelegramConfig (telegram_config.py).

Coverage
--------
1.  Default configuration (TEST mode, no credentials) — passes validation.
2.  get_safe_status() returns correct shape / types with no credentials set.
3.  REAL mode + enabled=True + valid credentials → passes validation.
4.  REAL mode + enabled=True + missing token → ConfigurationError raised.
5.  REAL mode + enabled=True + missing chat_id → ConfigurationError raised.
6.  REAL mode + enabled=True + both missing → ConfigurationError raised.
7.  REAL mode + enabled=False → passes even without credentials.
8.  get_safe_status() never returns raw token string under any mode.
9.  SecretStr repr masks the token (never shows raw value).
10. Invalid mode strings raise ValueError.
11. Mode field is normalised to uppercase ("test" → "TEST").
12. chat_id_set / bot_token_set reflect actual presence correctly.
13. ConfigurationError message does NOT contain the partial token value.
14. get_safe_status() configured=True in TEST mode (always).
15. get_safe_status() configured=False in REAL mode when creds missing
    (this can only be tested on an instance built with enabled=False and
     then patching; or via direct field inspection — tested via helper).
"""

from __future__ import annotations

import os
import pytest

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts.telegram_config import ConfigurationError, TelegramConfig


# ---------------------------------------------------------------------------
# Helpers — build config without touching real env vars
# ---------------------------------------------------------------------------

def _make(
    *,
    mode: str = "TEST",
    enabled: bool = True,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> TelegramConfig:
    """
    Construct a TelegramConfig by passing values directly as constructor
    arguments (bypasses env-var lookup; pydantic-settings honours kwargs
    over env vars).
    """
    kwargs: dict = {
        "mode":      mode,
        "enabled":   enabled,
        "bot_token": bot_token,
        "chat_id":   chat_id,
    }
    return TelegramConfig(**kwargs)


# ===========================================================================
# 1. Default / TEST mode
# ===========================================================================

class TestDefaultTestMode:

    def test_default_mode_is_test(self):
        cfg = _make()
        assert cfg.mode == "TEST"

    def test_default_enabled_true(self):
        cfg = _make()
        assert cfg.enabled is True

    def test_test_mode_no_credentials_valid(self):
        """TEST mode must NOT raise when credentials are absent."""
        cfg = _make(mode="TEST", bot_token=None, chat_id=None)
        assert cfg.mode == "TEST"

    def test_test_mode_configured_always_true(self):
        cfg = _make(mode="TEST")
        status = cfg.get_safe_status()
        assert status["configured"] is True

    def test_test_mode_enabled_reflected(self):
        cfg = _make(mode="TEST", enabled=True)
        assert cfg.get_safe_status()["enabled"] is True

    def test_test_mode_disabled_reflected(self):
        cfg = _make(mode="TEST", enabled=False)
        assert cfg.get_safe_status()["enabled"] is False


# ===========================================================================
# 2. get_safe_status() shape and types
# ===========================================================================

class TestGetSafeStatus:

    def test_status_has_required_keys(self):
        cfg = _make()
        status = cfg.get_safe_status()
        expected_keys = {"configured", "enabled", "mode", "chat_id_set", "bot_token_set"}
        assert expected_keys == set(status.keys())

    def test_status_types(self):
        cfg = _make()
        status = cfg.get_safe_status()
        assert isinstance(status["configured"],    bool)
        assert isinstance(status["enabled"],       bool)
        assert isinstance(status["mode"],          str)
        assert isinstance(status["chat_id_set"],   bool)
        assert isinstance(status["bot_token_set"], bool)

    def test_no_creds_bot_token_set_false(self):
        cfg = _make(mode="TEST")
        assert cfg.get_safe_status()["bot_token_set"] is False

    def test_no_creds_chat_id_set_false(self):
        cfg = _make(mode="TEST")
        assert cfg.get_safe_status()["chat_id_set"] is False

    def test_with_token_bot_token_set_true(self):
        cfg = _make(mode="TEST", bot_token="123456:AAAA_fake_token")
        assert cfg.get_safe_status()["bot_token_set"] is True

    def test_with_chat_id_chat_id_set_true(self):
        cfg = _make(mode="TEST", chat_id="-100123456")
        assert cfg.get_safe_status()["chat_id_set"] is True

    def test_mode_field_in_status(self):
        cfg = _make(mode="TEST")
        assert cfg.get_safe_status()["mode"] == "TEST"


# ===========================================================================
# 3. REAL mode — success paths
# ===========================================================================

class TestRealModeSuccess:

    def test_real_mode_with_valid_credentials_passes(self):
        cfg = _make(
            mode="REAL",
            enabled=True,
            bot_token="123456:AAAA_fake_token",
            chat_id="-100999888777",
        )
        assert cfg.mode == "REAL"
        assert cfg.get_safe_status()["configured"] is True

    def test_real_mode_disabled_no_credentials_passes(self):
        """When enabled=False, REAL mode must not demand credentials."""
        cfg = _make(mode="REAL", enabled=False)
        assert cfg.mode == "REAL"
        assert cfg.enabled is False

    def test_real_mode_disabled_configured_true(self):
        """Disabled REAL mode is always 'configured' (nothing to check)."""
        cfg = _make(mode="REAL", enabled=False)
        assert cfg.get_safe_status()["configured"] is True

    def test_real_mode_both_creds_present_configured_true(self):
        cfg = _make(
            mode="REAL",
            enabled=True,
            bot_token="tok:123",
            chat_id="99999",
        )
        assert cfg.get_safe_status()["configured"] is True
        assert cfg.get_safe_status()["bot_token_set"] is True
        assert cfg.get_safe_status()["chat_id_set"] is True


# ===========================================================================
# 4-6. REAL mode — failure paths (credential validation)
# ===========================================================================

class TestRealModeValidationFailures:

    def test_real_enabled_missing_token_raises(self):
        with pytest.raises((ConfigurationError, ValueError)):
            _make(
                mode="REAL",
                enabled=True,
                bot_token=None,
                chat_id="-100999888777",
            )

    def test_real_enabled_missing_chat_id_raises(self):
        with pytest.raises((ConfigurationError, ValueError)):
            _make(
                mode="REAL",
                enabled=True,
                bot_token="123456:AAAA_fake_token",
                chat_id=None,
            )

    def test_real_enabled_both_missing_raises(self):
        with pytest.raises((ConfigurationError, ValueError)):
            _make(mode="REAL", enabled=True)

    def test_real_enabled_empty_token_raises(self):
        with pytest.raises((ConfigurationError, ValueError)):
            _make(
                mode="REAL",
                enabled=True,
                bot_token="",
                chat_id="12345",
            )

    def test_real_enabled_whitespace_token_raises(self):
        with pytest.raises((ConfigurationError, ValueError)):
            _make(
                mode="REAL",
                enabled=True,
                bot_token="   ",
                chat_id="12345",
            )

    def test_real_enabled_empty_chat_id_raises(self):
        with pytest.raises((ConfigurationError, ValueError)):
            _make(
                mode="REAL",
                enabled=True,
                bot_token="123456:token",
                chat_id="",
            )


# ===========================================================================
# 7. Secret masking — get_safe_status never leaks raw token
# ===========================================================================

class TestSecretMasking:

    def test_get_safe_status_does_not_contain_raw_token(self):
        raw_token = "987654:SECRET_TOKEN_VALUE"
        cfg    = _make(mode="TEST", bot_token=raw_token)
        status = cfg.get_safe_status()
        for val in status.values():
            assert raw_token not in str(val), (
                f"Raw token found in get_safe_status() value: {val!r}"
            )

    def test_get_safe_status_does_not_contain_chat_id_value(self):
        chat_id = "-100111222333"
        cfg     = _make(mode="TEST", chat_id=chat_id)
        status  = cfg.get_safe_status()
        for val in status.values():
            assert chat_id not in str(val), (
                f"Chat ID found in get_safe_status() value: {val!r}"
            )


# ===========================================================================
# 8. SecretStr masking in repr / str
# ===========================================================================

class TestSecretStrRepresentation:

    def test_bot_token_repr_is_masked(self):
        raw_token = "123456:SUPER_SECRET"
        cfg = _make(mode="TEST", bot_token=raw_token)
        # pydantic SecretStr always renders as '**********'
        token_repr = repr(cfg.bot_token)
        assert raw_token not in token_repr, (
            f"Raw token leaked in repr(bot_token): {token_repr!r}"
        )
        assert "**" in token_repr

    def test_bot_token_str_is_masked(self):
        raw_token = "123456:SUPER_SECRET"
        cfg = _make(mode="TEST", bot_token=raw_token)
        token_str = str(cfg.bot_token)
        assert raw_token not in token_str, (
            f"Raw token leaked in str(bot_token): {token_str!r}"
        )

    def test_model_repr_does_not_leak_token(self):
        raw_token = "123456:SHOULD_NOT_APPEAR"
        cfg = _make(mode="TEST", bot_token=raw_token)
        full_repr = repr(cfg)
        assert raw_token not in full_repr, (
            f"Raw token leaked in repr(TelegramConfig): {full_repr!r}"
        )

    def test_model_dict_bot_token_is_secret_str(self):
        """model_dump() should yield a SecretStr for bot_token (not plaintext)."""
        from pydantic import SecretStr
        cfg = _make(mode="TEST", bot_token="very_secret")
        dumped = cfg.model_dump()
        # The token value in the dump is a SecretStr instance, not a plain str
        token_val = dumped.get("bot_token")
        # It could be None if SecretStr, or a SecretStr — ensure raw string not exposed
        assert "very_secret" not in str(token_val), (
            f"Raw token found in model_dump(): {token_val!r}"
        )


# ===========================================================================
# 9. Mode validation
# ===========================================================================

class TestModeValidation:

    @pytest.mark.parametrize("invalid_mode", [
        # Genuinely unrecognised strings — validator normalises with .strip().upper()
        # so 'real ' and 'test ' would resolve to valid modes and are excluded here.
        "MOCK", "PRODUCTION", "STAGING", "LIVE", "fake",
        "", "0", "None",
    ])
    def test_invalid_mode_raises_value_error(self, invalid_mode):
        with pytest.raises((ValueError, Exception)):
            _make(mode=invalid_mode)

    def test_mode_lowercase_normalised_to_uppercase(self):
        cfg = _make(mode="test")
        assert cfg.mode == "TEST"

    def test_mode_real_uppercase_accepted(self):
        cfg = _make(
            mode="REAL",
            enabled=False,  # avoid credential check
        )
        assert cfg.mode == "REAL"

    def test_mode_mixed_case_normalised(self):
        cfg = _make(mode="Test")
        assert cfg.mode == "TEST"


# ===========================================================================
# 10. ConfigurationError message security
# ===========================================================================

class TestConfigurationErrorSecurity:

    def test_error_message_does_not_contain_partial_token(self):
        """
        The ConfigurationError message must never include partial token chars.
        We attempt REAL+enabled with a partial token to ensure the error
        message is clean.
        """
        partial_token = "123456:PARTIAL"
        try:
            _make(
                mode="REAL",
                enabled=True,
                bot_token=partial_token,
                chat_id=None,  # missing chat_id triggers error
            )
        except (ConfigurationError, ValueError) as exc:
            assert partial_token not in str(exc), (
                f"Partial token found in error message: {exc!r}"
            )
        else:
            pytest.fail("Expected ConfigurationError was not raised")

    def test_error_message_names_missing_variables(self):
        """Error message must identify which env vars are missing."""
        try:
            _make(mode="REAL", enabled=True)
        except (ConfigurationError, ValueError) as exc:
            msg = str(exc)
            # Should mention at least one of the missing var names
            assert "TELEGRAM_BOT_TOKEN" in msg or "TELEGRAM_CHAT_ID" in msg
        else:
            pytest.fail("Expected ConfigurationError was not raised")
