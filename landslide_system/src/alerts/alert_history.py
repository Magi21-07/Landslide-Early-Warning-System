from pydantic import BaseModel
from typing import Optional, List, Dict
import threading
from src.alerts.alert_evaluator import AlertEvent
from src.alerts.delivery_tracker import DeliveryRecord
import uuid

class AlertHistoryRecord(BaseModel):
    alert_id: str
    target_id: str
    alert_type: str
    severity: str
    trigger_reason: str
    triggered_at: str
    resolved_at: Optional[str] = None
    telegram_delivery_status: str
    telegram_message_id: Optional[str] = None
    retry_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None

class AlertHistoryService:
    def __init__(self):
        self._lock = threading.Lock()
        self._store: Dict[str, AlertHistoryRecord] = {}

    def record_alert_event(self, event: AlertEvent, delivery_record: Optional[DeliveryRecord] = None) -> AlertHistoryRecord:
        with self._lock:
            # Look up by either provided event.alert_id, event_id or fallback to a new uuid for storage
            alert_id = getattr(event, "alert_id", None) or getattr(event, "event_id", None)
            if not alert_id:
                alert_id = str(uuid.uuid4())

            # Check if record exists to update it, else create new
            if alert_id in self._store:
                record = self._store[alert_id]
                if delivery_record:
                    record.telegram_delivery_status = delivery_record.status
                    record.telegram_message_id = delivery_record.message_id
                    record.retry_count = delivery_record.attempt_number
                    record.error_code = delivery_record.error_code
                    record.error_message = delivery_record.error_message
                return record

            resolved_at = None
            if event.event_type == "RECOVERY":
                # using triggered_at as resolved_at for simplicity when it's a recovery event
                resolved_at = event.triggered_at

            telegram_delivery_status = "NOT_SENT"
            telegram_message_id = None
            retry_count = 0
            error_code = None
            error_message = None

            if delivery_record:
                telegram_delivery_status = delivery_record.status
                telegram_message_id = delivery_record.message_id
                retry_count = delivery_record.attempt_number
                error_code = delivery_record.error_code
                error_message = delivery_record.error_message

            record = AlertHistoryRecord(
                alert_id=alert_id,
                target_id=event.target_id,
                alert_type=event.event_type,
                severity=event.current_risk_level,
                trigger_reason=event.trigger_reason,
                triggered_at=event.triggered_at,
                resolved_at=resolved_at,
                telegram_delivery_status=telegram_delivery_status,
                telegram_message_id=telegram_message_id,
                retry_count=retry_count,
                error_code=error_code,
                error_message=error_message
            )

            self._store[alert_id] = record
            return record

    def get_target_history(self, target_id: str, limit: int = 50, offset: int = 0) -> List[AlertHistoryRecord]:
        with self._lock:
            records = [r for r in self._store.values() if r.target_id == target_id]
            
            # Sort descending by triggered_at
            records.sort(key=lambda x: x.triggered_at, reverse=True)
            
            # Paginate
            return records[offset:offset+limit]

    def get_alert_by_id(self, alert_id: str) -> Optional[AlertHistoryRecord]:
        with self._lock:
            return self._store.get(alert_id)
