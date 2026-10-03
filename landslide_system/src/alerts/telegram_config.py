# src/alerts/telegram_config.py
"""
Phase 8.3 — Telegram Bot Configuration & Credential Security
=============================================================

Loads, validates, and safely exposes Telegram configuration from environment
variables (or a .env file).  Enforces strict security boundaries:

  - TELEGRAM_BOT_TOKEN is always stored as ``pydantic.SecretStr``, meaning it
    is masked automatically in __repr__, __str__, logging, and exception
    tracebacks.
  - No raw token or chat ID value is ever surfaced through public helpers or
    string representations.
  - REAL mode enforces non-empty credentials; TEST mode allows absent creds so
    unit tests and offline development work without live secrets.

Modes
-----
TEST (default)
    Credentials are optional.  No live Telegram messages may be dispatched.

REAL
    Both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be populated when
    TELEGRAM_ENABLED=true.  Missing credentials raise ConfigurationError at
    instantiation time, not at dispatch time.

Usage
-----
>>> from src.alerts.telegram_config import TelegramConfig
>>> cfg = TelegramConfig()
>>> cfg.get_safe_status()
{'configured': True, 'enabled': True, 'mode': 'TEST', ...}

No HTTP requests are made in this module.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ConfigurationError(RuntimeError):
    """
    Raised when the Telegram configuration is invalid for the selected mode.

    The message intentionally avoids including partial secret values.
    """


# ---------------------------------------------------------------------------
# Valid mode constants
# ---------------------------------------------------------------------------

_VALID_MODES = frozenset({"TEST", "REAL"})


# ---------------------------------------------------------------------------
# TelegramConfig (pydantic-settings BaseSettings)
# ---------------------------------------------------------------------------

class TelegramConfig(BaseSettings):
    """
    Telegram bot configuration loaded from environment variables.

    Environment variables
    ---------------------
    TELEGRAM_BOT_TOKEN  : str        — Bot token (stored as SecretStr).
    TELEGRAM_CHAT_ID    : str        — Destination chat / channel ID.
    TELEGRAM_ENABLED    : bool       — Master switch (default: True).
    TELEGRAM_MODE       : str        — "TEST" | "REAL" (default: "TEST").

    Security guarantees
    -------------------
    * ``bot_token`` is a ``SecretStr`` — printing or logging the model never
      reveals the raw token string.
    * ``get_safe_status()`` exposes only boolean presence flags, never values.
    * ``__repr__`` and ``__str__`` are overridden to prevent accidental leakage.
    """

    model_config = SettingsConfigDict(
        # Support optional .env file — ignored if absent
        env_file=".env",
        env_file_encoding="utf-8",
        # Populate from the named env vars below
        populate_by_name=True,
        # Forbid extra fields so typos in env-var names are caught early
        extra="ignore",
        # Case-insensitive env var lookup
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    bot_token: Optional[SecretStr] = None
    """TELEGRAM_BOT_TOKEN — stored as SecretStr; never logged in plaintext."""

    chat_id: Optional[str] = None
    """TELEGRAM_CHAT_ID — destination chat or channel identifier."""

    enabled: bool = True
    """TELEGRAM_ENABLED — master on/off switch (default True)."""

    mode: str = "TEST"
    """TELEGRAM_MODE — "TEST" (no live dispatch) or "REAL" (live dispatch)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
        case_sensitive=False,
        # Map env-var names → field names
        env_prefix="TELEGRAM_",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("mode", mode="before")
    @classmethod
    def _validate_mode(cls, v: Any) -> str:
        """Normalise to uppercase and reject unrecognised modes."""
        normalised = str(v).strip().upper()
        if normalised not in _VALID_MODES:
            raise ValueError(
                f"TELEGRAM_MODE must be one of {sorted(_VALID_MODES)!r}; "
                f"got {str(v)!r}."
            )
        return normalised

    @model_validator(mode="after")
    def _validate_real_mode_credentials(self) -> "TelegramConfig":
        """
        When mode is REAL and enabled is True, both bot_token and chat_id
        must be populated.

        The error message deliberately omits partial secret values.
        """
        if self.mode == "REAL" and self.enabled:
            missing: list[str] = []
            if not self.bot_token or not self.bot_token.get_secret_value().strip():
                missing.append("TELEGRAM_BOT_TOKEN")
            if not self.chat_id or not self.chat_id.strip():
                missing.append("TELEGRAM_CHAT_ID")
            if missing:
                raise ConfigurationError(
                    f"TELEGRAM_MODE=REAL with TELEGRAM_ENABLED=true requires "
                    f"the following environment variables to be set and non-empty: "
                    f"{missing}.  "
                    f"Set TELEGRAM_MODE=TEST or supply the missing credentials."
                )
        return self

    # ------------------------------------------------------------------
    # Safe public helpers
    # ------------------------------------------------------------------

    def get_safe_status(self) -> dict:
        """
        Return a safe status dictionary that exposes ONLY boolean presence
        flags — never raw token or chat ID values.

        Returns
        -------
        dict with keys:
            configured   : bool  — True when config is valid for the current mode.
            enabled      : bool  — True when TELEGRAM_ENABLED=true.
            mode         : str   — "TEST" or "REAL".
            chat_id_set  : bool  — True when TELEGRAM_CHAT_ID is present & non-empty.
            bot_token_set: bool  — True when TELEGRAM_BOT_TOKEN is present & non-empty.
        """
        token_set   = bool(
            self.bot_token and self.bot_token.get_secret_value().strip()
        )
        chat_id_set = bool(self.chat_id and self.chat_id.strip())

        if self.mode == "TEST":
            configured = True          # TEST mode is always considered configured
        else:
            # REAL mode: must have both credentials when enabled
            configured = (token_set and chat_id_set) if self.enabled else True

        return {
            "configured":    configured,
            "enabled":       self.enabled,
            "mode":          self.mode,
            "chat_id_set":   chat_id_set,
            "bot_token_set": token_set,
        }

    # ------------------------------------------------------------------
    # Security: suppress secret leakage via str/repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TelegramConfig("
            f"enabled={self.enabled}, "
            f"mode={self.mode!r}, "
            f"bot_token_set={bool(self.bot_token)}, "
            f"chat_id_set={bool(self.chat_id)}"
            f")"
        )

    def __str__(self) -> str:  # pragma: no cover
        return self.__repr__()
