# tests/test_alert_history.py
"""
Phase 8.10 — Unit tests for Telegram Alert History Service & API Endpoint
"""

import pytest
import uuid
from fastapi.testclient import TestClient
from src.alerts.alert_history import AlertHistoryService, AlertHistoryRecord
from src.alerts.alert_evaluator import AlertEvent
from src.alerts.alert_policy import AlertDecision
from src.alerts.delivery_tracker import DeliveryRecord
from src.api.main import app as main_app

@pytest.fixture
def history_service():
    return AlertHistoryService()

@pytest.fixture
def sample_event():
    return AlertEvent(
        alert_id=str(uuid.uuid4()),
        target_id="target_999",
        event_emitted=True,
        event_type="INITIAL_TRIGGER",
        current_risk_level="HIGH",
        previous_risk_level="LOW",
        probability=0.85,
        trigger_reason="Test reason",
        triggered_at="2025-01-01T12:00:00Z",
        risk_evaluation_timestamp="2025-01-01T12:00:00Z",
        model_version="1.0",
        data_quality="VALID",
        stale=False,
        policy_decision=AlertDecision(
            alert_triggered=True,
            alert_level="HIGH",
            triggering_risk_level="HIGH",
            probability=0.85,
            reason="Test reason",
            data_quality="VALID",
            stale=False,
            allowed_channels=["telegram"],
            triggered_at="2025-01-01T12:00:00Z",
            target_id="target_999",
            telegram_enabled=True,
            telegram_chat_id="chat_1",
            telegram_alert_level="HIGH"
        )
    )

def test_record_and_retrieve_history(history_service, sample_event):
    # 3. Multiple Historical Events
    record1 = history_service.record_alert_event(sample_event)
    assert record1.target_id == "target_999"
    
    sample_event.alert_id = str(uuid.uuid4())
    sample_event.event_type = "ESCALATION"
    sample_event.current_risk_level = "CRITICAL"
    sample_event.triggered_at = "2025-01-01T13:00:00Z"
    
    delivery = DeliveryRecord(
        alert_id=sample_event.alert_id,
        target_id=sample_event.target_id,
        chat_id="chat_1",
        status="SENT",
        attempt_number=1,
        message_id="msg_1",
        started_at="2025-01-01T12:00:00Z",
        success=True
    )
    
    record2 = history_service.record_alert_event(sample_event, delivery)
    
    history = history_service.get_target_history("target_999")
    assert len(history) == 2
    # Reverse chronological (newest first)
    assert history[0].alert_type == "ESCALATION"
    assert history[0].telegram_delivery_status == "SENT"
    assert history[1].alert_type == "INITIAL_TRIGGER"
    assert history[1].telegram_delivery_status == "NOT_SENT"

def test_resolved_recovery_alerts(history_service, sample_event):
    # 4. Resolved/Recovery Alerts
    sample_event.event_type = "RECOVERY"
    sample_event.current_risk_level = "MODERATE"
    record = history_service.record_alert_event(sample_event)
    
    assert record.resolved_at == sample_event.triggered_at

def test_failed_delivery_tracking(history_service, sample_event):
    # 5. Failed Delivery Tracking
    delivery = DeliveryRecord(
        alert_id=sample_event.alert_id,
        target_id=sample_event.target_id,
        chat_id="chat_1",
        status="FAILED",
        attempt_number=3,
        error_code="RATE_LIMITED",
        error_message="Too many requests",
        started_at="2025-01-01T12:00:00Z",
        success=False
    )
    record = history_service.record_alert_event(sample_event, delivery)
    
    assert record.telegram_delivery_status == "FAILED"
    assert record.retry_count == 3
    assert record.error_code == "RATE_LIMITED"
    assert record.error_message == "Too many requests"

# API Integration Tests
client = TestClient(main_app)

def test_api_history_retrieval(history_service, sample_event):
    # Overwrite the global instance for the test
    from src.api.routers.alerts import alert_history_service
    # Seed it
    alert_history_service.record_alert_event(sample_event)
    
    # 1. History Retrieval
    from src.api.security import verify_api_key
    main_app.dependency_overrides[verify_api_key] = lambda: True
    
    response = client.get("/api/v1/alerts/history/target_999")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["target_id"] == "target_999"
    assert data[0]["severity"] == "HIGH"
    
    # 6. Token Security Check
    response_text = response.text.lower()
    assert "token" not in response_text
    assert "secret" not in response_text

def test_api_empty_history():
    # 2. Empty History Handling
    from src.api.security import verify_api_key
    main_app.dependency_overrides[verify_api_key] = lambda: True
    
    response = client.get("/api/v1/alerts/history/unknown_target_999")
    assert response.status_code == 200
    assert response.json() == []
    
    main_app.dependency_overrides.clear()
