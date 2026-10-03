# tests/test_telegram_dispatcher.py
"""
Phase 8.3 Part 2 — Unit tests for TelegramFormatter and TelegramDispatcher.

All external HTTP calls are intercepted via httpx.MockTransport /
unittest.mock — no live network calls are ever made.

Coverage
--------
Formatter tests (TestTelegramFormatter)
    1.  CRITICAL event renders emergency header.
    2.  HIGH event renders warning header.
    3.  RECOVERY event renders recovery header.
    4.  Probability renders as integer percentage.
    5.  SHAP drivers render with signed contribution percentages.
    6.  Satellite metrics render NDVI, SAR, and rainfall lines.
    7.  GIS Dashboard link is present and contains target_id.
    8.  format_event() convenience wrapper works with AlertEvent.

Dispatcher tests (TestTelegramDispatcher)
    9.  Unemitted event → SKIPPED_EVENT_NOT_EMITTED (no network).
    10. TEST mode → MOCK_DISPATCH_SUCCESS without network call.
    11. dry_run=True → DRY_RUN_SUCCESS without network call.
    12. disabled config → MOCK_DISPATCH_SUCCESS without network call.
    13. REAL mode mock POST → DISPATCH_SUCCESS, correct URL and payload.
    14. REAL mode HTTP 429 → RATE_LIMITED, no exception raised.
    15. REAL mode HTTP 500 → HTTP_ERROR, no exception raised.
    16. REAL mode network timeout → TIMEOUT, no exception raised.
    17. REAL mode network error → NETWORK_ERROR, no exception raised.
    18. message_text is always populated (even on skip return).
    19. Return dict always has required keys.
"""

from __future__ import annotations

import asyncio
import datetime
import sys
import os
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts.alert_evaluator import AlertEvent
from src.alerts.alert_policy import AlertDecision
from src.alerts.telegram_config import TelegramConfig
from src.alerts.telegram_dispatcher import TelegramDispatcher
from src.alerts.telegram_formatter import format_alert_message, format_event


# ===========================================================================
# Helpers
# ===========================================================================

def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_decision(
    triggered: bool = True,
    alert_level: str = "WARNING",
    telegram_enabled: bool = False,
    telegram_chat_id: str | None = None,
) -> AlertDecision:
    return AlertDecision(
        alert_triggered=triggered,
        alert_level=alert_level,
        triggering_risk_level="HIGH",
        probability=0.68,
        reason="test reason",
        data_quality="VALID",
        stale=False,
        allowed_channels=["email"] if triggered else [],
        triggered_at=_now_utc(),
        target_id="LOC_TEST",
        telegram_enabled=telegram_enabled,
        telegram_chat_id=telegram_chat_id,
        telegram_alert_level="NO_ALERT",
    )


def _make_event(
    *,
    event_emitted: bool = True,
    event_type: str = "INITIAL_TRIGGER",
    current_risk_level: str = "HIGH",
    probability: float = 0.68,
    previous_risk_level: str | None = None,
    target_id: str = "LOC_TEST",
    model_version: str = "v2",
    data_quality: str = "VALID",
) -> AlertEvent:
    return AlertEvent(
        target_id=target_id,
        event_emitted=event_emitted,
        event_type=event_type,
        previous_risk_level=previous_risk_level,
        current_risk_level=current_risk_level,
        probability=probability,
        trigger_reason="test trigger",
        triggered_at=_now_utc(),
        model_version=model_version,
        risk_evaluation_timestamp=_now_utc(),
        data_quality=data_quality,
        stale=False,
        policy_decision=_make_decision(triggered=event_emitted),
    )


def _make_cfg(
    mode: str = "TEST",
    enabled: bool = True,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> TelegramConfig:
    kwargs: dict = {"mode": mode, "enabled": enabled}
    if bot_token:
        kwargs["bot_token"] = bot_token
    if chat_id:
        kwargs["chat_id"] = chat_id
    return TelegramConfig(**kwargs)


_SHAP = [
    {"feature": "slope_degrees",    "contribution": 0.34},
    {"feature": "rainfall_3day_mm", "contribution": 0.28},
    {"feature": "ndvi",             "contribution": -0.12},
]

_REQUIRED_RESULT_KEYS = {"status", "http_code", "target_id", "event_type",
                         "message_text", "detail"}


# ===========================================================================
# Formatter tests
# ===========================================================================

class TestTelegramFormatter:

    def test_critical_event_has_emergency_header(self):
        msg = format_alert_message(
            target_id="LOC_A",
            current_risk_level="CRITICAL",
            event_type="INITIAL_TRIGGER",
            probability=0.82,
            triggered_at=_now_utc(),
        )
        assert "CRITICAL LANDSLIDE EMERGENCY" in msg
        assert "🚨" in msg

    def test_high_event_has_warning_header(self):
        msg = format_alert_message(
            target_id="LOC_B",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.68,
            triggered_at=_now_utc(),
        )
        assert "HIGH LANDSLIDE WARNING" in msg
        assert "⚠️" in msg

    def test_escalation_event_has_emergency_header(self):
        msg = format_alert_message(
            target_id="LOC_C",
            current_risk_level="CRITICAL",
            event_type="ESCALATION",
            probability=0.88,
            triggered_at=_now_utc(),
            previous_risk_level="HIGH",
        )
        assert "CRITICAL LANDSLIDE EMERGENCY" in msg

    def test_recovery_event_has_recovery_header(self):
        msg = format_alert_message(
            target_id="LOC_D",
            current_risk_level="MODERATE",
            event_type="RECOVERY",
            probability=0.40,
            triggered_at=_now_utc(),
            previous_risk_level="HIGH",
        )
        assert "RECOVERY" in msg
        assert "🟢" in msg

    def test_de_escalation_event_has_recovery_header(self):
        msg = format_alert_message(
            target_id="LOC_E",
            current_risk_level="HIGH",
            event_type="DE_ESCALATION",
            probability=0.65,
            triggered_at=_now_utc(),
            previous_risk_level="CRITICAL",
        )
        assert "🟢" in msg

    def test_probability_renders_as_percentage(self):
        msg = format_alert_message(
            target_id="LOC_F",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.82,
            triggered_at=_now_utc(),
        )
        assert "82%" in msg

    def test_probability_rounds_to_integer(self):
        msg = format_alert_message(
            target_id="LOC_G",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.756,
            triggered_at=_now_utc(),
        )
        assert "76%" in msg

    def test_target_id_in_message(self):
        msg = format_alert_message(
            target_id="HILLSIDE_SECTOR_7",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.68,
            triggered_at=_now_utc(),
        )
        assert "HILLSIDE_SECTOR_7" in msg

    def test_shap_drivers_rendered(self):
        msg = format_alert_message(
            target_id="LOC_H",
            current_risk_level="CRITICAL",
            event_type="INITIAL_TRIGGER",
            probability=0.88,
            triggered_at=_now_utc(),
            shap_drivers=_SHAP,
        )
        assert "slope_degrees" in msg
        assert "+34%" in msg
        assert "rainfall_3day_mm" in msg
        assert "+28%" in msg

    def test_shap_negative_contribution_signed(self):
        msg = format_alert_message(
            target_id="LOC_I",
            current_risk_level="CRITICAL",
            event_type="INITIAL_TRIGGER",
            probability=0.88,
            triggered_at=_now_utc(),
            shap_drivers=_SHAP,
        )
        assert "-12%" in msg

    def test_shap_truncated_to_3_drivers(self):
        many_drivers = [
            {"feature": f"feat_{i}", "contribution": 0.1}
            for i in range(10)
        ]
        msg = format_alert_message(
            target_id="LOC_J",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
            shap_drivers=many_drivers,
        )
        # Only first 3 features should appear
        assert "feat_0" in msg
        assert "feat_2" in msg
        assert "feat_3" not in msg

    def test_ndvi_metric_rendered(self):
        msg = format_alert_message(
            target_id="LOC_K",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
            ndvi=0.423,
        )
        assert "NDVI" in msg
        assert "0.423" in msg

    def test_sar_soil_moisture_rendered(self):
        msg = format_alert_message(
            target_id="LOC_L",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
            sar_soil_moisture=0.651,
        )
        assert "SAR" in msg
        assert "0.651" in msg

    def test_rainfall_metric_rendered(self):
        msg = format_alert_message(
            target_id="LOC_M",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
            rainfall_3day_mm=127.5,
        )
        assert "127.5" in msg
        assert "mm" in msg

    def test_dashboard_link_contains_target_id(self):
        msg = format_alert_message(
            target_id="SECTOR_GAMMA",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
        )
        assert "dashboard.landslide.local/target/SECTOR_GAMMA" in msg

    def test_no_env_metrics_section_when_none(self):
        msg = format_alert_message(
            target_id="LOC_N",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
        )
        assert "SAR Soil-Moisture" not in msg
        assert "NDVI" not in msg

    def test_format_event_convenience_wrapper(self):
        """format_event() must produce the same output as format_alert_message()."""
        event = _make_event(
            current_risk_level="CRITICAL",
            event_type="ESCALATION",
            probability=0.90,
            target_id="LOC_WRAP",
        )
        msg = format_event(event, shap_drivers=_SHAP, ndvi=0.31)
        assert "CRITICAL LANDSLIDE EMERGENCY" in msg
        assert "slope_degrees" in msg
        assert "LOC_WRAP" in msg

    def test_action_guidance_critical(self):
        msg = format_alert_message(
            target_id="LOC_O",
            current_risk_level="CRITICAL",
            event_type="INITIAL_TRIGGER",
            probability=0.85,
            triggered_at=_now_utc(),
        )
        assert "Evacuate" in msg or "evacuation" in msg.lower() or "Immediate" in msg

    def test_action_guidance_high(self):
        msg = format_alert_message(
            target_id="LOC_P",
            current_risk_level="HIGH",
            event_type="INITIAL_TRIGGER",
            probability=0.70,
            triggered_at=_now_utc(),
        )
        assert "Monitor" in msg or "monitoring" in msg.lower() or "Deploy" in msg

    def test_transition_arrow_shown_when_prev_available(self):
        msg = format_alert_message(
            target_id="LOC_Q",
            current_risk_level="CRITICAL",
            event_type="ESCALATION",
            probability=0.85,
            triggered_at=_now_utc(),
            previous_risk_level="HIGH",
        )
        assert "HIGH" in msg
        assert "CRITICAL" in msg
        assert "→" in msg


# ===========================================================================
# Dispatcher tests
# ===========================================================================

class TestTelegramDispatcher:

    # -----------------------------------------------------------------------
    # 9. Unemitted event → SKIPPED immediately
    # -----------------------------------------------------------------------

    def test_unemitted_event_returns_skipped(self):
        event      = _make_event(event_emitted=False, event_type="PERSISTENT_UNCHANGED")
        dispatcher = TelegramDispatcher(config=_make_cfg())
        result     = asyncio.run(dispatcher.send_alert_event(event))
        assert result["status"] == "SKIPPED_EVENT_NOT_EMITTED"
        assert result["http_code"] == 0

    def test_unemitted_event_no_network_call(self):
        """SKIPPED path must never touch httpx."""
        event = _make_event(event_emitted=False)
        with patch("httpx.AsyncClient") as mock_client:
            asyncio.run(TelegramDispatcher(config=_make_cfg()).send_alert_event(event))
            mock_client.assert_not_called()

    # -----------------------------------------------------------------------
    # 10. TEST mode → MOCK_DISPATCH_SUCCESS
    # -----------------------------------------------------------------------

    def test_test_mode_returns_mock_success(self):
        event      = _make_event()
        dispatcher = TelegramDispatcher(config=_make_cfg(mode="TEST"))
        result     = asyncio.run(dispatcher.send_alert_event(event))
        assert result["status"] == "MOCK_DISPATCH_SUCCESS"
        assert result["http_code"] == 200

    def test_test_mode_no_network_call(self):
        event = _make_event()
        with patch("httpx.AsyncClient") as mock_client:
            asyncio.run(
                TelegramDispatcher(config=_make_cfg(mode="TEST")).send_alert_event(event)
            )
            mock_client.assert_not_called()

    def test_test_mode_message_text_populated(self):
        event  = _make_event(current_risk_level="CRITICAL", event_type="INITIAL_TRIGGER")
        result = asyncio.run(
            TelegramDispatcher(config=_make_cfg(mode="TEST")).send_alert_event(event)
        )
        assert len(result["message_text"]) > 50
        assert "CRITICAL" in result["message_text"]

    # -----------------------------------------------------------------------
    # 11. dry_run=True → DRY_RUN_SUCCESS
    # -----------------------------------------------------------------------

    def test_dry_run_returns_dry_run_success(self):
        # Even with REAL mode, dry_run overrides to DRY_RUN_SUCCESS
        event = _make_event()
        cfg   = _make_cfg(mode="REAL", enabled=False)  # disabled avoids cred check
        result = asyncio.run(
            TelegramDispatcher(config=cfg).send_alert_event(event, dry_run=True)
        )
        assert result["status"] == "DRY_RUN_SUCCESS"
        assert result["http_code"] == 200

    def test_dry_run_no_network_call(self):
        event = _make_event()
        cfg   = _make_cfg(mode="REAL", enabled=False)
        with patch("httpx.AsyncClient") as mock_client:
            asyncio.run(
                TelegramDispatcher(config=cfg).send_alert_event(event, dry_run=True)
            )
            mock_client.assert_not_called()

    # -----------------------------------------------------------------------
    # 12. config.enabled == False → MOCK_DISPATCH_SUCCESS
    # -----------------------------------------------------------------------

    def test_disabled_config_returns_mock_success(self):
        event  = _make_event()
        cfg    = _make_cfg(mode="TEST", enabled=False)
        result = asyncio.run(TelegramDispatcher(config=cfg).send_alert_event(event))
        assert result["status"] == "MOCK_DISPATCH_SUCCESS"
        assert result["http_code"] == 200

    # -----------------------------------------------------------------------
    # 13. REAL mode mock POST → DISPATCH_SUCCESS
    # -----------------------------------------------------------------------

    def test_real_mode_success_dispatch(self):
        """
        Mock httpx.AsyncClient so we can verify the POST is made to the
        correct URL with the correct payload without hitting the network.
        """
        event = _make_event(
            current_risk_level="CRITICAL",
            event_type="INITIAL_TRIGGER",
            probability=0.85,
        )
        cfg = _make_cfg(
            mode="REAL",
            enabled=True,
            bot_token="123456:FAKE_TOKEN",
            chat_id="-100123456",
        )

        # Build a mock HTTP response (status 200)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        # AsyncClient as async context manager
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            result = asyncio.run(
                TelegramDispatcher(config=cfg).send_alert_event(event)
            )

        assert result["status"] == "DISPATCH_SUCCESS"
        assert result["http_code"] == 200
        assert result["target_id"] == "LOC_TEST"

    def test_real_mode_post_url_contains_token_path(self):
        """Verify the URL sent to httpx contains /bot<token>/sendMessage."""
        event = _make_event()
        cfg   = _make_cfg(
            mode="REAL",
            enabled=True,
            bot_token="TOKEN_ABC",
            chat_id="-999",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            asyncio.run(TelegramDispatcher(config=cfg).send_alert_event(event))

        call_url = mock_client.post.call_args[0][0]
        assert "TOKEN_ABC" in call_url
        assert "sendMessage" in call_url

    def test_real_mode_post_payload_has_chat_id(self):
        """Verify chat_id is included in the POST data payload."""
        event = _make_event()
        cfg   = _make_cfg(
            mode="REAL",
            enabled=True,
            bot_token="T",
            chat_id="-100987",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            asyncio.run(TelegramDispatcher(config=cfg).send_alert_event(event))

        call_kwargs = mock_client.post.call_args
        # data is passed as keyword arg 'data'
        data_payload = call_kwargs[1].get("data") or call_kwargs[0][1]
        assert data_payload["chat_id"] == "-100987"
        assert data_payload["parse_mode"] == "Markdown"

    # -----------------------------------------------------------------------
    # 14. HTTP 429 → RATE_LIMITED, no exception
    # -----------------------------------------------------------------------

    def test_real_mode_http_429_returns_rate_limited(self):
        event = _make_event()
        cfg   = _make_cfg(
            mode="REAL", enabled=True, bot_token="T", chat_id="-1"
        )

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            result = asyncio.run(
                TelegramDispatcher(config=cfg).send_alert_event(event)
            )

        assert result["status"] == "RATE_LIMITED"
        assert result["http_code"] == 429
        assert "429" in result["detail"]

    # -----------------------------------------------------------------------
    # 15. HTTP 500 → HTTP_ERROR, no exception
    # -----------------------------------------------------------------------

    def test_real_mode_http_500_returns_http_error(self):
        event = _make_event()
        cfg   = _make_cfg(
            mode="REAL", enabled=True, bot_token="T", chat_id="-1"
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            result = asyncio.run(
                TelegramDispatcher(config=cfg).send_alert_event(event)
            )

        assert result["status"] == "HTTP_ERROR"
        assert result["http_code"] == 500
        assert not result.get("__exception_raised__")

    # -----------------------------------------------------------------------
    # 16. Network timeout → TIMEOUT, no exception
    # -----------------------------------------------------------------------

    def test_real_mode_timeout_returns_timeout_status(self):
        event = _make_event()
        cfg   = _make_cfg(
            mode="REAL", enabled=True, bot_token="T", chat_id="-1"
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            result = asyncio.run(
                TelegramDispatcher(config=cfg).send_alert_event(event)
            )

        assert result["status"] == "TIMEOUT"
        assert result["http_code"] == 0
        assert "timeout" in result["detail"].lower()

    # -----------------------------------------------------------------------
    # 17. Network error → NETWORK_ERROR, no exception
    # -----------------------------------------------------------------------

    def test_real_mode_network_error_returns_network_error_status(self):
        event = _make_event()
        cfg   = _make_cfg(
            mode="REAL", enabled=True, bot_token="T", chat_id="-1"
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patch("src.alerts.telegram_dispatcher.httpx.AsyncClient",
                   return_value=mock_client):
            result = asyncio.run(
                TelegramDispatcher(config=cfg).send_alert_event(event)
            )

        assert result["status"] == "NETWORK_ERROR"
        assert result["http_code"] == 0

    # -----------------------------------------------------------------------
    # 18. message_text present in all non-skip return dicts
    # -----------------------------------------------------------------------

    def test_test_mode_result_has_message_text(self):
        event  = _make_event()
        result = asyncio.run(
            TelegramDispatcher(config=_make_cfg()).send_alert_event(event)
        )
        assert isinstance(result["message_text"], str)
        assert len(result["message_text"]) > 0

    # -----------------------------------------------------------------------
    # 19. Return dict always has required keys
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("event_emitted,mode,enabled", [
        (False,  "TEST", True),
        (True,   "TEST", True),
        (True,   "TEST", False),
    ])
    def test_result_always_has_required_keys(self, event_emitted, mode, enabled):
        event  = _make_event(event_emitted=event_emitted)
        cfg    = _make_cfg(mode=mode, enabled=enabled)
        result = asyncio.run(
            TelegramDispatcher(config=cfg).send_alert_event(event)
        )
        for key in _REQUIRED_RESULT_KEYS:
            assert key in result, f"Missing key '{key}' in dispatcher result"

    # -----------------------------------------------------------------------
    # 20. SHAP drivers forwarded through dispatcher to message_text
    # -----------------------------------------------------------------------

    def test_shap_drivers_forwarded_to_message(self):
        event  = _make_event()
        result = asyncio.run(
            TelegramDispatcher(config=_make_cfg()).send_alert_event(
                event,
                shap_drivers=_SHAP,
                ndvi=0.312,
                sar_soil_moisture=0.554,
                rainfall_3day_mm=98.5,
            )
        )
        msg = result["message_text"]
        assert "slope_degrees" in msg
        assert "+34%" in msg
        assert "NDVI" in msg
        assert "0.312" in msg
        assert "98.5" in msg
