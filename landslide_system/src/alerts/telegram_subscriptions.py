# src/alerts/telegram_subscriptions.py
"""
Phase 8.4 — Telegram Alert Subscription Management
====================================================

Manages, persists, and queries target-level Telegram alert subscriptions.
Maps target IDs (e.g. ``"shimla-01"``, ``"wayanad-02"``) to Telegram chat IDs
with per-subscriber minimum severity thresholds.

Design decisions
----------------
* Storage is **in-memory** behind a ``threading.Lock`` for thread safety.
  A ``persistence_path`` hook (JSON file) is provided for optional durability —
  the flush/load methods are deliberately separated from the business logic so
  they can be mocked cleanly in tests.

* **No bot tokens** are ever stored in subscription records.  The schema has
  no token field by design.

* **Uniqueness**: one active subscription per ``(target_id, chat_id)`` pair.
  Creating a duplicate upserts ``minimum_alert_level`` and ``updated_at``.

Severity ordering (for threshold filtering)
-------------------------------------------
LOW (0) < MODERATE (1) < HIGH (2) < CRITICAL (3)

A subscriber with ``minimum_alert_level = "HIGH"`` receives HIGH and CRITICAL
alerts, but NOT LOW or MODERATE.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_LEVELS: tuple[str, ...] = ("LOW", "MODERATE", "HIGH", "CRITICAL")

_SEVERITY: Dict[str, int] = {
    "LOW":      0,
    "MODERATE": 1,
    "HIGH":     2,
    "CRITICAL": 3,
}


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class TelegramSubscription(BaseModel):
    """
    Represents one (target_id, chat_id) Telegram alert subscription.

    Security contract
    -----------------
    No bot token or secret is stored — ``chat_id`` is the public destination
    identifier only.

    Fields
    ------
    subscription_id : str
        UUID v4 string uniquely identifying this record.
    target_id : str
        Non-empty location / site identifier (e.g. ``"shimla-01"``).
    chat_id : str
        Non-empty Telegram chat or channel ID (numeric string or username).
    minimum_alert_level : str
        Minimum risk level that triggers a notification.
        Must be one of ``"LOW"``, ``"MODERATE"``, ``"HIGH"``, ``"CRITICAL"``.
        Default: ``"HIGH"``.
    enabled : bool
        Whether this subscription is currently active.  Default: ``True``.
    created_at : str
        ISO 8601 UTC timestamp of initial creation.
    updated_at : str
        ISO 8601 UTC timestamp of last modification.
    """

    subscription_id:     str  = Field(default_factory=_new_uuid)
    target_id:           str
    chat_id:             str
    minimum_alert_level: str  = "HIGH"
    enabled:             bool = True
    created_at:          str  = Field(default_factory=_now_utc)
    updated_at:          str  = Field(default_factory=_now_utc)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("target_id")
    @classmethod
    def _target_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("target_id must be a non-empty string.")
        return v.strip()

    @field_validator("chat_id")
    @classmethod
    def _chat_id_non_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("chat_id must be a non-empty string.")
        return str(v).strip()

    @field_validator("minimum_alert_level", mode="before")
    @classmethod
    def _validate_alert_level(cls, v: str) -> str:
        normalised = str(v).strip().upper()
        if normalised not in _VALID_LEVELS:
            raise ValueError(
                f"minimum_alert_level must be one of {list(_VALID_LEVELS)!r}; "
                f"got {v!r}."
            )
        return normalised

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def qualifies_for(self, current_alert_level: str) -> bool:
        """
        Return True when this subscription should receive an alert at
        ``current_alert_level``.

        A subscription qualifies when its ``minimum_alert_level`` severity is
        less than or equal to the current alert level severity — and it is
        enabled.
        """
        if not self.enabled:
            return False
        curr_sev = _SEVERITY.get(current_alert_level.upper(), -1)
        min_sev  = _SEVERITY.get(self.minimum_alert_level.upper(), 99)
        return curr_sev >= min_sev


# ---------------------------------------------------------------------------
# Composite key helper
# ---------------------------------------------------------------------------

def _sub_key(target_id: str, chat_id: str) -> str:
    return f"{target_id.strip()}::{chat_id.strip()}"


# ---------------------------------------------------------------------------
# TelegramSubscriptionService
# ---------------------------------------------------------------------------

class TelegramSubscriptionService:
    """
    Thread-safe in-memory subscription store with optional JSON persistence.

    Parameters
    ----------
    persistence_path : str | Path | None
        Path to a JSON file for optional durability.
        * ``None`` (default) — purely in-memory; no file I/O.
        * When supplied, subscriptions are loaded on init and flushed after
          every mutating operation.

    Usage
    -----
    >>> svc = TelegramSubscriptionService()
    >>> sub = svc.create_subscription("shimla-01", "-100123456")
    >>> sub.minimum_alert_level
    'HIGH'
    >>> svc.get_target_subscriptions("shimla-01", current_alert_level="HIGH")
    [TelegramSubscription(...)]
    """

    def __init__(self, persistence_path: Optional[str | Path] = None) -> None:
        self._lock:  threading.Lock                        = threading.Lock()
        # Primary index: composite key → subscription
        self._store: Dict[str, TelegramSubscription]       = {}
        self._persistence_path = (
            Path(persistence_path) if persistence_path else None
        )
        if self._persistence_path and self._persistence_path.exists():
            self._load_from_disk()

    # ------------------------------------------------------------------
    # 1. create_subscription — upsert on duplicate (target_id, chat_id)
    # ------------------------------------------------------------------

    def create_subscription(
        self,
        target_id:           str,
        chat_id:             str,
        minimum_alert_level: str = "HIGH",
    ) -> TelegramSubscription:
        """
        Create a new subscription or upsert an existing one.

        If an active subscription for ``(target_id, chat_id)`` already exists
        its ``minimum_alert_level`` and ``updated_at`` are updated in-place.
        The ``subscription_id`` and ``created_at`` are preserved.

        Parameters
        ----------
        target_id : str
            Location identifier.
        chat_id : str
            Telegram chat / channel ID.
        minimum_alert_level : str
            Minimum severity threshold (default ``"HIGH"``).

        Returns
        -------
        TelegramSubscription
            The created or updated subscription record.
        """
        # Validate level before acquiring lock (raises ValueError on bad input)
        level_norm = _normalise_level(minimum_alert_level)
        key = _sub_key(target_id, chat_id)

        with self._lock:
            existing = self._store.get(key)
            if existing is not None:
                # Upsert: update level + timestamp, preserve id & created_at
                updated = existing.model_copy(update={
                    "minimum_alert_level": level_norm,
                    "updated_at":          _now_utc(),
                    "enabled":             True,
                })
                self._store[key] = updated
                logger.info(
                    "SubscriptionService: upserted %s → level=%s",
                    key, level_norm,
                )
                sub = updated
            else:
                sub = TelegramSubscription(
                    target_id           = target_id,
                    chat_id             = chat_id,
                    minimum_alert_level = level_norm,
                    enabled             = True,
                )
                self._store[key] = sub
                logger.info(
                    "SubscriptionService: created %s → level=%s",
                    key, level_norm,
                )

        self._flush()
        return sub

    # ------------------------------------------------------------------
    # 2. disable_subscription
    # ------------------------------------------------------------------

    def disable_subscription(self, target_id: str, chat_id: str) -> bool:
        """
        Set ``enabled = False`` on the matching subscription.

        Returns
        -------
        bool
            ``True`` if the subscription was found and updated;
            ``False`` if no record exists for ``(target_id, chat_id)``.
        """
        key = _sub_key(target_id, chat_id)
        with self._lock:
            existing = self._store.get(key)
            if existing is None:
                return False
            self._store[key] = existing.model_copy(update={
                "enabled":    False,
                "updated_at": _now_utc(),
            })
        self._flush()
        logger.info("SubscriptionService: disabled %s", key)
        return True

    # ------------------------------------------------------------------
    # 3. enable_subscription
    # ------------------------------------------------------------------

    def enable_subscription(self, target_id: str, chat_id: str) -> bool:
        """
        Set ``enabled = True`` on the matching subscription.

        Returns
        -------
        bool
            ``True`` if the subscription was found and updated;
            ``False`` if no record exists for ``(target_id, chat_id)``.
        """
        key = _sub_key(target_id, chat_id)
        with self._lock:
            existing = self._store.get(key)
            if existing is None:
                return False
            self._store[key] = existing.model_copy(update={
                "enabled":    True,
                "updated_at": _now_utc(),
            })
        self._flush()
        logger.info("SubscriptionService: enabled %s", key)
        return True

    # ------------------------------------------------------------------
    # 4. get_target_subscriptions — with optional severity filter
    # ------------------------------------------------------------------

    def get_target_subscriptions(
        self,
        target_id:            str,
        current_alert_level:  Optional[str] = None,
    ) -> List[TelegramSubscription]:
        """
        Return active subscriptions for ``target_id``, optionally filtered
        by severity threshold.

        Parameters
        ----------
        target_id : str
            Location identifier to query.
        current_alert_level : str | None
            When supplied (e.g. ``"HIGH"``), only subscriptions whose
            ``minimum_alert_level`` ≤ ``current_alert_level`` are returned.
            When ``None``, all enabled subscriptions are returned.

        Returns
        -------
        list[TelegramSubscription]
            Matching active subscriptions (empty list if none).
        """
        target_id = target_id.strip()
        with self._lock:
            candidates = [
                sub for sub in self._store.values()
                if sub.target_id == target_id and sub.enabled
            ]

        if current_alert_level is not None:
            curr = current_alert_level.strip().upper()
            candidates = [s for s in candidates if s.qualifies_for(curr)]

        return candidates

    # ------------------------------------------------------------------
    # 5. list_all_subscriptions — administrative query
    # ------------------------------------------------------------------

    def list_all_subscriptions(
        self,
        target_id: Optional[str] = None,
    ) -> List[TelegramSubscription]:
        """
        Return all subscriptions (enabled and disabled).

        Parameters
        ----------
        target_id : str | None
            When supplied, filters to only that target.

        Returns
        -------
        list[TelegramSubscription]
        """
        with self._lock:
            subs = list(self._store.values())

        if target_id is not None:
            tid = target_id.strip()
            subs = [s for s in subs if s.target_id == tid]

        return subs

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:  # pragma: no cover
        return f"TelegramSubscriptionService(subscriptions={len(self)})"

    # ------------------------------------------------------------------
    # Persistence helpers (isolated — easy to mock in tests)
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        """Write current state to the persistence file (if configured)."""
        if self._persistence_path is None:
            return
        try:
            with self._lock:
                data = {k: v.model_dump() for k, v in self._store.items()}
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persistence_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
        except OSError as exc:  # pragma: no cover
            logger.warning("SubscriptionService: flush failed: %s", exc)

    def _load_from_disk(self) -> None:
        """Load persisted subscriptions from the JSON file."""
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as fh:  # type: ignore[arg-type]
                raw: dict = json.load(fh)
            with self._lock:
                for key, record in raw.items():
                    self._store[key] = TelegramSubscription(**record)
            logger.info(
                "SubscriptionService: loaded %d subscriptions from %s",
                len(self._store), self._persistence_path,
            )
        except (OSError, ValueError, KeyError) as exc:  # pragma: no cover
            logger.warning("SubscriptionService: load failed: %s", exc)

    def clear(self) -> None:
        """Clear all subscriptions (test isolation helper)."""
        with self._lock:
            self._store.clear()


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _normalise_level(level: str) -> str:
    """Validate and normalise a minimum_alert_level string."""
    normalised = str(level).strip().upper()
    if normalised not in _VALID_LEVELS:
        raise ValueError(
            f"minimum_alert_level must be one of {list(_VALID_LEVELS)!r}; "
            f"got {level!r}."
        )
    return normalised
