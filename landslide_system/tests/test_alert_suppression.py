# tests/test_alert_suppression.py
"""
Phase 8.5 — Unit tests for AlertSuppressionEngine.
"""

from __future__ import annotations

import datetime
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts.alert_suppression import AlertSuppressionEngine, _generate_fingerprint
from src.alerts.alert_evaluator import AlertEvent
from src.alerts.alert_policy import AlertDecision
from src.alerts.telegram_config import TelegramConfig

def _mock_event(
    target_id="t1", 
    event_type="INITIAL_TRIGGER", 
    current_risk_level="HIGH", 
    alert_id="a1"
) -> AlertEvent:
    return AlertEvent(
        alert_id=alert_id,
        target_id=target_id,
        event_emitted=True,
        event_type=event_type,
        current_risk_level=current_risk_level,
        previous_risk_level=None,
        probability=0.8,
        trigger_reason="test",
        triggered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        model_version="v1",
        risk_evaluation_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        data_quality="VALID",
        stale=False,
        policy_decision=AlertDecision(
            alert_triggered=True,
            alert_level="WARNING",
            triggering_risk_level="HIGH",
            probability=0.8,
            reason="test",
            data_quality="VALID",
            stale=False,
            allowed_channels=[],
            triggered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            target_id=target_id,
            telegram_enabled=True,
            telegram_chat_id=None,
            telegram_alert_level="TELEGRAM_WARNING"
        )
    )

@pytest.fixture
def policy_path(tmp_path):
    p = tmp_path / "telegram_alert_policy.yaml"
    p.write_text("cooldown_minutes: 30")
    return p

@pytest.fixture
def config():
    return TelegramConfig(mode="TEST")

@pytest.fixture
def engine(config, policy_path):
    return AlertSuppressionEngine(config=config, policy_path=policy_path)

@patch("src.alerts.alert_suppression._now_utc")
def test_idempotency_duplicate_suppressed(mock_now, engine):
    base_time = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_now.return_value = base_time
    
    event = _mock_event(alert_id="a1")
    engine.record_dispatch("t1", "c1", event)
    
    # Within 60 seconds
    mock_now.return_value = base_time + datetime.timedelta(seconds=30)
    decision = engine.should_suppress_alert("t1", "c1", event)
    assert decision.suppressed is True
    assert decision.reason == "IDEMPOTENT_DUPLICATE"
    
@patch("src.alerts.alert_suppression._now_utc")
def test_cooldown_suppression_high_to_high(mock_now, engine):
    base_time = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_now.return_value = base_time
    
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine.record_dispatch("t1", "c1", event1)
    
    # Evaluate 15 mins later (cooldown is 30)
    mock_now.return_value = base_time + datetime.timedelta(minutes=15)
    event2 = _mock_event(alert_id="a2", event_type="PERSISTENT_UNCHANGED", current_risk_level="HIGH")
    decision = engine.should_suppress_alert("t1", "c1", event2)
    
    assert decision.suppressed is True
    assert decision.reason == "COOLDOWN_ACTIVE"
    assert decision.cooldown_expires_at is not None

@patch("src.alerts.alert_suppression._now_utc")
def test_cooldown_suppression_expires(mock_now, engine):
    base_time = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_now.return_value = base_time
    
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine.record_dispatch("t1", "c1", event1)
    
    # Evaluate 31 mins later (cooldown is 30)
    mock_now.return_value = base_time + datetime.timedelta(minutes=31)
    event2 = _mock_event(alert_id="a2", event_type="PERSISTENT_UNCHANGED", current_risk_level="HIGH")
    decision = engine.should_suppress_alert("t1", "c1", event2)
    
    assert decision.suppressed is False
    assert decision.reason == "NO_SUPPRESSION"

@patch("src.alerts.alert_suppression._now_utc")
def test_escalation_bypass(mock_now, engine):
    base_time = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_now.return_value = base_time
    
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine.record_dispatch("t1", "c1", event1)
    
    # Evaluate 5 mins later with ESCALATION
    mock_now.return_value = base_time + datetime.timedelta(minutes=5)
    event2 = _mock_event(alert_id="a2", event_type="ESCALATION", current_risk_level="CRITICAL")
    decision = engine.should_suppress_alert("t1", "c1", event2)
    
    assert decision.suppressed is False
    assert decision.reason == "ESCALATION_BYPASS"

@patch("src.alerts.alert_suppression._now_utc")
def test_recovery_handling(mock_now, engine):
    base_time = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_now.return_value = base_time
    
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="CRITICAL")
    engine.record_dispatch("t1", "c1", event1)
    
    mock_now.return_value = base_time + datetime.timedelta(minutes=5)
    event2 = _mock_event(alert_id="a2", event_type="RECOVERY", current_risk_level="MODERATE")
    decision = engine.should_suppress_alert("t1", "c1", event2)
    
    assert decision.suppressed is False
    assert decision.reason == "RECOVERY_ALLOWED"

@patch("src.alerts.alert_suppression._now_utc")
def test_restart_persistence(mock_now, config, policy_path, tmp_path):
    persist_path = tmp_path / "suppression.json"
    
    base_time = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_now.return_value = base_time
    
    engine1 = AlertSuppressionEngine(config=config, policy_path=policy_path, persistence_path=persist_path)
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine1.record_dispatch("t1", "c1", event1)
    
    # Restart
    engine2 = AlertSuppressionEngine(config=config, policy_path=policy_path, persistence_path=persist_path)
    
    # Cooldown still active
    mock_now.return_value = base_time + datetime.timedelta(minutes=10)
    event2 = _mock_event(alert_id="a2", event_type="PERSISTENT_UNCHANGED", current_risk_level="HIGH")
    decision = engine2.should_suppress_alert("t1", "c1", event2)
    
    assert decision.suppressed is True
    assert decision.reason == "COOLDOWN_ACTIVE"

def test_multi_target_isolation(engine):
    event1 = _mock_event(target_id="t1", event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine.record_dispatch("t1", "c1", event1)
    
    event2 = _mock_event(target_id="t2", event_type="INITIAL_TRIGGER", current_risk_level="HIGH", alert_id="a2")
    decision = engine.should_suppress_alert("t2", "c1", event2)
    
    assert decision.suppressed is False
    assert decision.reason == "NO_SUPPRESSION"

def test_multi_chat_isolation(engine):
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine.record_dispatch("t1", "c1", event1)
    
    event2 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH", alert_id="a2")
    decision = engine.should_suppress_alert("t1", "c2", event2)
    
    assert decision.suppressed is False
    assert decision.reason == "NO_SUPPRESSION"

def test_clear_suppression_history(engine):
    event1 = _mock_event(event_type="INITIAL_TRIGGER", current_risk_level="HIGH")
    engine.record_dispatch("t1", "c1", event1)
    
    engine.clear_suppression_history()
    
    event2 = _mock_event(event_type="PERSISTENT_UNCHANGED", current_risk_level="HIGH", alert_id="a2")
    decision = engine.should_suppress_alert("t1", "c1", event2)
    
    assert decision.suppressed is False
