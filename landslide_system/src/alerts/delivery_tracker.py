import threading
from typing import Optional, List, Dict
from pydantic import BaseModel

class DeliveryRecord(BaseModel):
    alert_id: str
    target_id: str
    chat_id: str
    attempt_number: int
    started_at: str
    completed_at: Optional[str] = None
    status: str
    success: bool
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

class DeliveryTracker:
    """
    In-memory store (with optional persistence hook) tracking dispatch logs by alert_id.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._history: Dict[str, List[DeliveryRecord]] = {}

    def record_attempt(self, record: DeliveryRecord) -> None:
        with self._lock:
            if record.alert_id not in self._history:
                self._history[record.alert_id] = []
            self._history[record.alert_id].append(record)

    def get_delivery_history(self, alert_id: str) -> List[DeliveryRecord]:
        with self._lock:
            return self._history.get(alert_id, []).copy()

    def is_already_delivered(self, alert_id: str, chat_id: str) -> bool:
        with self._lock:
            records = self._history.get(alert_id, [])
            for r in records:
                if r.chat_id == chat_id and r.success:
                    return True
            return False
