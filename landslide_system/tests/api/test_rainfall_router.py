import pytest
import datetime
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.dependencies import get_rainfall_service
from src.risk.rainfall_service import RainfallService

# Create a mock RainfallService
class MockRainfallService:
    def __init__(self, fail=False):
        self.fail = fail

    def get_recent_rainfall(self, latitude, longitude, days=15, **kwargs):
        if self.fail:
            raise Exception("Mock failure")
            
        records = []
        base = datetime.date.today()
        for i in range(days):
            d = base - datetime.timedelta(days=i)
            records.append({
                "location_id": "test",
                "latitude": latitude,
                "longitude": longitude,
                "date": d.isoformat(),
                "rainfall_mm": 10.0,
                "source": "MOCK"
            })
        return records

client = TestClient(app)

def test_get_recent_rainfall_success():
    app.dependency_overrides[get_rainfall_service] = lambda: MockRainfallService()
    
    response = client.get("/api/v1/rainfall/recent?latitude=27.5&longitude=85.5&days=5")
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == 27.5
    assert len(data["rainfall_observations"]) == 5
    assert data["source"] == "MOCK"

def test_get_recent_rainfall_out_of_bounds():
    response = client.get("/api/v1/rainfall/recent?latitude=95.0&longitude=85.5")
    assert response.status_code == 422

def test_get_recent_rainfall_failure():
    app.dependency_overrides[get_rainfall_service] = lambda: MockRainfallService(fail=True)
    
    response = client.get("/api/v1/rainfall/recent?latitude=27.5&longitude=85.5")
    assert response.status_code == 503
    assert response.json()["detail"] == "Rainfall data service temporarily unavailable"

def test_get_rainfall_summary_success():
    # We must override get_scheduler so get_rainfall_summary uses our mock!
    from src.api.dependencies import get_scheduler
    from src.risk.risk_scheduler import RiskScheduler
    
    class MockScheduler(RiskScheduler):
        def _get_rainfall_service(self):
            return MockRainfallService()
            
    app.dependency_overrides[get_scheduler] = lambda: MockScheduler(gee_config="mock")
    
    response = client.get("/api/v1/rainfall/summary?latitude=27.5&longitude=85.5")
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == 27.5
    assert data["rainfall_1d"] == 10.0
    assert data["rainfall_3d"] == 30.0
    assert data["rainfall_7d"] == 70.0
    assert data["rainfall_15d"] == 150.0
    assert "api_15" in data
    assert "rainfall_trigger_state" in data

def test_get_rainfall_summary_failure():
    from src.api.dependencies import get_scheduler
    from src.risk.risk_scheduler import RiskScheduler
    
    class MockScheduler(RiskScheduler):
        def _get_rainfall_service(self):
            return MockRainfallService(fail=True)
            
    app.dependency_overrides[get_scheduler] = lambda: MockScheduler(gee_config="mock")
    
    response = client.get("/api/v1/rainfall/summary?latitude=27.5&longitude=85.5")
    assert response.status_code == 503
    assert response.json()["detail"] == "Rainfall data service temporarily unavailable"
