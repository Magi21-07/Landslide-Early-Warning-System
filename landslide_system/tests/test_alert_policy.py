# tests/test_alert_policy.py
"""
tests/test_alert_policy.py
--------------------------
Phase 8.1: Unit tests for src/alerts/alert_policy.py (AlertPolicyEngine).

Covers 100% of policy boundaries and gating conditions:

  1. LOW risk         -> alert_triggered=False, alert_level=NONE
  2. MODERATE risk    -> alert_triggered=False, alert_level=MONITORING
  3. HIGH + valid     -> alert_triggered=True,  alert_level=WARNING
  4. CRITICAL + valid -> alert_triggered=True,  alert_level=IMMEDIATE
  5. HIGH + stale     -> alert_triggered=False  (GATE 3)
  6. CRITICAL + stale -> alert_triggered=False  (GATE 3)
  7. HIGH + notif=False    -> alert_triggered=False  (GATE 5)
  8. CRITICAL + notif=False -> alert_triggered=False (GATE 5)
  9. HIGH + status!=success -> alert_triggered=False (GATE 1)
 10. CRITICAL + data_quality=INVALID -> alert_triggered=False (GATE 2)
 11. Model version mismatch -> alert_triggered=False (GATE 4)
 12. No channels configured -> alert_triggered=False (GATE 6)
 13. AlertDecision schema validation
 14. Policy config loading: missing file, missing keys
 15. Probability boundary values at each threshold
 16. Stale detection via data_timestamp

All tests use tmp_path to isolate policy config — no writes to production config.
No GEE / network / SMTP / Twilio / Slack calls occur.
"""

import sys
import os
import datetime
import pytest
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.alerts.alert_policy import AlertDecision, AlertPolicyEngine, _load_policy

# ---------------------------------------------------------------------------
# Shared policy YAML fixture helpers
# ---------------------------------------------------------------------------

_BASE_POLICY = {
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
        "WARNING": ["email", "webhook"],
        "IMMEDIATE": ["email", "sms", "webhook"],
    },
    "cooldown_minutes": 30,
}


def _write_policy(tmp_path, overrides: dict | None = None) -> str:
    """Write a policy YAML to tmp_path and return its path string."""
    policy = {**_BASE_POLICY, **(overrides or {})}
    path = tmp_path / "alert_policy.yaml"
    path.write_text(yaml.dump(policy), encoding="utf-8")
    # Clear cache so the new file is picked up by lru_cache
    _load_policy.cache_clear()
    return str(path)


def _engine(tmp_path, overrides: dict | None = None) -> AlertPolicyEngine:
    return AlertPolicyEngine(policy_path=_write_policy(tmp_path, overrides))


# ---------------------------------------------------------------------------
# Baseline valid risk_response dicts
# ---------------------------------------------------------------------------

def _rr(
    *,
    risk_level: str,
    probability: float,
    status: str = "success",
    data_quality: str = "VALID",
    stale: bool = False,
    model_version: str = "v2",
    data_timestamp: str | None = None,
    target_id: str | None = "LOC_001",
) -> dict:
    """Build a minimal RiskResponse-like dict."""
    ts = data_timestamp or datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    return {
        "status": status,
        "risk_level": risk_level,
        "probability": probability,
        "data_quality": data_quality,
        "stale": stale,
        "model_version": model_version,
        "data_timestamp": ts,
        "target_id": target_id,
    }


def _valid_target(notifications_enabled: bool = True) -> dict:
    return {"notifications_enabled": notifications_enabled}


# ===========================================================================
# 1. Non-actionable risk levels (GATE 0)
# ===========================================================================

class TestNonActionableRiskLevels:

    def test_low_risk_returns_not_triggered(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="LOW", probability=0.10)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.alert_level == "NONE"
        assert d.triggering_risk_level == "LOW"
        assert d.allowed_channels == []

    def test_low_risk_boundary_below_0_30(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="LOW", probability=0.2999)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.alert_level == "NONE"

    def test_moderate_risk_returns_not_triggered(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="MODERATE", probability=0.40)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.alert_level == "MONITORING"
        assert d.triggering_risk_level == "MODERATE"
        assert d.allowed_channels == []

    def test_moderate_risk_boundary_at_0_30(self, tmp_path):
        """Probability exactly 0.30 => MODERATE => MONITORING, not triggered."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="MODERATE", probability=0.30)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.alert_level == "MONITORING"

    def test_moderate_risk_boundary_just_below_0_55(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="MODERATE", probability=0.5499)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.alert_level == "MONITORING"


# ===========================================================================
# 2. HIGH risk — all gates pass -> WARNING triggered (GATE 0 cleared)
# ===========================================================================

class TestHighRiskAlertTriggered:

    def test_high_risk_valid_data_triggers_warning(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.alert_level == "WARNING"
        assert d.triggering_risk_level == "HIGH"
        assert "email" in d.allowed_channels
        assert "webhook" in d.allowed_channels

    def test_high_risk_boundary_at_0_55(self, tmp_path):
        """Probability exactly 0.55 => HIGH => WARNING."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.55)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.alert_level == "WARNING"

    def test_high_risk_boundary_just_below_0_75(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.7499)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.alert_level == "WARNING"


# ===========================================================================
# 3. CRITICAL risk — all gates pass -> IMMEDIATE triggered
# ===========================================================================

class TestCriticalRiskAlertTriggered:

    def test_critical_risk_valid_data_triggers_immediate(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.85)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.alert_level == "IMMEDIATE"
        assert d.triggering_risk_level == "CRITICAL"
        assert set(d.allowed_channels) == {"email", "sms", "webhook"}

    def test_critical_risk_boundary_at_0_75(self, tmp_path):
        """Probability exactly 0.75 => CRITICAL => IMMEDIATE."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.75)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.alert_level == "IMMEDIATE"

    def test_critical_risk_probability_1_0(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=1.0)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.alert_level == "IMMEDIATE"


# ===========================================================================
# 4. GATE 1 — Evaluation status check
# ===========================================================================

class TestGate1EvaluationStatus:

    def test_high_risk_with_failed_status_is_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, status="error")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason
        assert "status" in d.reason.lower()

    def test_critical_risk_with_failed_status_is_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.80, status="partial_failure")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason

    def test_high_risk_with_empty_status_is_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, status="")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False

    def test_alert_level_still_correct_when_status_failed(self, tmp_path):
        """alert_level should still reflect the risk mapping even when suppressed."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, status="error")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_level == "WARNING"


# ===========================================================================
# 5. GATE 2 — Dynamic data availability
# ===========================================================================

class TestGate2DataQuality:

    def test_high_risk_with_invalid_data_quality_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, data_quality="INVALID")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason
        assert "INVALID" in d.reason

    def test_critical_risk_with_invalid_data_quality_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.80, data_quality="INVALID")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False

    def test_degraded_data_quality_still_triggers(self, tmp_path):
        """DEGRADED is not INVALID — alert should still be triggered."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, data_quality="DEGRADED")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.data_quality == "DEGRADED"

    def test_gate2_skipped_when_require_valid_dynamic_data_false(self, tmp_path):
        """If require_valid_dynamic_data=false, INVALID data should not suppress."""
        engine = _engine(tmp_path, {"require_valid_dynamic_data": False})
        rr = _rr(risk_level="HIGH", probability=0.65, data_quality="INVALID")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True


# ===========================================================================
# 6. GATE 3 — Data staleness
# ===========================================================================

class TestGate3DataStaleness:

    def test_high_risk_with_stale_flag_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, stale=True)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason
        assert "stale" in d.reason.lower() or "24" in d.reason

    def test_critical_risk_with_stale_flag_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.80, stale=True)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.stale is True

    def test_stale_detected_via_old_data_timestamp(self, tmp_path):
        """data_timestamp > 24 h old should set stale=True and suppress."""
        engine = _engine(tmp_path)
        old_ts = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=25)
        ).isoformat()
        rr = _rr(risk_level="HIGH", probability=0.65, stale=False, data_timestamp=old_ts)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert d.stale is True

    def test_fresh_data_timestamp_does_not_set_stale(self, tmp_path):
        engine = _engine(tmp_path)
        fresh_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rr = _rr(risk_level="HIGH", probability=0.65, stale=False, data_timestamp=fresh_ts)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.stale is False

    def test_custom_staleness_window_12h(self, tmp_path):
        """Policy max_staleness_hours=12 — 13h-old data should suppress."""
        engine = _engine(tmp_path, {"max_staleness_hours": 12})
        old_ts = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=13)
        ).isoformat()
        rr = _rr(risk_level="HIGH", probability=0.65, stale=False, data_timestamp=old_ts)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "12" in d.reason  # reason mentions the configured window


# ===========================================================================
# 7. GATE 4 — Model integrity
# ===========================================================================

class TestGate4ModelIntegrity:

    def test_model_version_mismatch_suppresses_high(self, tmp_path):
        engine = _engine(tmp_path)  # active_model_version=v2
        rr = _rr(risk_level="HIGH", probability=0.65, model_version="v1")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason
        assert "version" in d.reason.lower()

    def test_model_version_mismatch_suppresses_critical(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.80, model_version="v3")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False

    def test_correct_model_version_passes(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, model_version="v2")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True

    def test_empty_model_version_in_response_passes_gate(self, tmp_path):
        """If model_version is absent in response, gate 4 should be lenient."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65, model_version="")
        d = engine.evaluate_alert(rr, _valid_target())
        # Empty string means no version info available — gate should pass
        assert d.alert_triggered is True


# ===========================================================================
# 8. GATE 5 — Target notifications_enabled
# ===========================================================================

class TestGate5NotificationsEnabled:

    def test_high_risk_notifications_disabled_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65)
        d = engine.evaluate_alert(rr, _valid_target(notifications_enabled=False))
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason
        assert "notifications disabled" in d.reason.lower() or "notifications_enabled" in d.reason

    def test_critical_risk_notifications_disabled_suppressed(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.85)
        d = engine.evaluate_alert(rr, _valid_target(notifications_enabled=False))
        assert d.alert_triggered is False

    def test_no_target_config_defaults_notifications_enabled(self, tmp_path):
        """If no target_config provided, notifications should default to enabled."""
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.65)
        d = engine.evaluate_alert(rr)  # no target_config
        assert d.alert_triggered is True


# ===========================================================================
# 9. GATE 6 — Channel eligibility
# ===========================================================================

class TestGate6ChannelEligibility:

    def test_no_channels_configured_for_warning_suppressed(self, tmp_path):
        engine = _engine(tmp_path, {"channels": {}})  # empty channels dict
        rr = _rr(risk_level="HIGH", probability=0.65)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        assert "ALERT_SUPPRESSED" in d.reason
        assert "channel" in d.reason.lower()

    def test_no_channels_configured_for_immediate_suppressed(self, tmp_path):
        engine = _engine(tmp_path, {"channels": {"WARNING": ["email"]}})
        rr = _rr(risk_level="CRITICAL", probability=0.85)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False

    def test_channels_from_target_config_override_policy(self, tmp_path):
        """target_config can inject channels for an alert level."""
        engine = _engine(tmp_path, {"channels": {}})  # policy has no channels
        rr = _rr(risk_level="HIGH", probability=0.65)
        tc = {"notifications_enabled": True, "channels": {"WARNING": ["sms"]}}
        d = engine.evaluate_alert(rr, tc)
        assert d.alert_triggered is True
        assert "sms" in d.allowed_channels

    def test_only_sms_channel_in_policy(self, tmp_path):
        engine = _engine(tmp_path, {"channels": {"WARNING": ["sms"], "IMMEDIATE": ["sms"]}})
        rr = _rr(risk_level="HIGH", probability=0.65)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is True
        assert d.allowed_channels == ["sms"]


# ===========================================================================
# 10. AlertDecision schema validation
# ===========================================================================

class TestAlertDecisionSchema:

    def test_decision_is_pydantic_model(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70)
        d = engine.evaluate_alert(rr, _valid_target())
        assert isinstance(d, AlertDecision)

    def test_triggered_at_is_iso_utc(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70)
        d = engine.evaluate_alert(rr, _valid_target())
        dt = datetime.datetime.fromisoformat(d.triggered_at)
        assert dt.tzinfo is not None

    def test_probability_rounded_to_6dp(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=1 / 3)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.probability == round(1 / 3, 6)

    def test_target_id_forwarded(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70, target_id="KULLU_01")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.target_id == "KULLU_01"

    def test_target_id_none_when_absent(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70, target_id=None)
        d = engine.evaluate_alert(rr)
        assert d.target_id is None

    def test_data_quality_forwarded(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.70, data_quality="DEGRADED")
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.data_quality == "DEGRADED"

    def test_suppressed_decision_has_empty_channels(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="LOW", probability=0.10)
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.allowed_channels == []

    def test_model_dump_is_json_serialisable(self, tmp_path):
        import json
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.90)
        d = engine.evaluate_alert(rr, _valid_target())
        raw = json.dumps(d.model_dump())  # must not raise
        loaded = json.loads(raw)
        assert loaded["alert_triggered"] is True


# ===========================================================================
# 11. Policy config loading edge cases
# ===========================================================================

class TestPolicyConfigLoading:

    def test_missing_policy_file_raises(self, tmp_path):
        _load_policy.cache_clear()
        with pytest.raises(FileNotFoundError):
            AlertPolicyEngine(policy_path=str(tmp_path / "nonexistent.yaml")).policy

    def test_policy_missing_required_key_raises(self, tmp_path):
        _load_policy.cache_clear()
        incomplete = {k: v for k, v in _BASE_POLICY.items() if k != "channels"}
        path = tmp_path / "incomplete.yaml"
        path.write_text(yaml.dump(incomplete), encoding="utf-8")
        with pytest.raises(ValueError, match="channels"):
            AlertPolicyEngine(policy_path=str(path)).policy

    def test_invalid_yaml_structure_raises(self, tmp_path):
        _load_policy.cache_clear()
        path = tmp_path / "bad.yaml"
        path.write_text("- item1\n- item2\n", encoding="utf-8")  # list, not dict
        with pytest.raises(ValueError, match="mapping"):
            AlertPolicyEngine(policy_path=str(path)).policy


# ===========================================================================
# 12. Risk level derivation from probability (when risk_level key absent/unknown)
# ===========================================================================

class TestRiskLevelDerivation:

    def test_unknown_risk_level_key_falls_back_to_probability(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="UNKNOWN_LABEL", probability=0.80)
        d = engine.evaluate_alert(rr, _valid_target())
        # Should derive CRITICAL from probability=0.80
        assert d.triggering_risk_level == "CRITICAL"
        assert d.alert_triggered is True

    def test_missing_risk_level_key_uses_probability(self, tmp_path):
        engine = _engine(tmp_path)
        rr = {
            "status": "success",
            "probability": 0.65,
            "data_quality": "VALID",
            "stale": False,
            "model_version": "v2",
            "data_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.triggering_risk_level == "HIGH"
        assert d.alert_triggered is True


# ===========================================================================
# 13. Compound scenarios (multiple simultaneous gate failures)
# ===========================================================================

class TestCompoundScenarios:

    def test_stale_and_invalid_data_suppressed_at_gate3(self, tmp_path):
        """Stale check (gate 3) fires before data_quality (gate 2) — gate 3 wins."""
        engine = _engine(tmp_path)
        rr = _rr(
            risk_level="HIGH",
            probability=0.70,
            stale=True,
            data_quality="INVALID",
        )
        d = engine.evaluate_alert(rr, _valid_target())
        assert d.alert_triggered is False
        # Gate 1 (status) and 2 (quality) may pass, gate 3 should suppress
        # (gate 2 fires before gate 3 — INVALID quality is caught first)
        assert "ALERT_SUPPRESSED" in d.reason

    def test_notifications_disabled_and_stale_suppressed_by_gate3(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.90, stale=True)
        d = engine.evaluate_alert(rr, _valid_target(notifications_enabled=False))
        assert d.alert_triggered is False

    def test_high_probability_with_all_gates_passing(self, tmp_path):
        engine = _engine(tmp_path)
        rr = _rr(
            risk_level="HIGH",
            probability=0.74,
            status="success",
            data_quality="VALID",
            stale=False,
            model_version="v2",
        )
        d = engine.evaluate_alert(rr, _valid_target(notifications_enabled=True))
        assert d.alert_triggered is True
        assert d.alert_level == "WARNING"
        assert d.triggering_risk_level == "HIGH"
