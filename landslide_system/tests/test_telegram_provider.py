# tests/test_telegram_provider.py
"""
Phase 8.7 — Unit tests for TelegramProvider and MockTelegramProvider
"""

import pytest
import httpx
import asyncio
from unittest.mock import patch, AsyncMock

from src.alerts.telegram_config import TelegramConfig
from src.alerts.providers.telegram_provider import TelegramProvider, MockTelegramProvider

@pytest.fixture
def config():
    return TelegramConfig(
        mode="REAL", 
        enabled=True, 
        bot_token="secret_token_123", 
        chat_id="chat_123"
    )

def test_successful_delivery(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"message_id": 999}})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is True
    assert result["message_id"] == "999"
    assert result["provider"] == "telegram"
    assert result["error_code"] is None

def test_error_400(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400)
    
    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "INVALID_REQUEST_OR_CHAT_ID"

def test_error_403(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)
    
    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "BOT_PERMISSION_DENIED"

def test_error_429(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    
    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "RATE_LIMITED"

def test_error_500(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    
    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "TELEGRAM_SERVER_ERROR"

def test_error_unknown(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(418)
    
    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_HTTP_ERROR"

def test_network_timeout(config):
    provider = TelegramProvider(config)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = httpx.TimeoutException("timeout")
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "NETWORK_TIMEOUT"

def test_network_error(config):
    provider = TelegramProvider(config)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = httpx.RequestError("connection failed")
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "CONNECTION_FAILED"

def test_internal_error(config):
    provider = TelegramProvider(config)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = Exception("internal error")
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert result["success"] is False
    assert result["error_code"] == "INTERNAL_ERROR"

def test_credential_security_no_token_in_error(config):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    
    transport = httpx.MockTransport(mock_handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TelegramProvider(config)
    
    with patch("src.alerts.providers.telegram_provider.httpx.AsyncClient", return_value=client):
        result = asyncio.run(provider.send_message("chat_123", "Hello"))
        
    assert "secret_token_123" not in str(result)
    assert "secret_token_123" not in str(result.get("error_message", ""))

def test_mock_provider():
    config = TelegramConfig(mode="TEST", enabled=True)
    provider = MockTelegramProvider(config)
    
    result = asyncio.run(provider.send_message("chat_123", "Hello"))
    
    assert result["success"] is True
    assert result["message_id"] == "mock_msg_123"
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0]["text"] == "Hello"
    assert provider.sent_messages[0]["chat_id"] == "chat_123"
