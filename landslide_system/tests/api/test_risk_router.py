import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.dependencies import get_risk_service
from src.api.services.risk_service import RiskService
from src.risk.risk_store import SQLiteRiskStore
from src.risk.risk_scheduler import RiskScheduler

def override_get_risk_service():
    store = SQLiteRiskStore(":memory:")
    scheduler = RiskScheduler(gee_config="mock")
    return RiskService(store=store, scheduler=scheduler)

from src.api.config import get_settings

app.dependency_overrides[get_risk_service] = override_get_risk_service

settings = get_settings()
client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_db():
    # Make sure db is cleared or we get a fresh in-memory db before each test
    # Actually risk_service uses lru_cache for get_risk_store. We'll just rely on the 
    # persistent in-memory DB or we can manually empty it if we want.
    pass

def test_evaluate_risk_success():
    payload = {
        "latitude": 27.5,
        "longitude": 85.5
    }
    response = client.post("/api/v1/risk/evaluate?mock=true", json=payload,
                           headers={"X-API-Key": settings.API_KEY})
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == 27.5
    assert data["longitude"] == 85.5
    assert data["data_source"] == "MOCK/SYNTHETIC"
    assert "location_id" in data

def test_evaluate_risk_invalid_coords():
    payload = {
        "latitude": 95.0, # invalid
        "longitude": 85.5
    }
    response = client.post("/api/v1/risk/evaluate?mock=true", json=payload,
                           headers={"X-API-Key": settings.API_KEY})
    # Pydantic validation error is 422
    assert response.status_code == 422

def test_get_latest_risk_success():
    loc_id = "test_latest_loc"
    service = override_get_risk_service()
    app.dependency_overrides[get_risk_service] = lambda: service
    
    service.store.save_risk_result({
        "location_id": loc_id,
        "latitude": 27.5,
        "longitude": 85.5,
        "timestamp": "2026-10-01T12:00:00Z",
        "susceptibility_probability": 0.5,
        "susceptibility_class": "MODERATE",
        "rainfall_trigger_state": "NORMAL",
        "rainfall_trigger_score": 0,
        "dynamic_risk": "LOW",
        "stale": False
    })
    
    response = client.get(f"/api/v1/risk/latest?location_id={loc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["location_id"] == loc_id
    assert data["dynamic_risk"] == "LOW"

def test_get_latest_risk_not_found():
    response = client.get("/api/v1/risk/latest?location_id=UNKNOWN_LOC")
    assert response.status_code == 404

def test_get_risk_history_success():
    loc_id = "test_history_loc"
    service = override_get_risk_service()
    app.dependency_overrides[get_risk_service] = lambda: service
    
    for i in range(3):
        service.store.save_risk_result({
            "location_id": loc_id,
            "latitude": 27.5,
            "longitude": 85.5,
            "timestamp": f"2026-10-01T12:0{i}:00Z",
            "susceptibility_probability": 0.5,
            "susceptibility_class": "MODERATE",
            "rainfall_trigger_state": "NORMAL",
            "rainfall_trigger_score": 0,
            "dynamic_risk": "LOW",
            "stale": False
        })
        
    response = client.get(f"/api/v1/risk/history?location_id={loc_id}&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

def test_get_risk_history_not_found():
    response = client.get("/api/v1/risk/history?location_id=UNKNOWN_LOC_HISTORY")
    assert response.status_code == 404

def test_openapi_includes_endpoints():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    assert "/api/v1/risk/evaluate" in paths
    assert "/api/v1/risk/latest" in paths
    assert "/api/v1/risk/history" in paths
