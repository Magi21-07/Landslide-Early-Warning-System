# tests/test_telegram_async_retry.py
"""
Phase 8.8 — Unit tests for AsyncTelegramDispatcher & DeliveryTracker
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch

from src.alerts.telegram_config import TelegramConfig
from src.alerts.delivery_tracker import DeliveryTracker
from src.alerts.telegram_async import AsyncTelegramDispatcher
from src.alerts.alert_evaluator import AlertEvent
from src.alerts.alert_policy import AlertDecision
from fastapi.testclient import TestClient
from src.api.main import app

@pytest.fixture
def base_event():
    return AlertEvent(
        alert_id="test_alert_123",
        target_id="target_123",
        event_emitted=True,
        event_type="INITIAL_TRIGGER",
        current_risk_level="HIGH",
        previous_risk_level=None,
        probability=0.85,
        trigger_reason="test",
        triggered_at="2025-01-01T12:00:00Z",
        risk_evaluation_timestamp="2025-01-01T12:00:00Z",
        model_version="v1.0",
        data_quality="VALID",
        stale=False,
        policy_decision=AlertDecision(
            alert_triggered=True,
            alert_level="WARNING",
            triggering_risk_level="HIGH",
            probability=0.85,
            reason="test",
            data_quality="VALID",
            stale=False,
            allowed_channels=["telegram"],
            triggered_at="2025-01-01T12:00:00Z",
            target_id="target_123",
            telegram_enabled=True,
            telegram_chat_id="chat_123",
            telegram_alert_level="WARNING"
        )
    )

@pytest.fixture
def config():
    return TelegramConfig(mode="REAL", enabled=True, bot_token="secret", chat_id="chat_123")

@pytest.fixture
def tracker():
    return DeliveryTracker()

def test_transient_retry_success(config, tracker, base_event):
    provider = AsyncMock()
    # First fails with timeout, second succeeds
    provider.send_message.side_effect = [
        {"success": False, "error_code": "NETWORK_TIMEOUT", "error_message": "Timeout"},
        {"success": True, "message_id": "msg2", "error_code": None, "error_message": None}
    ]
    
    dispatcher = AsyncTelegramDispatcher(config, tracker, provider=provider)
    
    asyncio.run(dispatcher.dispatch_in_background(base_event, "chat_123", max_retries=3))
    
    history = tracker.get_delivery_history(getattr(base_event, "alert_id", "default"))
    assert len(history) == 2
    assert history[0].status == "RETRYING"
    assert history[0].attempt_number == 1
    assert history[1].status == "SUCCESS"
    assert history[1].attempt_number == 2

def test_max_retries_exceeded(config, tracker, base_event):
    provider = AsyncMock()
    provider.send_message.return_value = {"success": False, "error_code": "TELEGRAM_SERVER_ERROR", "error_message": "500 Error"}
    
    dispatcher = AsyncTelegramDispatcher(config, tracker, provider=provider)
    
    asyncio.run(dispatcher.dispatch_in_background(base_event, "chat_123", max_retries=3))
    
    history = tracker.get_delivery_history(getattr(base_event, "alert_id", "default"))
    assert len(history) == 3
    assert history[0].status == "RETRYING"
    assert history[1].status == "RETRYING"
    assert history[2].status == "FAILED"
    assert history[2].attempt_number == 3

def test_permanent_failure_early_exit(config, tracker, base_event):
    provider = AsyncMock()
    provider.send_message.return_value = {"success": False, "error_code": "BOT_PERMISSION_DENIED", "error_message": "403 Forbidden"}
    
    dispatcher = AsyncTelegramDispatcher(config, tracker, provider=provider)
    
    asyncio.run(dispatcher.dispatch_in_background(base_event, "chat_123", max_retries=3))
    
    history = tracker.get_delivery_history(getattr(base_event, "alert_id", "default"))
    assert len(history) == 1
    assert history[0].status == "FAILED"
    assert history[0].attempt_number == 1

def test_rate_limit_respect(config, tracker, base_event):
    provider = AsyncMock()
    provider.send_message.side_effect = [
        {"success": False, "error_code": "RATE_LIMITED", "error_message": "Retry-After: 1"},
        {"success": True, "message_id": "msg2"}
    ]
    
    dispatcher = AsyncTelegramDispatcher(config, tracker, provider=provider)
    
    start_time = time.monotonic()
    asyncio.run(dispatcher.dispatch_in_background(base_event, "chat_123", max_retries=3))
    elapsed = time.monotonic() - start_time
    
    assert elapsed >= 1.0  # Must have slept for at least 1 second
    history = tracker.get_delivery_history(getattr(base_event, "alert_id", "default"))
    assert len(history) == 2
    assert history[1].status == "SUCCESS"

def test_idempotency_check(config, tracker, base_event):
    provider = AsyncMock()
    provider.send_message.return_value = {"success": True, "message_id": "msg1"}
    
    dispatcher = AsyncTelegramDispatcher(config, tracker, provider=provider)
    
    asyncio.run(dispatcher.dispatch_in_background(base_event, "chat_123", max_retries=3))
    asyncio.run(dispatcher.dispatch_in_background(base_event, "chat_123", max_retries=3))
    
    assert provider.send_message.call_count == 1
    
    history = tracker.get_delivery_history(getattr(base_event, "alert_id", "default"))
    assert len(history) == 1

def test_non_blocking_verification():
    # Use TestClient to verify the endpoint doesn't block or error out when dispatch_alerts is true
    client = TestClient(app)
    
    from src.api.security import verify_api_key
    app.dependency_overrides[verify_api_key] = lambda: True
    
    response = client.post(
        "/api/v1/risk/evaluate?dispatch_alerts=true",
        json={"latitude": 31.1, "longitude": 77.1},
        headers={"X-API-Key": "test-api-key-123"}
    )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert "location_id" in data
