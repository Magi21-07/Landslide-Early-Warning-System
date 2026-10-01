import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.dependencies import get_geospatial_service
from src.api.services.geospatial_service import GeospatialService
from src.risk.risk_store import SQLiteRiskStore

def _fresh_geo_service():
    store = SQLiteRiskStore(":memory:")
    for loc in [
        {"id": "loc1", "lat": 27.5, "lon": 85.5, "risk": "RISK_HIGH"},
        {"id": "loc2", "lat": 28.0, "lon": 86.0, "risk": "RISK_MODERATE"},
        {"id": "loc3", "lat": 29.0, "lon": 87.0, "risk": "RISK_LOW"}
    ]:
        store.save_risk_result({
            "location_id": loc["id"],
            "latitude": loc["lat"],
            "longitude": loc["lon"],
            "timestamp": "2026-10-01T12:00:00Z",
            "risk_level": loc["risk"],
            "stale": False
        })
    return GeospatialService(store=store)

@pytest.fixture(autouse=True)
def reset_geo_override():
    svc = _fresh_geo_service()
    app.dependency_overrides[get_geospatial_service] = lambda: svc
    yield
    app.dependency_overrides.pop(get_geospatial_service, None)

client = TestClient(app, raise_server_exceptions=False)

def test_get_risk_map_valid_feature_collection():
    response = client.get("/api/v1/geospatial/risk-map")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) == 3
    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    coords = feature["geometry"]["coordinates"]
    assert len(coords) == 2
    if feature["properties"]["location_id"] == "loc1":
        assert coords[0] == 85.5  # longitude first
        assert coords[1] == 27.5  # latitude second

def test_bounding_box_filtering():
    response = client.get("/api/v1/geospatial/risk-map?min_lat=27.0&max_lat=27.8&min_lon=85.0&max_lon=85.8")
    assert response.status_code == 200
    data = response.json()
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["location_id"] == "loc1"

def test_invalid_bounding_box():
    response = client.get("/api/v1/geospatial/risk-map?min_lat=28.0&max_lat=27.0")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid bounding box parameters"

def test_empty_result_set():
    response = client.get("/api/v1/geospatial/risk-map?min_lat=10.0&max_lat=20.0")
    assert response.status_code == 200
    assert len(response.json()["features"]) == 0
