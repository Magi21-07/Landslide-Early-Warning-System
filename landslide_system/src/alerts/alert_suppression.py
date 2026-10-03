# src/alerts/alert_suppression.py
"""
Phase 8.5 — Telegram Alert Deduplication, Cooldown & Suppression
================================================================

Enforces event deduplication, time-window cooldowns, alert fingerprinting,
and persistence. Prevents notification fatigue by suppressing repeated
identical conditions during cooldown, while allowing genuine severity
escalations to bypass cooldown gates.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from src.alerts.alert_evaluator import AlertEvent
from src.alerts.telegram_config import TelegramConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SuppressionDecision(BaseModel):
    suppressed: bool
    reason: str
    fingerprint: str
    cooldown_expires_at: Optional[str] = None

class DispatchRecord(BaseModel):
    target_id: str
    chat_id: str
    alert_id: str
    event_type: str
    risk_level: str
    dispatched_at: str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)

def _generate_fingerprint(target_id: str, chat_id: str, current_risk_level: str, event_type: str) -> str:
    raw = f"{target_id}:{chat_id}:{current_risk_level}:{event_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------------------
# AlertSuppressionEngine
# ---------------------------------------------------------------------------

class AlertSuppressionEngine:
    def __init__(
        self,
        config: TelegramConfig,
        policy_path: str | Path,
        persistence_path: Optional[str | Path] = None
    ) -> None:
        self.config = config
        self.persistence_path = Path(persistence_path) if persistence_path else None
        
        self.cooldown_minutes = 30
        try:
            with open(policy_path, "r", encoding="utf-8") as f:
                policy_data = yaml.safe_load(f) or {}
            self.cooldown_minutes = policy_data.get("cooldown_minutes", 30)
        except Exception as e:
            logger.warning("Could not read cooldown_minutes from policy, using default: %s", e)

        self._lock = threading.Lock()
        self._history: list[DispatchRecord] = []
        
        if self.persistence_path and self.persistence_path.exists():
            self.load_state()

    def should_suppress_alert(self, target_id: str, chat_id: str, event: AlertEvent) -> SuppressionDecision:
        fingerprint = _generate_fingerprint(target_id, chat_id, event.current_risk_level, event.event_type)
        now = _now_utc()

        with self._lock:
            # 1. Idempotency Window (Exact same alert_id within 60s)
            for rec in reversed(self._history):
                if rec.target_id == target_id and rec.chat_id == chat_id and rec.alert_id == event.alert_id:
                    rec_time = datetime.datetime.fromisoformat(rec.dispatched_at)
                    if (now - rec_time).total_seconds() <= 60:
                        return SuppressionDecision(
                            suppressed=True,
                            reason="IDEMPOTENT_DUPLICATE",
                            fingerprint=fingerprint
                        )
            
            # 2. Escalation Bypass
            if event.event_type == "ESCALATION":
                return SuppressionDecision(
                    suppressed=False,
                    reason="ESCALATION_BYPASS",
                    fingerprint=fingerprint
                )

            # 3. Recovery/De-escalation Handling
            if event.event_type in ("RECOVERY", "DE_ESCALATION"):
                return SuppressionDecision(
                    suppressed=False,
                    reason="RECOVERY_ALLOWED",
                    fingerprint=fingerprint
                )

            # 4. Cooldown Check (HIGH -> HIGH, CRITICAL -> CRITICAL)
            if event.current_risk_level in ("HIGH", "CRITICAL"):
                last_rec = None
                for rec in reversed(self._history):
                    if rec.target_id == target_id and rec.chat_id == chat_id:
                        last_rec = rec
                        break
                
                if last_rec and last_rec.risk_level == event.current_risk_level:
                    rec_time = datetime.datetime.fromisoformat(last_rec.dispatched_at)
                    elapsed_seconds = (now - rec_time).total_seconds()
                    if elapsed_seconds < self.cooldown_minutes * 60:
                        expires_at = (rec_time + datetime.timedelta(minutes=self.cooldown_minutes)).isoformat()
                        return SuppressionDecision(
                            suppressed=True,
                            reason="COOLDOWN_ACTIVE",
                            fingerprint=fingerprint,
                            cooldown_expires_at=expires_at
                        )

            return SuppressionDecision(
                suppressed=False,
                reason="NO_SUPPRESSION",
                fingerprint=fingerprint
            )

    def record_dispatch(self, target_id: str, chat_id: str, event: AlertEvent) -> None:
        rec = DispatchRecord(
            target_id=target_id,
            chat_id=chat_id,
            alert_id=event.alert_id,
            event_type=event.event_type,
            risk_level=event.current_risk_level,
            dispatched_at=_now_utc().isoformat()
        )
        with self._lock:
            self._history.append(rec)
        self.save_state()

    def save_state(self) -> None:
        if not self.persistence_path:
            return
        with self._lock:
            data = [rec.model_dump() for rec in self._history]
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as e:
            logger.warning("Failed to save suppression state: %s", e)

    def load_state(self) -> None:
        if not self.persistence_path or not self.persistence_path.exists():
            return
        try:
            with open(self.persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._history = [DispatchRecord(**rec) for rec in data]
        except Exception as e:
            logger.warning("Failed to load suppression state: %s", e)

    def clear_suppression_history(self) -> None:
        with self._lock:
            self._history.clear()
        self.save_state()
