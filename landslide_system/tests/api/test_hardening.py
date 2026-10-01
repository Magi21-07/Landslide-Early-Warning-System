import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app, raise_server_exceptions=False)

def test_request_id_middleware():
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    
    # Test passing explicit request ID
    custom_id = "test-correlation-123"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id

def test_cors_middleware():
    # Try an allowed origin
    response = client.options("/health", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET"
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    
    # Disallowed origins typically still return 200 for OPTIONS in some ASGI configs but omit the allow-origin header
    # Let's verify standard CORS behavior via FastAPI test client
    response = client.options("/health", headers={
        "Origin": "http://malicious-site.com",
        "Access-Control-Request-Method": "GET"
    })
    assert "access-control-allow-origin" not in response.headers or response.headers["access-control-allow-origin"] != "http://malicious-site.com"

def test_readiness_probe_success():
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

def test_global_exception_handler():
    # Force an unhandled exception by mocking the readiness probe endpoint to raise Exception
    # We can temporarily add a test endpoint to main app
    @app.get("/force-error")
    def force_error():
        raise Exception("Secret internal database password failure")
        
    response = client.get("/force-error")
    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert "request_id" in data
    assert data["error"]["code"] == "INTERNAL_ERROR"
    # Ensure stack trace / secret is NOT leaked
    assert "Secret internal" not in str(data)

def test_value_error_handler():
    @app.get("/force-value-error")
    def force_value_error():
        raise ValueError("Invalid domain state")
        
    response = client.get("/force-value-error")
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Invalid domain state"
    assert "request_id" in data
