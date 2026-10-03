# tests/test_alert_evaluator.py
"""
tests/test_alert_evaluator.py
------------------------------
Phase 8.2: Unit tests for AlertEvaluator + TargetStateStore.

All tests use isolated instances of AlertEvaluator with a fresh
TargetStateStore per test (via pytest fixture) to guarantee full
determinism.  A tmp_path-backed alert_policy.yaml is provided for
every engine instance — no production config files are read.

Coverage
--------
1.  First-time HIGH event              → INITIAL_TRIGGER, event_emitted=True
2.  HIGH persistence                   → PERSISTENT_UNCHANGED, event_emitted=False
3.  Escalation HIGH → CRITICAL         → ESCALATION, event_emitted=True
4.  De-escalation CRITICAL → HIGH      → DE_ESCALATION, event_emitted=True
5.  Recovery HIGH → MODERATE           → RECOVERY, event_emitted=True
6.  Recovery CRITICAL → LOW            → RECOVERY, event_emitted=True
7.  Stale data (policy gate 3)         → SUPPRESSED, event_emitted=False
8.  Failed evaluation status           → SUPPRESSED, event_emitted=False
9.  LOW risk (no prior state)          → SUPPRESSED, event_emitted=False
10. MODERATE risk (no prior state)     → SUPPRESSED, event_emitted=False
11. First-time CRITICAL event          → INITIAL_TRIGGER, event_emitted=True
12. CRITICAL → CRITICAL persistence    → PERSISTENT_UNCHANGED, event_emitted=False
13. MODERATE → HIGH (safe → actionable)→ INITIAL_TRIGGER, event_emitted=True
14. State store not updated on failure
15. State store updated on success
16. AlertEvent schema (all required fields present, types correct)
17. Notifications disabled             → SUPPRESSED, event_emitted=False
18. Previous LOW → current CRITICAL    → INITIAL_TRIGGER, event_emitted=True
19. De-escalation CRITICAL → MODERATE  → RECOVERY, event_emitted=True
"""

from __future__ import annotations

import datetime
import sys
import os
import pytest
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.alerts.alert_policy import AlertPolicyEngine, _load_policy
from src.alerts.alert_evaluator import AlertEvaluator, AlertEvent, _classify_transition
from src.alerts.state_store import TargetStateStore


# ===========================================================================
# Shared helpers & fixtures
# ===========================================================================

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
    """Write alert_policy.yaml to tmp_path and return its string path."""
    pol = {**_BASE_POLICY, **(overrides or {})}
    path = tmp_path / "alert_policy.yaml"
    path.write_text(yaml.dump(pol), encoding="utf-8")
    _load_policy.cache_clear()
    return str(path)


def _make_evaluator(
    tmp_path,
    policy_overrides: dict | None = None,
    state_store: TargetStateStore | None = None,
) -> AlertEvaluator:
    """Create a fully isolated AlertEvaluator backed by a tmp policy file."""
    pp = _write_policy(tmp_path, policy_overrides)
    engine = AlertPolicyEngine(policy_path=pp)
    # Use `is not None` guard: an empty TargetStateStore is falsy via __len__
    resolved_store = state_store if state_store is not None else TargetStateStore()
    return AlertEvaluator(policy_engine=engine, state_store=resolved_store)


def _fresh_ts() -> str:
    """Return a fresh UTC ISO timestamp (now)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _stale_ts(hours: int = 25) -> str:
    """Return a UTC ISO timestamp that is `hours` hours in the past."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=hours)
    ).isoformat()


def _rr(
    *,
    risk_level:     str,
    probability:    float,
    status:         str = "success",
    data_quality:   str = "VALID",
    stale:          bool = False,
    model_version:  str = "v2",
    data_timestamp: str | None = None,
    target_id:      str | None = None,
) -> dict:
    """Build a minimal risk-response dict."""
    return {
        "status":         status,
        "risk_level":     risk_level,
        "probability":    probability,
        "data_quality":   data_quality,
        "stale":          stale,
        "model_version":  model_version,
        "data_timestamp": data_timestamp or _fresh_ts(),
        **({"target_id": target_id} if target_id else {}),
    }


def _valid_tc(notifications_enabled: bool = True) -> dict:
    return {"notifications_enabled": notifications_enabled}


# ===========================================================================
# 1. INITIAL_TRIGGER — first-time HIGH
# ===========================================================================

class TestInitialTriggerHigh:

    def test_first_high_emits_initial_trigger(self, tmp_path):
        ev = _make_evaluator(tmp_path)
        rr = _rr(risk_level="HIGH", probability=0.68)
        event = ev.evaluate_target_risk("LOC_001", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "INITIAL_TRIGGER"
        assert event.previous_risk_level is None
        assert event.current_risk_level == "HIGH"

    def test_first_critical_emits_initial_trigger(self, tmp_path):
        ev = _make_evaluator(tmp_path)
        rr = _rr(risk_level="CRITICAL", probability=0.82)
        event = ev.evaluate_target_risk("LOC_A", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "INITIAL_TRIGGER"
        assert event.current_risk_level == "CRITICAL"

    def test_low_then_high_emits_initial_trigger(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)

        # Seed store with LOW state
        store.update_state("LOC_X", "LOW", _fresh_ts(), 0.15)

        rr    = _rr(risk_level="HIGH", probability=0.65)
        event = ev.evaluate_target_risk("LOC_X", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "INITIAL_TRIGGER"
        assert event.previous_risk_level == "LOW"

    def test_moderate_then_critical_emits_initial_trigger(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_Y", "MODERATE", _fresh_ts(), 0.45)

        rr    = _rr(risk_level="CRITICAL", probability=0.90)
        event = ev.evaluate_target_risk("LOC_Y", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "INITIAL_TRIGGER"


# ===========================================================================
# 2. PERSISTENT_UNCHANGED — HIGH → HIGH
# ===========================================================================

class TestPersistentUnchanged:

    def test_high_to_high_suppresses_duplicate(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_001", "HIGH", _fresh_ts(), 0.65)

        rr    = _rr(risk_level="HIGH", probability=0.68)
        event = ev.evaluate_target_risk("LOC_001", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "PERSISTENT_UNCHANGED"
        assert "PERSISTENT_STATE_UNCHANGED" in event.trigger_reason

    def test_critical_to_critical_suppresses_duplicate(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_002", "CRITICAL", _fresh_ts(), 0.80)

        rr    = _rr(risk_level="CRITICAL", probability=0.85)
        event = ev.evaluate_target_risk("LOC_002", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "PERSISTENT_UNCHANGED"

    def test_low_to_low_is_suppressed(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_003", "LOW", _fresh_ts(), 0.10)

        rr    = _rr(risk_level="LOW", probability=0.12)
        event = ev.evaluate_target_risk("LOC_003", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"

    def test_moderate_to_moderate_is_suppressed(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_004", "MODERATE", _fresh_ts(), 0.40)

        rr    = _rr(risk_level="MODERATE", probability=0.42)
        event = ev.evaluate_target_risk("LOC_004", rr, _valid_tc())

        assert event.event_emitted is False


# ===========================================================================
# 3. ESCALATION — HIGH → CRITICAL
# ===========================================================================

class TestEscalation:

    def test_high_to_critical_escalation(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_005", "HIGH", _fresh_ts(), 0.67)

        rr    = _rr(risk_level="CRITICAL", probability=0.83)
        event = ev.evaluate_target_risk("LOC_005", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "ESCALATION"
        assert event.previous_risk_level == "HIGH"
        assert event.current_risk_level == "CRITICAL"

    def test_escalation_allowed_channels_populated(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_006", "HIGH", _fresh_ts(), 0.70)

        rr    = _rr(risk_level="CRITICAL", probability=0.88)
        event = ev.evaluate_target_risk("LOC_006", rr, _valid_tc())

        assert event.event_emitted is True
        assert "sms" in event.policy_decision.allowed_channels

    def test_escalation_suppressed_when_policy_gates_fail(self, tmp_path):
        """Escalation must still pass policy gates."""
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_007", "HIGH", _fresh_ts(), 0.70)

        # Stale data fails gate 3
        rr    = _rr(risk_level="CRITICAL", probability=0.80, stale=True)
        event = ev.evaluate_target_risk("LOC_007", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"


# ===========================================================================
# 4. DE_ESCALATION — CRITICAL → HIGH
# ===========================================================================

class TestDeEscalation:

    def test_critical_to_high_de_escalation(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_010", "CRITICAL", _fresh_ts(), 0.82)

        rr    = _rr(risk_level="HIGH", probability=0.65)
        event = ev.evaluate_target_risk("LOC_010", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "DE_ESCALATION"
        assert event.previous_risk_level == "CRITICAL"
        assert event.current_risk_level == "HIGH"

    def test_de_escalation_trigger_reason_mentions_transition(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_011", "CRITICAL", _fresh_ts(), 0.81)

        rr    = _rr(risk_level="HIGH", probability=0.66)
        event = ev.evaluate_target_risk("LOC_011", rr, _valid_tc())

        assert "DE_ESCALATION" in event.trigger_reason or "CRITICAL" in event.trigger_reason


# ===========================================================================
# 5 & 6. RECOVERY
# ===========================================================================

class TestRecovery:

    def test_high_to_moderate_recovery(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_020", "HIGH", _fresh_ts(), 0.65)

        rr    = _rr(risk_level="MODERATE", probability=0.42)
        event = ev.evaluate_target_risk("LOC_020", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "RECOVERY"
        assert event.previous_risk_level == "HIGH"

    def test_high_to_low_recovery(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_021", "HIGH", _fresh_ts(), 0.68)

        rr    = _rr(risk_level="LOW", probability=0.12)
        event = ev.evaluate_target_risk("LOC_021", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "RECOVERY"

    def test_critical_to_low_recovery(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_022", "CRITICAL", _fresh_ts(), 0.85)

        rr    = _rr(risk_level="LOW", probability=0.10)
        event = ev.evaluate_target_risk("LOC_022", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "RECOVERY"

    def test_critical_to_moderate_recovery(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_023", "CRITICAL", _fresh_ts(), 0.88)

        rr    = _rr(risk_level="MODERATE", probability=0.44)
        event = ev.evaluate_target_risk("LOC_023", rr, _valid_tc())

        assert event.event_emitted is True
        assert event.event_type == "RECOVERY"


# ===========================================================================
# 7. Stale data — policy gate 3 suppresses INITIAL_TRIGGER / ESCALATION
# ===========================================================================

class TestStaleSuppression:

    def test_initial_trigger_suppressed_when_stale_flag_set(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70, stale=True)
        event = ev.evaluate_target_risk("LOC_030", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"
        assert event.stale is True

    def test_initial_trigger_suppressed_when_data_timestamp_old(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(
            risk_level="HIGH", probability=0.70,
            stale=False, data_timestamp=_stale_ts(25),
        )
        event = ev.evaluate_target_risk("LOC_031", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"

    def test_escalation_suppressed_when_stale(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_032", "HIGH", _fresh_ts(), 0.70)

        rr    = _rr(risk_level="CRITICAL", probability=0.85, stale=True)
        event = ev.evaluate_target_risk("LOC_032", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"


# ===========================================================================
# 8. Failed evaluation status — policy gate 1
# ===========================================================================

class TestFailedEvaluationStatus:

    def test_initial_trigger_suppressed_when_status_error(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70, status="error")
        event = ev.evaluate_target_risk("LOC_040", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"

    def test_escalation_suppressed_when_status_error(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_041", "HIGH", _fresh_ts(), 0.70)

        rr    = _rr(risk_level="CRITICAL", probability=0.82, status="error")
        event = ev.evaluate_target_risk("LOC_041", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"

    def test_state_not_updated_when_status_fails(self, tmp_path):
        """Failed evaluations must NOT poison the state store."""
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)

        rr    = _rr(risk_level="HIGH", probability=0.70, status="error")
        ev.evaluate_target_risk("LOC_042", rr, _valid_tc())

        # State must remain None — no entry for a failed evaluation
        assert store.get_last_state("LOC_042") is None

    def test_state_updated_when_status_success(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)

        rr    = _rr(risk_level="HIGH", probability=0.68, status="success")
        ev.evaluate_target_risk("LOC_043", rr, _valid_tc())

        state = store.get_last_state("LOC_043")
        assert state is not None
        assert state["risk_level"] == "HIGH"
        assert state["probability"] == 0.68


# ===========================================================================
# 9 & 10. Non-actionable levels with no prior state
# ===========================================================================

class TestNonActionableLevels:

    def test_low_risk_no_prior_state_not_emitted(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="LOW", probability=0.12)
        event = ev.evaluate_target_risk("LOC_050", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"
        assert event.previous_risk_level is None

    def test_moderate_risk_no_prior_state_not_emitted(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="MODERATE", probability=0.42)
        event = ev.evaluate_target_risk("LOC_051", rr, _valid_tc())

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"


# ===========================================================================
# 11. Notifications disabled
# ===========================================================================

class TestNotificationsDisabled:

    def test_initial_trigger_suppressed_when_notifications_disabled(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70)
        event = ev.evaluate_target_risk(
            "LOC_060", rr, _valid_tc(notifications_enabled=False)
        )

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"

    def test_escalation_suppressed_when_notifications_disabled(self, tmp_path):
        store = TargetStateStore()
        ev    = _make_evaluator(tmp_path, state_store=store)
        store.update_state("LOC_061", "HIGH", _fresh_ts(), 0.70)

        rr    = _rr(risk_level="CRITICAL", probability=0.85)
        event = ev.evaluate_target_risk(
            "LOC_061", rr, _valid_tc(notifications_enabled=False)
        )

        assert event.event_emitted is False
        assert event.event_type == "SUPPRESSED"


# ===========================================================================
# 12. AlertEvent schema integrity
# ===========================================================================

class TestAlertEventSchema:

    def test_alert_event_is_pydantic_model(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70)
        event = ev.evaluate_target_risk("LOC_070", rr, _valid_tc())
        assert isinstance(event, AlertEvent)

    def test_alert_id_is_non_empty_uuid(self, tmp_path):
        import re
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70)
        event = ev.evaluate_target_risk("LOC_071", rr, _valid_tc())
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        )
        assert uuid_pattern.match(event.alert_id), f"Not a UUID v4: {event.alert_id}"

    def test_alert_ids_are_unique_per_call(self, tmp_path):
        ev  = _make_evaluator(tmp_path)
        rr  = _rr(risk_level="HIGH", probability=0.70)
        e1  = ev.evaluate_target_risk("LOC_072", rr, _valid_tc())
        e2  = ev.evaluate_target_risk("LOC_073", rr, _valid_tc())
        assert e1.alert_id != e2.alert_id

    def test_triggered_at_is_utc_iso(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70)
        event = ev.evaluate_target_risk("LOC_074", rr, _valid_tc())
        dt    = datetime.datetime.fromisoformat(event.triggered_at)
        assert dt.tzinfo is not None

    def test_probability_rounded(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=1 / 3)
        event = ev.evaluate_target_risk("LOC_075", rr, _valid_tc())
        assert event.probability == round(1 / 3, 6)

    def test_policy_decision_embedded(self, tmp_path):
        from src.alerts.alert_policy import AlertDecision
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70)
        event = ev.evaluate_target_risk("LOC_076", rr, _valid_tc())
        assert isinstance(event.policy_decision, AlertDecision)

    def test_model_dump_json_serialisable(self, tmp_path):
        import json
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="CRITICAL", probability=0.90)
        event = ev.evaluate_target_risk("LOC_077", rr, _valid_tc())
        raw   = json.dumps(event.model_dump())  # must not raise
        loaded = json.loads(raw)
        assert loaded["event_emitted"] is True

    def test_all_required_fields_present(self, tmp_path):
        ev    = _make_evaluator(tmp_path)
        rr    = _rr(risk_level="HIGH", probability=0.70)
        event = ev.evaluate_target_risk("LOC_078", rr, _valid_tc())
        d     = event.model_dump()
        required_keys = {
            "alert_id", "target_id", "event_emitted", "event_type",
            "previous_risk_level", "current_risk_level", "probability",
            "trigger_reason", "triggered_at", "model_version",
            "risk_evaluation_timestamp", "data_quality", "stale",
            "policy_decision",
        }
        for key in required_keys:
            assert key in d, f"Missing key in AlertEvent: {key}"


# ===========================================================================
# 13. TargetStateStore unit tests
# ===========================================================================

class TestTargetStateStore:

    def test_get_last_state_returns_none_when_empty(self):
        store = TargetStateStore()
        assert store.get_last_state("UNKNOWN") is None

    def test_update_then_get(self):
        store = TargetStateStore()
        ts    = _fresh_ts()
        store.update_state("LOC_S1", "HIGH", ts, 0.70)
        state = store.get_last_state("LOC_S1")
        assert state is not None
        assert state["risk_level"]  == "HIGH"
        assert state["probability"] == 0.70

    def test_update_overwrites_previous(self):
        store = TargetStateStore()
        store.update_state("LOC_S2", "HIGH",     _fresh_ts(), 0.65)
        store.update_state("LOC_S2", "CRITICAL", _fresh_ts(), 0.82)
        state = store.get_last_state("LOC_S2")
        assert state["risk_level"] == "CRITICAL"

    def test_clear_specific_target(self):
        store = TargetStateStore()
        store.update_state("LOC_S3", "HIGH", _fresh_ts(), 0.65)
        store.update_state("LOC_S4", "HIGH", _fresh_ts(), 0.66)
        store.clear_state("LOC_S3")
        assert store.get_last_state("LOC_S3") is None
        assert store.get_last_state("LOC_S4") is not None

    def test_clear_all_targets(self):
        store = TargetStateStore()
        store.update_state("LOC_S5", "HIGH",     _fresh_ts(), 0.65)
        store.update_state("LOC_S6", "CRITICAL", _fresh_ts(), 0.82)
        store.clear_state()
        assert store.get_last_state("LOC_S5") is None
        assert store.get_last_state("LOC_S6") is None

    def test_get_returns_copy_not_reference(self):
        """Mutating the returned dict must not affect the store."""
        store = TargetStateStore()
        store.update_state("LOC_S7", "HIGH", _fresh_ts(), 0.70)
        state = store.get_last_state("LOC_S7")
        state["risk_level"] = "MUTATED"
        assert store.get_last_state("LOC_S7")["risk_level"] == "HIGH"

    def test_len_tracks_target_count(self):
        store = TargetStateStore()
        assert len(store) == 0
        store.update_state("A", "HIGH", _fresh_ts(), 0.65)
        store.update_state("B", "LOW",  _fresh_ts(), 0.10)
        assert len(store) == 2
        store.clear_state("A")
        assert len(store) == 1


# ===========================================================================
# 14. _classify_transition unit tests (pure function)
# ===========================================================================

class TestClassifyTransition:

    @pytest.mark.parametrize("prev, curr, expected", [
        # No prior state
        (None, "HIGH",     "INITIAL_TRIGGER"),
        (None, "CRITICAL", "INITIAL_TRIGGER"),
        (None, "LOW",      "UNCHANGED_SAFE"),
        (None, "MODERATE", "UNCHANGED_SAFE"),
        # Escalation
        ("HIGH",     "CRITICAL", "ESCALATION"),
        # De-escalation
        ("CRITICAL", "HIGH",     "DE_ESCALATION"),
        # Recovery
        ("HIGH",     "MODERATE", "RECOVERY"),
        ("HIGH",     "LOW",      "RECOVERY"),
        ("CRITICAL", "MODERATE", "RECOVERY"),
        ("CRITICAL", "LOW",      "RECOVERY"),
        # Persistent
        ("HIGH",     "HIGH",     "PERSISTENT_UNCHANGED"),
        ("CRITICAL", "CRITICAL", "PERSISTENT_UNCHANGED"),
        ("LOW",      "LOW",      "UNCHANGED_SAFE"),
        ("MODERATE", "MODERATE", "UNCHANGED_SAFE"),
        # Safe → actionable
        ("LOW",      "HIGH",     "INITIAL_TRIGGER"),
        ("MODERATE", "CRITICAL", "INITIAL_TRIGGER"),
        ("LOW",      "CRITICAL", "INITIAL_TRIGGER"),
    ])
    def test_transitions(self, prev, curr, expected):
        result = _classify_transition(prev, curr)
        assert result == expected, (
            f"_classify_transition({prev!r}, {curr!r}) = {result!r}, "
            f"expected {expected!r}"
        )
