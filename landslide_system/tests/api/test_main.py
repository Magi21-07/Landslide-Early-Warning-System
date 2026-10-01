import sys
import os

# Ensure the root project directory is in the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["system"] == "Landslide Early Warning System API"
    assert data["version"] == "1.0.0"
    assert data["documentation"] == "/docs"
    assert data["status"] == "online"

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "landslide-api"
    assert data["version"] == "1.0.0"

def test_landslide_status():
    response = client.get("/api/v1/landslide/status")
    assert response.status_code == 200
    data = response.json()
    assert data["system"] == "landslide-early-warning"
    assert data["status"] == "operational"
    assert data["api"] == "ready"

def test_openapi_schema():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Landslide Early Warning System API"
    assert data["info"]["version"] == "1.0.0"
