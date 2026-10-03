# tests/test_telegram_message.py
"""
Phase 8.6 - Unit tests for TelegramMessageBuilder
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts.telegram_message import TelegramMessageBuilder

def test_high_warning_template():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="HIGH",
        event_type="INITIAL_TRIGGER",
        probability=0.75,
        triggered_at="2025-01-01T12:00:00Z"
    )
    assert "HIGH LANDSLIDE WARNING" in msg
    assert "Elevated landslide risk detected" in msg

def test_critical_alert_template():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="CRITICAL",
        event_type="ESCALATION",
        probability=0.90,
        triggered_at="2025-01-01T12:00:00Z"
    )
    assert "CRITICAL LANDSLIDE EMERGENCY" in msg
    assert "Severe landslide risk condition detected" in msg

def test_recovery_template():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="MODERATE",
        event_type="RECOVERY",
        probability=0.30,
        triggered_at="2025-01-01T12:00:00Z"
    )
    assert "LANDSLIDE RISK RECOVERY / DE-ESCALATION" in msg
    assert "de-escalated to normal/safe baseline" in msg

def test_system_failure_template_data_quality():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="HIGH",
        event_type="INITIAL_TRIGGER",
        probability=0.75,
        triggered_at="2025-01-01T12:00:00Z",
        data_quality="INVALID"
    )
    assert "LEWS SYSTEM NOTICE / SENSOR DEGRADATION" in msg
    assert "Data quality or sensor staleness flag detected" in msg

def test_system_failure_template_stale():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="HIGH",
        event_type="INITIAL_TRIGGER",
        probability=0.75,
        triggered_at="2025-01-01T12:00:00Z",
        stale=True
    )
    assert "LEWS SYSTEM NOTICE / SENSOR DEGRADATION" in msg
    assert "Data quality or sensor staleness flag detected" in msg

def test_forbidden_phrasing_guardrail():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="CRITICAL",
        event_type="INITIAL_TRIGGER",
        probability=0.99,
        triggered_at="2025-01-01T12:00:00Z"
    )
    forbidden = ["definitely occur", "guaranteed", "disaster imminent", "will happen"]
    msg_lower = msg.lower()
    for phrase in forbidden:
        assert phrase not in msg_lower

def test_missing_data_fallback():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="HIGH",
        event_type="INITIAL_TRIGGER",
        probability=0.75,
        triggered_at="2025-01-01T12:00:00Z",
        shap_drivers=None,
        ndvi=None,
        sar_soil_moisture=None,
        rainfall_3day_mm=None
    )
    assert "*Rainfall 3-Day:*" not in msg
    assert "*NDVI:*" not in msg
    assert "*SAR Soil Moisture Proxy:*" not in msg
    assert "  • `Unavailable`" in msg

def test_shap_attribution_wording():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="HIGH",
        event_type="INITIAL_TRIGGER",
        probability=0.75,
        triggered_at="2025-01-01T12:00:00Z",
        shap_drivers=[{"feature": "rainfall_intensity", "contribution": 0.4}]
    )
    assert "Key Risk Drivers (SHAP Attribution):" in msg
    assert "statistical correlation, not definitive causation" in msg
    assert "rainfall_intensity" in msg
    assert "+40%" in msg

def test_mobile_formatting_integrity():
    msg = TelegramMessageBuilder.build_message(
        target_id="t1",
        current_risk_level="HIGH",
        event_type="INITIAL_TRIGGER",
        probability=0.75,
        triggered_at="2025-01-01T12:00:00Z",
        shap_drivers=[{"feature": "slope", "contribution": -0.15}],
        ndvi=0.6,
        sar_soil_moisture=0.4,
        rainfall_3day_mm=120.5
    )
    
    # Assert tags are balanced
    assert msg.count("**") % 2 == 0
    assert msg.count("`") % 2 == 0
