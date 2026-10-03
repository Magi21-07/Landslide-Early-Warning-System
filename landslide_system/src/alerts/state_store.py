# src/alerts/state_store.py
"""
Phase 8.2 — Target State Store
================================

In-memory, thread-safe store that tracks the last known risk evaluation
state for each target.  Used by AlertEvaluator to determine state
transitions (escalation, de-escalation, persistence, etc.).

No persistence layer is required in this phase — state lives only for
the lifetime of the process.  Clean-state injection via `clear_state()`
supports deterministic unit testing without any filesystem dependency.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State record shape
# ---------------------------------------------------------------------------

# Each entry stored under a target_id has the following keys:
#   risk_level  : str   — "LOW" | "MODERATE" | "HIGH" | "CRITICAL"
#   timestamp   : str   — ISO 8601 UTC string of the evaluation
#   probability : float — raw susceptibility probability [0.0, 1.0]

_StateRecord = dict  # typed alias for readability


# ---------------------------------------------------------------------------
# TargetStateStore
# ---------------------------------------------------------------------------

class TargetStateStore:
    """
    Thread-safe in-memory store for per-target risk evaluation states.

    Operations
    ----------
    get_last_state(target_id)
        Returns the most-recent state record for the given target,
        or ``None`` if no state has been recorded yet.

    update_state(target_id, risk_level, timestamp, probability)
        Upserts the current state for the given target.

    clear_state(target_id=None)
        Clears state for a specific target, or **all** targets when
        called with no argument (useful for test isolation).

    Thread-safety
    -------------
    All mutating operations are protected by a ``threading.Lock``.
    Read operations acquire the same lock to guarantee a consistent
    snapshot.

    Usage
    -----
    >>> store = TargetStateStore()
    >>> store.update_state("LOC_001", "HIGH", "2026-01-01T00:00:00+00:00", 0.68)
    >>> store.get_last_state("LOC_001")
    {'risk_level': 'HIGH', 'timestamp': '...', 'probability': 0.68}
    >>> store.clear_state("LOC_001")
    >>> store.get_last_state("LOC_001") is None
    True
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._store: dict[str, _StateRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_last_state(self, target_id: str) -> Optional[_StateRecord]:
        """
        Return the last recorded state for *target_id*, or ``None``.

        Parameters
        ----------
        target_id : str
            Unique location / target identifier.

        Returns
        -------
        dict | None
            ``{'risk_level': str, 'timestamp': str, 'probability': float}``
            or ``None`` if the target has never been evaluated.
        """
        with self._lock:
            record = self._store.get(target_id)
            # Return a shallow copy to prevent external mutation
            return dict(record) if record is not None else None

    def update_state(
        self,
        target_id:   str,
        risk_level:  str,
        timestamp:   str,
        probability: float,
    ) -> None:
        """
        Upsert the current evaluation state for *target_id*.

        Parameters
        ----------
        target_id   : str   — unique location identifier
        risk_level  : str   — canonical risk label (LOW/MODERATE/HIGH/CRITICAL)
        timestamp   : str   — ISO 8601 UTC string of the evaluation moment
        probability : float — raw susceptibility probability in [0.0, 1.0]
        """
        with self._lock:
            self._store[target_id] = {
                "risk_level":  risk_level,
                "timestamp":   timestamp,
                "probability": float(probability),
            }
        logger.debug(
            "TargetStateStore: updated target='%s' risk_level='%s' p=%.4f",
            target_id, risk_level, probability,
        )

    def clear_state(self, target_id: Optional[str] = None) -> None:
        """
        Clear stored state.

        Parameters
        ----------
        target_id : str | None
            When provided, removes only that target's state.
            When ``None`` (default), clears **all** stored states.
        """
        with self._lock:
            if target_id is None:
                self._store.clear()
                logger.debug("TargetStateStore: cleared all states")
            elif target_id in self._store:
                del self._store[target_id]
                logger.debug(
                    "TargetStateStore: cleared state for target='%s'", target_id
                )

    # ------------------------------------------------------------------
    # Diagnostics (not part of public contract — for debugging only)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of targets currently tracked."""
        with self._lock:
            return len(self._store)

    def __repr__(self) -> str:  # pragma: no cover
        with self._lock:
            return f"TargetStateStore(targets={list(self._store.keys())})"
