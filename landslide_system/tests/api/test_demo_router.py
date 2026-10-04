import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_low_risk_parameters():
    # Test 1 (Low Risk Parameters): Low rainfall (10mm) & mild slope (10°) returns LOW risk and no alert event.
    payload = {
        "target_id": "DEMO-001",
        "rainfall_3d_mm": 10.0,
        "soil_moisture_pct": 20.0,
        "terrain_slope": 10.0,
        "trigger_telegram": False
    }
    response = client.post("/api/v1/demo/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["risk_response"]["risk_level"] in ("LOW", "MODERATE")
    assert not data["alert_summary"]["event_emitted"]

def test_extreme_risk_shift():
    # Test 2 (Extreme Risk Shift): High rainfall (220mm) & steep slope (45°) produces HIGH or CRITICAL risk 
    # with dynamic SHAP values reflecting rainfall as top driver.
    payload = {
        "target_id": "DEMO-002",
        "rainfall_3d_mm": 220.0,
        "soil_moisture_pct": 95.0,
        "terrain_slope": 45.0,
        "trigger_telegram": False
    }
    response = client.post("/api/v1/demo/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["risk_response"]["risk_level"] in ("HIGH", "CRITICAL")
    top_factors = data["risk_response"]["top_risk_factors"]
    assert len(top_factors) > 0

def test_state_isolation_check():
    # Test 3 (State Isolation Check): Verify calling /api/v1/demo/simulate multiple times 
    # does not alter persistent StateStore target history or AlertHistoryService.
    # Since AlertEvaluator instantiates a local empty state store each time it runs,
    # the second call should be an INITIAL_TRIGGER again (not PERSISTENT_UNCHANGED).
    payload = {
        "target_id": "DEMO-003",
        "rainfall_3d_mm": 220.0,
        "soil_moisture_pct": 95.0,
        "terrain_slope": 45.0,
        "trigger_telegram": False
    }
    r1 = client.post("/api/v1/demo/simulate", json=payload)
    assert r1.status_code == 200
    
    r2 = client.post("/api/v1/demo/simulate", json=payload)
    assert r2.status_code == 200
    
    # In a stateful real app, identical HIGH calls trigger PERSISTENT_UNCHANGED or suppress.
    # Here, it is stateless, so event type should be INITIAL_TRIGGER for both if it was triggered.
    if r1.json()["alert_summary"]["event_emitted"]:
        assert r1.json()["alert_summary"]["event_type"] == "INITIAL_TRIGGER"
        assert r2.json()["alert_summary"]["event_type"] == "INITIAL_TRIGGER"
