"""
tests/api/test_phase6_integration.py
--------------------------------------
Phase 6.10: Complete end-to-end integration test suite for the FastAPI backend.
Covers all implemented endpoints with realistic mock injection.
No live GEE/CHIRPS calls. No blocking server processes.
"""
import datetime
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.config import get_settings
from src.api.dependencies import (
    get_risk_service,
    get_rainfall_service,
    get_geospatial_service,
    get_scheduler,
)
from src.api.services.risk_service import RiskService
from src.api.services.geospatial_service import GeospatialService
from src.risk.risk_store import SQLiteRiskStore
from src.risk.risk_scheduler import RiskScheduler

settings = get_settings()
API_KEY = settings.API_KEY

# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

class MockRainfallService:
    """Deterministic offline rainfall service."""
    def get_recent_rainfall(self, latitude, longitude, days=15, **kwargs):
        base = datetime.date.today()
        return [
            {
                "location_id": "mock",
                "latitude": latitude,
                "longitude": longitude,
                "date": (base - datetime.timedelta(days=i)).isoformat(),
                "rainfall_mm": 10.0,
                "source": "MOCK",
                "retrieved_at": datetime.datetime.utcnow().isoformat(),
            }
            for i in range(days)
        ]


class MockSchedulerWithRainfall(RiskScheduler):
    def _get_rainfall_service(self):
        return MockRainfallService()


def make_risk_service(store=None):
    store = store or SQLiteRiskStore(":memory:")
    sched = RiskScheduler(gee_config="mock")
    return RiskService(store=store, scheduler=sched)


def make_geospatial_service(records=None):
    store = SQLiteRiskStore(":memory:")
    if records:
        for r in records:
            store.save_risk_result(r)
    return GeospatialService(store=store)


# ---------------------------------------------------------------------------
# Set up dependency overrides
# ---------------------------------------------------------------------------

_shared_risk_service = make_risk_service()
_shared_geo_store = SQLiteRiskStore(":memory:")

# Pre-populate geo store for geospatial tests
_shared_geo_service = GeospatialService(store=_shared_geo_store)
for _loc in [
    {"location_id": "LOC-A", "latitude": 27.5, "longitude": 85.5,
     "timestamp": "2026-10-01T12:00:00Z", "dynamic_risk": "HIGH",
     "risk_level": "RISK_HIGH", "stale": False},
    {"location_id": "LOC-B", "latitude": 28.0, "longitude": 86.0,
     "timestamp": "2026-10-01T11:00:00Z", "dynamic_risk": "LOW",
     "risk_level": "RISK_LOW", "stale": False},
]:
    _shared_geo_store.save_risk_result(_loc)

# Pre-populate the risk service store for read-endpoint tests
_shared_risk_service.store.save_risk_result({
    "location_id": "INTEGRATION_LOC",
    "latitude": 30.0,
    "longitude": 77.0,
    "timestamp": "2026-10-01T12:00:00Z",
    "susceptibility_probability": 0.72,
    "susceptibility_class": "HIGH",
    "rainfall_trigger_state": "WATCH",
    "rainfall_trigger_score": 1,
    "dynamic_risk": "HIGH",
    "stale": False,
})
for _i in range(5):
    _shared_risk_service.store.save_risk_result({
        "location_id": "HIST_TEST_LOC",
        "latitude": 27.5,
        "longitude": 85.5,
        "timestamp": f"2026-10-01T12:0{_i}:00Z",
        "dynamic_risk": "MODERATE",
        "stale": False,
    })

app.dependency_overrides[get_risk_service] = lambda: _shared_risk_service
app.dependency_overrides[get_rainfall_service] = lambda: MockRainfallService()
app.dependency_overrides[get_scheduler] = lambda: MockSchedulerWithRainfall(gee_config="mock")
app.dependency_overrides[get_geospatial_service] = lambda: _shared_geo_service

# Separate isolated service for tests that need a predictable, clean store
def _make_isolated_risk_service():
    store = SQLiteRiskStore(":memory:")
    store.save_risk_result({
        "location_id": "INTEGRATION_LOC",
        "latitude": 30.0,
        "longitude": 77.0,
        "timestamp": "2026-10-01T12:00:00Z",
        "susceptibility_probability": 0.72,
        "susceptibility_class": "HIGH",
        "rainfall_trigger_state": "WATCH",
        "rainfall_trigger_score": 1,
        "dynamic_risk": "HIGH",
        "stale": False,
    })
    for i in range(5):
        store.save_risk_result({
            "location_id": "HIST_TEST_LOC",
            "latitude": 27.5,
            "longitude": 85.5,
            "timestamp": f"2026-10-01T12:0{i}:00Z",
            "dynamic_risk": "MODERATE",
            "stale": False,
        })
    return RiskService(store=store, scheduler=RiskScheduler(gee_config="mock"))

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Root & liveness endpoints
# ---------------------------------------------------------------------------

def test_root_endpoint():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["system"] == "Landslide Early Warning System API"
    assert data["version"] == "1.0.0"
    assert "documentation" in data
    assert "status" in data


def test_health_liveness():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_readiness():
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# ---------------------------------------------------------------------------
# 2. Risk evaluation endpoints (POST — PROTECTED)
# ---------------------------------------------------------------------------

def test_risk_evaluate_no_auth():
    """Missing API key must return 401."""
    r = client.post("/api/v1/risk/evaluate?mock=true",
                    json={"latitude": 27.5, "longitude": 85.5})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or missing API Key"


def test_risk_evaluate_wrong_auth():
    """Wrong API key must return 401."""
    r = client.post("/api/v1/risk/evaluate?mock=true",
                    json={"latitude": 27.5, "longitude": 85.5},
                    headers={"X-API-Key": "totally-wrong-key"})
    assert r.status_code == 401


def test_risk_evaluate_valid_auth():
    """Valid API key with mock=true must return 200 with correct schema."""
    r = client.post("/api/v1/risk/evaluate?mock=true",
                    json={"latitude": 27.5, "longitude": 85.5},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    data = r.json()
    assert data["latitude"] == 27.5
    assert data["longitude"] == 85.5
    assert "dynamic_risk" in data
    assert data["data_source"] == "MOCK/SYNTHETIC"
    assert data["stale"] is False


def test_risk_evaluate_invalid_coords():
    """Out-of-bounds coordinates must return 422 (Pydantic rejection)."""
    r = client.post("/api/v1/risk/evaluate?mock=true",
                    json={"latitude": 95.0, "longitude": 85.5},
                    headers={"X-API-Key": API_KEY})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 3. Risk read endpoints (GET — PUBLIC)
# ---------------------------------------------------------------------------

def test_risk_latest_not_found():
    r = client.get("/api/v1/risk/latest?location_id=UNKNOWN_LOC_XYZ")
    assert r.status_code == 404


def test_risk_latest_found():
    isolated = _make_isolated_risk_service()
    app.dependency_overrides[get_risk_service] = lambda: isolated
    r = client.get("/api/v1/risk/latest?location_id=INTEGRATION_LOC")
    app.dependency_overrides[get_risk_service] = lambda: _shared_risk_service
    assert r.status_code == 200
    data = r.json()
    assert data["location_id"] == "INTEGRATION_LOC"
    assert data["dynamic_risk"] == "HIGH"


def test_risk_history_not_found():
    r = client.get("/api/v1/risk/history?location_id=UNKNOWN_HIST_LOC")
    assert r.status_code == 404


def test_risk_history_with_limit():
    isolated = _make_isolated_risk_service()
    app.dependency_overrides[get_risk_service] = lambda: isolated
    r = client.get("/api/v1/risk/history?location_id=HIST_TEST_LOC&limit=3")
    app.dependency_overrides[get_risk_service] = lambda: _shared_risk_service
    assert r.status_code == 200
    assert len(r.json()) == 3


# ---------------------------------------------------------------------------
# 4. Rainfall endpoints (GET — PUBLIC)
# ---------------------------------------------------------------------------

def test_rainfall_recent_success():
    r = client.get("/api/v1/rainfall/recent?latitude=27.5&longitude=85.5&days=7")
    assert r.status_code == 200
    data = r.json()
    assert data["latitude"] == 27.5
    assert len(data["rainfall_observations"]) == 7
    assert data["source"] == "MOCK"


def test_rainfall_recent_invalid_coords():
    r = client.get("/api/v1/rainfall/recent?latitude=95.0&longitude=85.5")
    assert r.status_code == 422


def test_rainfall_summary_success():
    r = client.get("/api/v1/rainfall/summary?latitude=27.5&longitude=85.5")
    assert r.status_code == 200
    data = r.json()
    assert "rainfall_1d" in data
    assert "rainfall_3d" in data
    assert "rainfall_7d" in data
    assert "rainfall_15d" in data
    assert "api_15" in data
    assert "rainfall_trigger_state" in data
    assert "rainfall_trigger_score" in data
    assert data["rainfall_1d"] == 10.0
    assert data["rainfall_3d"] == 30.0


# ---------------------------------------------------------------------------
# 5. Geospatial endpoint (GET — PUBLIC)
# ---------------------------------------------------------------------------

def test_geospatial_risk_map_feature_collection():
    fresh_geo = GeospatialService(store=_shared_geo_store)
    app.dependency_overrides[get_geospatial_service] = lambda: GeospatialService(store=_shared_geo_store)
    r = client.get("/api/v1/geospatial/risk-map")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)
    # At least LOC-A and LOC-B must be present
    location_ids = [f["properties"]["location_id"] for f in data["features"]]
    assert "LOC-A" in location_ids
    assert "LOC-B" in location_ids


def test_geospatial_coordinate_order():
    """GeoJSON strictly mandates [longitude, latitude] order."""
    # Use bbox to ensure only LOC-A (known coords) is returned
    r = client.get("/api/v1/geospatial/risk-map?min_lat=27.0&max_lat=27.9&min_lon=85.0&max_lon=85.9")
    data = r.json()
    assert len(data["features"]) >= 1
    for feature in data["features"]:
        coords = feature["geometry"]["coordinates"]
        props = feature["properties"]
        assert feature["geometry"]["type"] == "Point"
        assert len(coords) == 2
        if props.get("location_id") == "LOC-A":
            assert coords[0] == 85.5  # longitude first
            assert coords[1] == 27.5  # latitude second


def test_geospatial_bounding_box_filter():
    # Narrow box that can ONLY match LOC-A at (27.5, 85.5)
    r = client.get("/api/v1/geospatial/risk-map?min_lat=27.4&max_lat=27.6&min_lon=85.4&max_lon=85.6")
    data = r.json()
    ids = [f["properties"]["location_id"] for f in data["features"]]
    assert "LOC-A" in ids
    assert "LOC-B" not in ids


def test_geospatial_invalid_bbox():
    r = client.get("/api/v1/geospatial/risk-map?min_lat=28.0&max_lat=27.0")
    assert r.status_code == 400


def test_geospatial_empty_bbox():
    r = client.get("/api/v1/geospatial/risk-map?min_lat=10.0&max_lat=15.0")
    assert r.status_code == 200
    assert len(r.json()["features"]) == 0


# ---------------------------------------------------------------------------
# 6. Interactive documentation endpoints
# ---------------------------------------------------------------------------

def test_swagger_ui_returns_html():
    r = client.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_openapi_schema_valid():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "Landslide Early Warning System API"
    # Verify all key route paths are registered
    paths = schema["paths"]
    assert "/api/v1/risk/evaluate" in paths
    assert "/api/v1/risk/latest" in paths
    assert "/api/v1/risk/history" in paths
    assert "/api/v1/rainfall/recent" in paths
    assert "/api/v1/rainfall/summary" in paths
    assert "/api/v1/geospatial/risk-map" in paths


# ---------------------------------------------------------------------------
# 7. X-Request-ID correlation and error sanitization
# ---------------------------------------------------------------------------

def test_request_id_propagation():
    custom_id = "integration-test-id-12345"
    r = client.get("/health", headers={"X-Request-ID": custom_id})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == custom_id


def test_auto_request_id_generated():
    r = client.get("/health")
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) > 0


def test_error_response_no_stack_trace():
    """Server errors must return sanitized ErrorResponse without tracebacks."""
    @app.get("/integration-force-error")
    def _force_error():
        raise Exception("Internal DB connection refused — secret password: xyz")

    r = client.get("/integration-force-error")
    assert r.status_code == 500
    data = r.json()
    assert "error" in data
    assert "request_id" in data
    assert data["error"]["code"] == "INTERNAL_ERROR"
    # Traceback and secret must NOT appear in client response
    assert "Traceback" not in str(data)
    assert "secret password" not in str(data)
