# tests/test_telegram_alert_policy.py
"""
Phase 8.1 Ext – Telegram Alert Policy unit tests.

These tests verify that the extended AlertPolicyEngine correctly evaluates
Telegram gating rules and populates the new Telegram fields on the returned
AlertDecision.
"""

from __future__ import annotations

import os
import datetime
import yaml
import pytest

import sys
import os

# Ensure the project root is on the import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts.alert_policy import AlertPolicyEngine, AlertDecision, _load_policy

# ---------------------------------------------------------------------------
# Helper to write a temporary telegram policy file
# ---------------------------------------------------------------------------
_BASE_TELEGRAM_POLICY = {
    "enabled": True,
    "minimum_risk_level": "HIGH",
    "bot_token_env_var": "TELEGRAM_BOT_TOKEN",
    "default_chat_id_env_var": "TELEGRAM_CHAT_ID",
    "max_staleness_hours": 24,
    "allow_stale_alerts": False,
    "risk_alert_mapping": {
        "LOW": "NO_ALERT",
        "MODERATE": "NO_ALERT",
        "HIGH": "TELEGRAM_WARNING",
        "CRITICAL": "TELEGRAM_CRITICAL",
    },
    "escalation_enabled": True,
    "recovery_enabled": True,
    "cooldown_minutes": 30,
}


def _write_telegram_policy(tmp_path, overrides: dict | None = None) -> str:
    """Write a telegram_alert_policy.yaml to *tmp_path* and return its path."""
    policy = {**_BASE_TELEGRAM_POLICY, **(overrides or {})}
    f = tmp_path / "telegram_alert_policy.yaml"
    f.write_text(yaml.dump(policy), encoding="utf-8")
    # clear the lru cache so the new file is read
    from src.alerts.alert_policy import _load_telegram_policy
    _load_telegram_policy.cache_clear()
    return str(f)


def _make_engine(tmp_path, telegram_overrides=None, policy_overrides=None):
    """Construct an AlertPolicyEngine using temporary config files.

    *telegram_overrides* – dict to merge into the base telegram policy.
    *policy_overrides*     – dict to merge into the generic alert policy (optional).
    """
    tg_path = _write_telegram_policy(tmp_path, telegram_overrides)
    # Write a minimal alert_policy.yaml required by AlertPolicyEngine
    base_policy = {
        "max_staleness_hours": 24,
        "require_valid_dynamic_data": True,
        "active_model_version": "v2",
        "risk_alert_mapping": {
            "LOW": "NONE",
            "MODERATE": "MONITORING",
            "HIGH": "WARNING",
            "CRITICAL": "IMMEDIATE",
        },
        "channels": {
            "WARNING": ["email"],
            "IMMEDIATE": ["email"],
        },
        "cooldown_minutes": 30,
        "targets": {},
    }
    policy_content = {**base_policy, **(policy_overrides or {})}
    policy_file = tmp_path / "alert_policy.yaml"
    policy_file.write_text(yaml.dump(policy_content), encoding="utf-8")
    # Ensure any cached load is cleared
    from src.alerts.alert_policy import _load_policy
    _load_policy.cache_clear()
    engine = AlertPolicyEngine(policy_path=str(policy_file))
    # Inject the telegram policy path attribute (private, but used internally)
    engine._telegram_policy_path = tg_path
    return engine


def _fresh_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _rr(
    *,
    risk_level: str,
    probability: float,
    status: str = "success",
    data_quality: str = "VALID",
    stale: bool = False,
    model_version: str = "v2",
    data_timestamp: str | None = None,
    target_id: str | None = None,
) -> dict:
    return {
        "status": status,
        "risk_level": risk_level,
        "probability": probability,
        "data_quality": data_quality,
        "stale": stale,
        "model_version": model_version,
        "data_timestamp": data_timestamp or _fresh_ts(),
        **({"target_id": target_id} if target_id else {}),
    }

# ---------------------------------------------------------------------------
# 1. LOW / MODERATE risk – Telegram should be NO_ALERT and disabled
# ---------------------------------------------------------------------------
class TestLowModerateRisk:
    def test_low_risk_telegram_no_alert(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="LOW", probability=0.15)
        dec: AlertDecision = engine.evaluate_alert(rr, target_config={})
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"
        assert dec.telegram_chat_id is None

    def test_moderate_risk_telegram_no_alert(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="MODERATE", probability=0.40)
        dec = engine.evaluate_alert(rr, target_config={})
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"

# ---------------------------------------------------------------------------
# 2. HIGH risk – Telegram warning
# ---------------------------------------------------------------------------
class TestHighRisk:
    def test_high_risk_triggers_telegram_warning(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.68)
        dec = engine.evaluate_alert(rr, target_config={"telegram_chat_id": "12345"})
        assert dec.telegram_enabled is True
        assert dec.telegram_alert_level == "TELEGRAM_WARNING"
        assert dec.telegram_chat_id == "12345"

# ---------------------------------------------------------------------------
# 3. CRITICAL risk – Telegram critical
# ---------------------------------------------------------------------------
class TestCriticalRisk:
    def test_critical_risk_triggers_telegram_critical(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.85)
        dec = engine.evaluate_alert(rr, target_config={"telegram_chat_id": "99999"})
        assert dec.telegram_enabled is True
        assert dec.telegram_alert_level == "TELEGRAM_CRITICAL"
        assert dec.telegram_chat_id == "99999"

# ---------------------------------------------------------------------------
# 4. Stale data – Telegram suppressed
#    NOTE: When `stale=True` is pre-flagged in the RiskResponse the primary
#    engine GATE 3 fires first (ALERT_SUPPRESSED). Telegram gating is a
#    sub-pass that only runs after all primary gates pass. Therefore the
#    reason field carries the primary suppression message.
# ---------------------------------------------------------------------------
class TestStaleData:
    def test_stale_data_suppresses_telegram(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70, stale=True)
        dec = engine.evaluate_alert(rr, target_config={"telegram_chat_id": "123"})
        # Primary gate fires first — alert_triggered is False
        assert dec.alert_triggered is False
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"
        # Primary GATE 3 sets the reason — includes 'stale' in message
        assert "stale" in dec.reason.lower()

# ---------------------------------------------------------------------------
# 5. Invalid data quality – Telegram suppressed
#    NOTE: INVALID quality is caught by primary engine GATE 2 before Telegram
#    gating. The reason message is set by the primary gate (ALERT_SUPPRESSED).
# ---------------------------------------------------------------------------
class TestInvalidDataQuality:
    def test_invalid_data_quality_suppresses_telegram(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70, data_quality="INVALID")
        dec = engine.evaluate_alert(rr, target_config={"telegram_chat_id": "123"})
        # Primary gate fires first — alert_triggered is False
        assert dec.alert_triggered is False
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"
        # Primary GATE 2 sets the reason — includes 'INVALID' in message
        assert "INVALID" in dec.reason

# ---------------------------------------------------------------------------
# 6. Disabled Telegram policy
# ---------------------------------------------------------------------------
class TestPolicyDisabled:
    def test_telegram_disabled_via_policy(self, tmp_path):
        engine = _make_engine(tmp_path, telegram_overrides={"enabled": False})
        rr = _rr(risk_level="HIGH", probability=0.70)
        dec = engine.evaluate_alert(rr, target_config={"telegram_chat_id": "123"})
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"
        assert "Telegram alerts disabled" in dec.reason

# ---------------------------------------------------------------------------
# 7. Missing chat ID – Telegram suppressed
# ---------------------------------------------------------------------------
class TestMissingChatId:
    def test_missing_chat_id_suppresses_telegram(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70)
        # No telegram_chat_id provided and no env var set
        dec = engine.evaluate_alert(rr, target_config={})
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"
        assert "Missing Telegram chat ID" in dec.reason

# ---------------------------------------------------------------------------
# 8. Per‑target telegram_notifications_enabled flag
# ---------------------------------------------------------------------------
class TestTargetTelegramFlag:
    def test_target_disables_telegram(self, tmp_path):
        engine = _make_engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70)
        dec = engine.evaluate_alert(rr, target_config={
            "telegram_chat_id": "123",
            "telegram_notifications_enabled": False,
        })
        assert dec.telegram_enabled is False
        assert dec.telegram_alert_level == "NO_ALERT"
        assert "telegram_notifications_enabled=False" in dec.reason
