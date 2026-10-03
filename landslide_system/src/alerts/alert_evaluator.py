# src/alerts/alert_evaluator.py
"""
Phase 8.2 — Alert Event Detection & Transition Engine
======================================================

Consumes authoritative Phase-5/FC-4 risk results, tracks historical
target states via TargetStateStore, classifies state transitions
(INITIAL_TRIGGER, ESCALATION, DE_ESCALATION, RECOVERY,
PERSISTENT_UNCHANGED, SUPPRESSED), and delegates safety gating to
AlertPolicyEngine (Phase 8.1) to produce deterministic AlertEvent
payloads.

No external notifications are dispatched in this phase.

State Transition Matrix
-----------------------
Previous         Current     Transition
─────────────────────────────────────────────────────────
None / LOW /     HIGH or     INITIAL_TRIGGER
MODERATE         CRITICAL

HIGH             CRITICAL    ESCALATION

CRITICAL         HIGH        DE_ESCALATION
HIGH/CRITICAL    MOD/LOW     RECOVERY

HIGH             HIGH        PERSISTENT_UNCHANGED
CRITICAL         CRITICAL    PERSISTENT_UNCHANGED

LOW/MODERATE     LOW/MOD     UNCHANGED_SAFE  (SUPPRESSED)
"""

from __future__ import annotations

import datetime
import logging
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from src.alerts.alert_policy import AlertDecision, AlertPolicyEngine
from src.alerts.state_store import TargetStateStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Risk-level ordering helpers
# ---------------------------------------------------------------------------

# Numeric severity used to compare risk levels
_SEVERITY: dict[str, int] = {
    "LOW":      1,
    "MODERATE": 2,
    "HIGH":     3,
    "CRITICAL": 4,
}

_ACTIONABLE_RISK_LEVELS = {"HIGH", "CRITICAL"}
_SAFE_RISK_LEVELS       = {"LOW", "MODERATE"}

# Valid canonical risk levels (used for fallback classification)
_VALID_RISK_LEVELS = set(_SEVERITY.keys())


def _severity(level: str) -> int:
    """Return the numeric severity for a risk level string."""
    return _SEVERITY.get(level.upper(), 0)


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class AlertEvent(BaseModel):
    """
    Immutable output produced by AlertEvaluator.evaluate_target_risk().

    Fields
    ------
    alert_id : str
        UUID v4 uniquely identifying this event.
    target_id : str
        Location/target identifier.
    event_emitted : bool
        True only when the transition warrants an actionable notification
        AND all Phase 8.1 gating rules pass.
    event_type : str
        One of:
          INITIAL_TRIGGER      – first HIGH/CRITICAL after safe state
          ESCALATION           – HIGH → CRITICAL
          DE_ESCALATION        – CRITICAL → HIGH
          RECOVERY             – HIGH/CRITICAL → MODERATE/LOW
          PERSISTENT_UNCHANGED – same actionable level repeated
          SUPPRESSED           – gating blocked or non-actionable level
    previous_risk_level : Optional[str]
        Risk level from the last stored state (None if first evaluation).
    current_risk_level : str
        Risk level from the current risk_response.
    probability : float
        Raw susceptibility probability.
    trigger_reason : str
        Human-readable summary of why the event was (or was not) emitted.
    triggered_at : str
        UTC ISO 8601 timestamp of this evaluation.
    model_version : str
        Model version string from the risk_response.
    risk_evaluation_timestamp : str
        Timestamp of the risk evaluation inside the risk_response.
    data_quality : str
        Data quality flag from the risk_response.
    stale : bool
        Whether the dynamic data was considered stale.
    policy_decision : AlertDecision
        Full Phase 8.1 gating decision embedded for transparency.
    """
    alert_id:                   str  = Field(default_factory=lambda: str(uuid.uuid4()))
    target_id:                  str
    event_emitted:              bool
    event_type:                 str
    previous_risk_level:        Optional[str]
    current_risk_level:         str
    probability:                float
    trigger_reason:             str
    triggered_at:               str
    model_version:              str
    risk_evaluation_timestamp:  str
    data_quality:               str
    stale:                      bool
    policy_decision:            AlertDecision


# ---------------------------------------------------------------------------
# Transition classifier
# ---------------------------------------------------------------------------

def _classify_transition(
    previous_level: Optional[str],
    current_level:  str,
) -> str:
    """
    Return the transition type string given previous and current risk levels.

    Parameters
    ----------
    previous_level : str | None
        Last recorded risk level, or None if this is the first evaluation.
    current_level : str
        Current risk level.

    Returns
    -------
    str — one of INITIAL_TRIGGER | ESCALATION | DE_ESCALATION | RECOVERY |
                 PERSISTENT_UNCHANGED | UNCHANGED_SAFE
    """
    curr = current_level.upper()

    # No prior state → any actionable level is an initial trigger
    if previous_level is None:
        if curr in _ACTIONABLE_RISK_LEVELS:
            return "INITIAL_TRIGGER"
        return "UNCHANGED_SAFE"

    prev = previous_level.upper()

    if prev == curr:
        if curr in _ACTIONABLE_RISK_LEVELS:
            return "PERSISTENT_UNCHANGED"
        return "UNCHANGED_SAFE"

    prev_sev = _severity(prev)
    curr_sev = _severity(curr)

    # Escalation: HIGH → CRITICAL
    if prev == "HIGH" and curr == "CRITICAL":
        return "ESCALATION"

    # De-escalation: CRITICAL → HIGH
    if prev == "CRITICAL" and curr == "HIGH":
        return "DE_ESCALATION"

    # Recovery: was actionable, now safe
    if prev in _ACTIONABLE_RISK_LEVELS and curr in _SAFE_RISK_LEVELS:
        return "RECOVERY"

    # First-time entry into actionable from safe (covers MODERATE→HIGH etc.)
    if prev in _SAFE_RISK_LEVELS and curr in _ACTIONABLE_RISK_LEVELS:
        return "INITIAL_TRIGGER"

    # Catch-all: if severity went up it is a general escalation path
    if curr_sev > prev_sev:
        return "ESCALATION"

    # Severity went down but didn't match specific cases above
    return "RECOVERY"


# ---------------------------------------------------------------------------
# AlertEvaluator
# ---------------------------------------------------------------------------

class AlertEvaluator:
    """
    Stateful evaluator that combines transition detection with Phase 8.1
    policy gating to produce deterministic AlertEvent payloads.

    Parameters
    ----------
    policy_engine : AlertPolicyEngine | None
        Phase 8.1 gating engine.  Instantiated with default config when
        not provided.
    state_store : TargetStateStore | None
        In-memory state store.  A fresh store is created when not provided.
    policy_path : str | Path | None
        Path to alert_policy.yaml, forwarded to the engine when
        ``policy_engine`` is not supplied explicitly.

    Usage
    -----
    >>> evaluator = AlertEvaluator()
    >>> event = evaluator.evaluate_target_risk("LOC_001", risk_response)
    >>> print(event.event_type, event.event_emitted)
    """

    def __init__(
        self,
        policy_engine: Optional[AlertPolicyEngine] = None,
        state_store:   Optional[TargetStateStore]  = None,
        policy_path:   Optional[str | Path]        = None,
    ) -> None:
        # Use `is not None` guards — TargetStateStore defines __len__ so an empty
        # store is falsy; `store or TargetStateStore()` would silently discard it.
        self._engine = policy_engine if policy_engine is not None else AlertPolicyEngine(policy_path=policy_path)
        self._store  = state_store  if state_store  is not None else TargetStateStore()

    # ------------------------------------------------------------------
    # Convenience accessors (allow tests to inspect internals)
    # ------------------------------------------------------------------

    @property
    def state_store(self) -> TargetStateStore:
        return self._store

    @property
    def policy_engine(self) -> AlertPolicyEngine:
        return self._engine

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    def evaluate_target_risk(
        self,
        target_id:     str,
        risk_response: dict,
        target_config: Optional[dict] = None,
    ) -> AlertEvent:
        """
        Evaluate a risk_response for a given target and return an AlertEvent.

        Parameters
        ----------
        target_id : str
            Unique location / target identifier.
        risk_response : dict
            Must include at minimum:
                status          : str
                risk_level      : str
                probability     : float
                data_quality    : str
                stale           : bool
                model_version   : str
                data_timestamp  : str (ISO 8601 UTC)
        target_config : dict | None
            Optional per-location overrides forwarded to AlertPolicyEngine.

        Returns
        -------
        AlertEvent
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # ----------------------------------------------------------------
        # 1. Extract fields from risk_response
        # ----------------------------------------------------------------
        current_risk_level = str(risk_response.get("risk_level", "")).upper()
        probability        = float(risk_response.get("probability", 0.0))
        data_quality       = str(risk_response.get("data_quality", "UNKNOWN")).upper()
        stale              = bool(risk_response.get("stale", False))
        model_version      = str(risk_response.get("model_version", ""))
        eval_timestamp     = str(
            risk_response.get("data_timestamp") or
            risk_response.get("timestamp") or
            now_utc
        )

        # Inject target_id into the risk_response for the gating engine
        enriched_rr = {**risk_response, "target_id": target_id}

        # ----------------------------------------------------------------
        # 2. Fetch previous state from the store
        # ----------------------------------------------------------------
        previous_state      = self._store.get_last_state(target_id)
        previous_risk_level: Optional[str] = (
            previous_state["risk_level"] if previous_state else None
        )

        # ----------------------------------------------------------------
        # 3. Classify the state transition
        # ----------------------------------------------------------------
        transition = _classify_transition(previous_risk_level, current_risk_level)

        logger.info(
            "AlertEvaluator: target='%s' prev=%s curr=%s transition=%s",
            target_id, previous_risk_level, current_risk_level, transition,
        )

        # ----------------------------------------------------------------
        # 4. Evaluate Phase 8.1 safety gating
        # ----------------------------------------------------------------
        policy_decision = self._engine.evaluate_alert(enriched_rr, target_config)

        # ----------------------------------------------------------------
        # 5. Determine whether to emit the event
        # ----------------------------------------------------------------
        event_emitted, event_type, trigger_reason = self._resolve_emission(
            transition=transition,
            policy_decision=policy_decision,
            current_risk_level=current_risk_level,
            previous_risk_level=previous_risk_level,
        )

        # ----------------------------------------------------------------
        # 6. Update state store (only for valid/successful evaluations)
        # ----------------------------------------------------------------
        if risk_response.get("status", "").lower() == "success":
            self._store.update_state(
                target_id   = target_id,
                risk_level  = current_risk_level,
                timestamp   = now_utc,
                probability = probability,
            )

        # ----------------------------------------------------------------
        # 7. Build and return AlertEvent
        # ----------------------------------------------------------------
        event = AlertEvent(
            target_id                 = target_id,
            event_emitted             = event_emitted,
            event_type                = event_type,
            previous_risk_level       = previous_risk_level,
            current_risk_level        = current_risk_level,
            probability               = round(probability, 6),
            trigger_reason            = trigger_reason,
            triggered_at              = now_utc,
            model_version             = model_version,
            risk_evaluation_timestamp = eval_timestamp,
            data_quality              = data_quality,
            stale                     = stale,
            policy_decision           = policy_decision,
        )

        logger.info(
            "AlertEvaluator: event_type=%s event_emitted=%s target='%s'",
            event.event_type, event.event_emitted, target_id,
        )
        return event

    # ------------------------------------------------------------------
    # Internal: emission resolution logic
    # ------------------------------------------------------------------

    def _resolve_emission(
        self,
        transition:         str,
        policy_decision:    AlertDecision,
        current_risk_level: str,
        previous_risk_level: Optional[str],
    ) -> tuple[bool, str, str]:
        """
        Decide whether to emit the event based on transition type and
        policy gating outcome.

        Returns
        -------
        (event_emitted: bool, event_type: str, trigger_reason: str)
        """
        # ---- PERSISTENT_UNCHANGED: suppress duplicates by default ----
        if transition == "PERSISTENT_UNCHANGED":
            reason = (
                f"PERSISTENT_STATE_UNCHANGED: Risk level has remained "
                f"{current_risk_level} since last evaluation. "
                "No new alert event emitted."
            )
            return False, "PERSISTENT_UNCHANGED", reason

        # ---- UNCHANGED_SAFE (LOW/MOD → LOW/MOD): always suppress ----
        if transition == "UNCHANGED_SAFE":
            reason = (
                f"Risk level {current_risk_level} is within safe bounds "
                "and is unchanged. No alert event emitted."
            )
            return False, "SUPPRESSED", reason

        # ---- RECOVERY / DE_ESCALATION ----
        if transition in ("RECOVERY", "DE_ESCALATION"):
            reason = (
                f"{transition}: Risk level transitioned from "
                f"{previous_risk_level} → {current_risk_level}. "
                "Recovery event recorded."
            )
            return True, transition, reason

        # ---- INITIAL_TRIGGER / ESCALATION: subject to policy gating ----
        if transition in ("INITIAL_TRIGGER", "ESCALATION"):
            if policy_decision.alert_triggered:
                reason = (
                    f"{transition}: {policy_decision.reason}"
                )
                return True, transition, reason
            else:
                # Policy suppressed the alert — report SUPPRESSED
                reason = (
                    f"SUPPRESSED ({transition}): {policy_decision.reason}"
                )
                return False, "SUPPRESSED", reason

        # ---- Fallback (should not be reached) ----
        return False, "SUPPRESSED", f"Unhandled transition type: {transition}"
