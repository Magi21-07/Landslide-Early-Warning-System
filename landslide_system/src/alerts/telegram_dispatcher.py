# src/alerts/telegram_dispatcher.py
"""
Phase 8.3 Part 2 — Asynchronous Telegram Dispatcher
=====================================================

Consumes an emitted ``AlertEvent`` (Phase 8.2), delegates message formatting
to ``telegram_formatter``, checks the active ``TelegramConfig`` mode
(TEST vs REAL), and delivers the payload asynchronously to
``api.telegram.org`` using ``httpx.AsyncClient``.

Dispatch State Machine
----------------------
event.event_emitted == False
    → SKIPPED_EVENT_NOT_EMITTED  (no network call, no log)

dry_run == True  OR  config.mode == "TEST"  OR  config.enabled == False
    → DRY_RUN_SUCCESS / MOCK_DISPATCH_SUCCESS
      (log the formatted message; NO external network call)

config.mode == "REAL"  AND  config.enabled == True
    → POST https://api.telegram.org/bot<token>/sendMessage
      Handles: timeout, HTTP 429 rate-limit, non-200 status codes.

No unmocked live HTTP calls are ever made during pytest execution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from src.alerts.alert_evaluator import AlertEvent
from src.alerts.telegram_config import TelegramConfig
from src.alerts.telegram_formatter import format_event

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TELEGRAM_API_BASE = "https://api.telegram.org"
_SEND_MESSAGE_PATH = "/bot{token}/sendMessage"
_DEFAULT_TIMEOUT_S = 10.0

# Dispatch status codes surfaced in the return dict
_STATUS_SKIPPED         = "SKIPPED_EVENT_NOT_EMITTED"
_STATUS_DRY_RUN         = "DRY_RUN_SUCCESS"
_STATUS_MOCK            = "MOCK_DISPATCH_SUCCESS"
_STATUS_OK              = "DISPATCH_SUCCESS"
_STATUS_RATE_LIMITED    = "RATE_LIMITED"
_STATUS_HTTP_ERROR      = "HTTP_ERROR"
_STATUS_NETWORK_ERROR   = "NETWORK_ERROR"
_STATUS_TIMEOUT         = "TIMEOUT"


# ---------------------------------------------------------------------------
# TelegramDispatcher
# ---------------------------------------------------------------------------

class TelegramDispatcher:
    """
    Async Telegram alert dispatcher.

    Parameters
    ----------
    config : TelegramConfig | None
        Injected configuration.  When ``None``, a default ``TelegramConfig``
        is instantiated (reads env vars / .env file).

    Usage
    -----
    >>> import asyncio
    >>> dispatcher = TelegramDispatcher(config=TelegramConfig(mode="TEST"))
    >>> result = asyncio.run(dispatcher.send_alert_event(event))
    >>> result["status"]
    'MOCK_DISPATCH_SUCCESS'
    """

    def __init__(self, config: Optional[TelegramConfig] = None) -> None:
        self._config: TelegramConfig = config if config is not None else TelegramConfig()

    # ------------------------------------------------------------------
    # Properties (allow tests to inspect / replace config)
    # ------------------------------------------------------------------

    @property
    def config(self) -> TelegramConfig:
        return self._config

    # ------------------------------------------------------------------
    # Core dispatch method
    # ------------------------------------------------------------------

    async def send_alert_event(
        self,
        event:             AlertEvent,
        *,
        dry_run:           bool                        = False,
        shap_drivers:      Optional[List[Dict[str, Any]]] = None,
        ndvi:              Optional[float]             = None,
        sar_soil_moisture: Optional[float]             = None,
        rainfall_3day_mm:  Optional[float]             = None,
    ) -> Dict[str, Any]:
        """
        Format and dispatch a Telegram alert for an emitted ``AlertEvent``.

        Parameters
        ----------
        event : AlertEvent
            The event produced by ``AlertEvaluator.evaluate_target_risk()``.
        dry_run : bool
            Force TEST/dry-run mode regardless of ``config.mode``.
        shap_drivers : list[dict] | None
            Optional SHAP factor dicts forwarded to the formatter.
        ndvi : float | None
            NDVI value forwarded to the formatter.
        sar_soil_moisture : float | None
            SAR soil-moisture proxy forwarded to the formatter.
        rainfall_3day_mm : float | None
            3-day rainfall in mm forwarded to the formatter.

        Returns
        -------
        dict with keys:
            status        : str   — one of the _STATUS_* constants
            http_code     : int   — HTTP status (200 for dry-runs)
            target_id     : str
            event_type    : str
            message_text  : str   — the formatted Telegram message
            detail        : str   — extra info on success or error
        """
        cfg = self._config

        # ----------------------------------------------------------------
        # GATE 1 — skip unemitted events immediately
        # ----------------------------------------------------------------
        if not event.event_emitted:
            logger.debug(
                "TelegramDispatcher: skipping target='%s' event_type='%s' "
                "(event_emitted=False)",
                event.target_id, event.event_type,
            )
            return {
                "status":       _STATUS_SKIPPED,
                "http_code":    0,
                "target_id":    event.target_id,
                "event_type":   event.event_type,
                "message_text": "",
                "detail":       "event_emitted is False — dispatch skipped.",
            }

        # ----------------------------------------------------------------
        # Format the message (always, so tests can inspect message_text)
        # ----------------------------------------------------------------
        message_text = format_event(
            event,
            shap_drivers      = shap_drivers,
            ndvi              = ndvi,
            sar_soil_moisture = sar_soil_moisture,
            rainfall_3day_mm  = rainfall_3day_mm,
        )

        # ----------------------------------------------------------------
        # GATE 2 — dry-run / TEST / disabled interception
        # ----------------------------------------------------------------
        is_test_mode = (
            dry_run
            or cfg.mode == "TEST"
            or not cfg.enabled
        )

        if is_test_mode:
            mode_label = (
                "dry_run=True" if dry_run
                else f"mode={cfg.mode}" if cfg.mode == "TEST"
                else "enabled=False"
            )
            status = _STATUS_DRY_RUN if dry_run else _STATUS_MOCK
            logger.info(
                "TelegramDispatcher: %s — target='%s' event_type='%s'\n%s",
                mode_label, event.target_id, event.event_type, message_text,
            )
            return {
                "status":       status,
                "http_code":    200,
                "target_id":    event.target_id,
                "event_type":   event.event_type,
                "message_text": message_text,
                "detail":       f"Message formatted but not sent ({mode_label}).",
            }

        # ----------------------------------------------------------------
        # GATE 3 — REAL mode live dispatch
        # ----------------------------------------------------------------
        return await self._dispatch_real(event, message_text)

    # ------------------------------------------------------------------
    # Internal: live HTTP dispatch
    # ------------------------------------------------------------------

    async def _dispatch_real(
        self,
        event:        AlertEvent,
        message_text: str,
    ) -> Dict[str, Any]:
        """
        POST the formatted message to api.telegram.org.

        All network errors are caught and returned as structured error dicts.
        """
        from src.alerts.providers.telegram_provider import TelegramProvider
        
        cfg   = self._config
        chat_id = (
            cfg.chat_id
            or (
                event.policy_decision.telegram_chat_id
                if event.policy_decision
                else None
            )
            or ""
        )

        logger.info(
            "TelegramDispatcher: REAL dispatch → target='%s' event_type='%s'",
            event.target_id, event.event_type,
        )

        provider = TelegramProvider(cfg)
        result = await provider.send_message(chat_id, message_text)

        if result["success"]:
            logger.info(
                "TelegramDispatcher: success — target='%s' event_type='%s'",
                event.target_id, event.event_type,
            )
            return {
                "status":       _STATUS_OK,
                "http_code":    200,
                "target_id":    event.target_id,
                "event_type":   event.event_type,
                "message_text": message_text,
                "detail":       "Message dispatched to Telegram API.",
            }
        else:
            err_code = result["error_code"]
            msg = result["error_message"]
            
            # Map provider error codes back to dispatcher status and http codes for backwards compatibility
            code_map = {
                "RATE_LIMITED": (_STATUS_RATE_LIMITED, 429),
                "TELEGRAM_SERVER_ERROR": (_STATUS_HTTP_ERROR, 500),
                "NETWORK_TIMEOUT": (_STATUS_TIMEOUT, 0),
                "CONNECTION_FAILED": (_STATUS_NETWORK_ERROR, 0),
                "INVALID_REQUEST_OR_CHAT_ID": (_STATUS_HTTP_ERROR, 400),
                "BOT_PERMISSION_DENIED": (_STATUS_HTTP_ERROR, 403),
                "UNKNOWN_HTTP_ERROR": (_STATUS_HTTP_ERROR, 0),
            }
            
            # Note: For some reason, test_real_mode_http_500_returns_http_error explicitly expects 500
            # in detail message if it's 500. `TELEGRAM_SERVER_ERROR` in the provider puts exactly that.
            status, http_code = code_map.get(err_code, (_STATUS_HTTP_ERROR, 0))
            
            if err_code in ("NETWORK_TIMEOUT", "CONNECTION_FAILED"):
                logger.error(
                    "TelegramDispatcher: %s for target='%s': %s",
                    err_code, event.target_id, msg,
                )
            elif err_code == "RATE_LIMITED":
                logger.warning("TelegramDispatcher: rate limited (429). Retry-After: unknown")
            else:
                logger.error(
                    "TelegramDispatcher: HTTP error %s for target='%s'",
                    http_code, event.target_id,
                )

            return {
                "status":       status,
                "http_code":    http_code,
                "target_id":    event.target_id,
                "event_type":   event.event_type,
                "message_text": message_text,
                "detail":       msg,
            }
