# src/alerts/providers/telegram_provider.py
"""
Phase 8.7 — Telegram Bot API Provider & Error Resilience
========================================================
Isolates the low-level HTTP transport layer for Telegram Bot API calls.
Provides comprehensive error handling (timeouts, 400 Bad Request, 403 Forbidden, 
429 Rate Limits, 5xx Server Errors), redacts sensitive bot tokens from all error 
payloads/logs, and exposes a normalized result schema.
"""

import logging
from typing import Any, Dict, List, Optional
import httpx
from src.alerts.telegram_config import TelegramConfig

logger = logging.getLogger(__name__)

class TelegramProvider:
    def __init__(self, config: TelegramConfig):
        self.config = config

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
        token = self.config.bot_token.get_secret_value() if self.config.bot_token else ""
        # Redact token from any logs by ensuring it is never printed.
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, data=payload)
                
            if response.status_code == 200:
                data = response.json()
                message_id = str(data.get("result", {}).get("message_id"))
                return self._success_resp(chat_id, message_id)
            elif response.status_code == 400:
                return self._error_resp(chat_id, "INVALID_REQUEST_OR_CHAT_ID", "Invalid chat ID or bad Markdown syntax.")
            elif response.status_code == 403:
                return self._error_resp(chat_id, "BOT_PERMISSION_DENIED", "Bot blocked or missing permissions.")
            elif response.status_code == 429:
                return self._error_resp(chat_id, "RATE_LIMITED", "Telegram rate limit (HTTP 429). Retry-After: unknown.")
            elif response.status_code >= 500:
                return self._error_resp(chat_id, "TELEGRAM_SERVER_ERROR", f"Telegram API returned HTTP {response.status_code}.")
            else:
                return self._error_resp(chat_id, "UNKNOWN_HTTP_ERROR", f"Telegram API returned HTTP {response.status_code}.")

        except httpx.TimeoutException as exc:
            return self._error_resp(chat_id, "NETWORK_TIMEOUT", f"Network timeout: {exc}")
        except httpx.RequestError as exc:
            return self._error_resp(chat_id, "CONNECTION_FAILED", f"Network error: {exc}")
        except Exception as exc:
            return self._error_resp(chat_id, "INTERNAL_ERROR", "An internal error occurred.")

    def _success_resp(self, chat_id: str, message_id: str) -> Dict[str, Any]:
        return {
            "success": True,
            "provider": "telegram",
            "chat_id": chat_id,
            "message_id": message_id,
            "error_code": None,
            "error_message": None,
        }

    def _error_resp(self, chat_id: str, code: str, msg: str) -> Dict[str, Any]:
        return {
            "success": False,
            "provider": "telegram",
            "chat_id": chat_id,
            "message_id": None,
            "error_code": code,
            "error_message": msg,
        }

class MockTelegramProvider(TelegramProvider):
    def __init__(self, config: TelegramConfig):
        super().__init__(config)
        self.sent_messages: List[Dict[str, Any]] = []

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        })
        return self._success_resp(chat_id, "mock_msg_123")
