import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.config import get_settings
from src.api.dependencies import get_risk_service
from src.risk.risk_store import SQLiteRiskStore
from src.risk.risk_scheduler import RiskScheduler
from src.api.services.risk_service import RiskService

def override_get_risk_service():
    store = SQLiteRiskStore(":memory:")
    scheduler = RiskScheduler(gee_config="mock")
    return RiskService(store=store, scheduler=scheduler)

app.dependency_overrides[get_risk_service] = override_get_risk_service

client = TestClient(app, raise_server_exceptions=False)

def test_public_endpoint_unauthenticated():
    # Should work without API Key
    response = client.get("/health")
    assert response.status_code == 200
    
    response = client.get("/health/ready")
    assert response.status_code == 200

def test_protected_endpoint_missing_key():
    payload = {"latitude": 27.5, "longitude": 85.5}
    response = client.post("/api/v1/risk/evaluate?mock=true", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API Key"

def test_protected_endpoint_invalid_key():
    payload = {"latitude": 27.5, "longitude": 85.5}
    response = client.post(
        "/api/v1/risk/evaluate?mock=true", 
        json=payload, 
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API Key"

def test_protected_endpoint_valid_key():
    settings = get_settings()
    payload = {"latitude": 27.5, "longitude": 85.5}
    response = client.post(
        "/api/v1/risk/evaluate?mock=true", 
        json=payload, 
        headers={"X-API-Key": settings.API_KEY}
    )
    assert response.status_code == 200
    assert response.json()["latitude"] == 27.5

def test_openapi_schema_contains_security():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    
    # Verify security schemes are defined
    assert "components" in schema
    assert "securitySchemes" in schema["components"]
    assert "APIKeyHeader" in schema["components"]["securitySchemes"]
    
    # Verify the protected endpoint requires the security scheme
    evaluate_route = schema["paths"]["/api/v1/risk/evaluate"]["post"]
    assert "security" in evaluate_route
    assert any("APIKeyHeader" in req for req in evaluate_route["security"])
