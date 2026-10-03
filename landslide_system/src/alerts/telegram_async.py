import asyncio
import datetime
import logging
import uuid
import re
from typing import Optional, Dict, Any

from src.alerts.alert_evaluator import AlertEvent
from src.alerts.telegram_config import TelegramConfig
from src.alerts.telegram_formatter import format_event
from src.alerts.providers.telegram_provider import TelegramProvider, MockTelegramProvider
from src.alerts.delivery_tracker import DeliveryTracker, DeliveryRecord

logger = logging.getLogger(__name__)

class AsyncTelegramDispatcher:
    """
    Handles transient failures with exponential backoff retries, respects 
    Telegram HTTP 429 rate limits, enforces idempotency, drops permanent 
    failures immediately, and logs audit records for all dispatch attempts.
    """
    def __init__(self, config: TelegramConfig, tracker: DeliveryTracker, provider=None):
        self.config = config
        self.tracker = tracker
        if provider:
            self.provider = provider
        elif config.mode == "TEST":
            self.provider = MockTelegramProvider(config)
        else:
            self.provider = TelegramProvider(config)

    async def dispatch_in_background(self, event: AlertEvent, chat_id: str, max_retries: int = 3) -> None:
        alert_id = getattr(event, "alert_id", None) or getattr(event, "event_id", None)
        if not alert_id:
            alert_id = str(uuid.uuid4())
            
        if self.tracker.is_already_delivered(alert_id, chat_id):
            logger.info(f"Alert {alert_id} already delivered to {chat_id}. Skipping.")
            return

        message_text = format_event(event)

        for attempt in range(1, max_retries + 1):
            started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            try:
                result = await self.provider.send_message(chat_id, message_text)
            except Exception as e:
                result = {
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": str(e)
                }
                
            completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            record = DeliveryRecord(
                alert_id=alert_id,
                target_id=event.target_id,
                chat_id=chat_id,
                attempt_number=attempt,
                started_at=started_at,
                completed_at=completed_at,
                status="SUCCESS" if result.get("success") else "FAILED",
                success=result.get("success", False),
                message_id=result.get("message_id"),
                error_code=result.get("error_code"),
                error_message=result.get("error_message")
            )

            if result.get("success"):
                self.tracker.record_attempt(record)
                return

            err_code = result.get("error_code")
            # Determine transient vs permanent
            transient = err_code in ("NETWORK_TIMEOUT", "CONNECTION_FAILED", "RATE_LIMITED", "TELEGRAM_SERVER_ERROR")
            
            if not transient:
                # permanent error
                self.tracker.record_attempt(record)
                return
            
            # Transient error, handle retries
            if attempt < max_retries:
                record.status = "RETRYING"
                self.tracker.record_attempt(record)
                
                # Sleep before retry
                delay = 2 ** (attempt - 1)  # 1s, 2s, 4s
                
                if err_code == "RATE_LIMITED":
                    # Try to parse retry-after from error_message if provider added it
                    match = re.search(r"Retry-After:\s*(\d+)", result.get("error_message", ""))
                    if match:
                        delay = max(delay, int(match.group(1)))
                
                await asyncio.sleep(delay)
            else:
                self.tracker.record_attempt(record)
