# src/alerts/alert_policy.py
"""
Phase 8.1 / Phase 8.1 Ext — Alert Policy & Severity Engine
===========================================================

Evaluates a completed RiskResponse against configurable alert policies and
safety gates to produce a deterministic AlertDecision.

Phase 8.1 Ext adds native Telegram alert policy support:
  - Reads config/telegram_alert_policy.yaml for Telegram-specific gating.
  - Stamps telegram_alert_level, telegram_chat_id, telegram_enabled onto
    every AlertDecision (backwards-compatible defaults when Telegram is not
    configured).
  - No HTTP requests to api.telegram.org are made in this phase.

No external notification APIs (SMTP, Twilio, Slack, webhooks) are invoked
in this phase.  The engine is a pure-function evaluation layer.

Locked risk thresholds (Phase 5 / FC-4 — DO NOT ALTER):
    LOW:      probability < 0.30
    MODERATE: probability < 0.55
    HIGH:     probability < 0.75
    CRITICAL: probability >= 0.75

Alert policy severity mapping:
    LOW      -> NONE        (no alert)
    MODERATE -> MONITORING  (internal logging only)
    HIGH     -> WARNING     (configurable alert generated)
    CRITICAL -> IMMEDIATE   (configurable alert generated)

Telegram alert mapping:
    LOW      -> NO_ALERT
    MODERATE -> NO_ALERT
    HIGH     -> TELEGRAM_WARNING
    CRITICAL -> TELEGRAM_CRITICAL
"""

from __future__ import annotations

import datetime
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
_DEFAULT_POLICY_PATH = os.path.join(_PROJECT_ROOT, 'config', 'alert_policy.yaml')
_DEFAULT_TELEGRAM_POLICY_PATH = os.path.join(
    _PROJECT_ROOT, 'config', 'telegram_alert_policy.yaml'
)

# Locked risk thresholds — MUST NOT be altered (Phase 5 / FC-4)
_RISK_THRESHOLDS: dict[str, tuple[float, float]] = {
    "LOW":      (0.00, 0.30),
    "MODERATE": (0.30, 0.55),
    "HIGH":     (0.55, 0.75),
    "CRITICAL": (0.75, 1.00),
}

# Valid alert levels in ascending severity order
_VALID_ALERT_LEVELS = ("NONE", "MONITORING", "WARNING", "IMMEDIATE")

# Valid Telegram-specific alert levels
_VALID_TELEGRAM_ALERT_LEVELS = ("NO_ALERT", "TELEGRAM_WARNING", "TELEGRAM_CRITICAL")

# Risk levels that produce an actionable alert (subject to gating)
_ACTIONABLE_RISK_LEVELS = {"HIGH", "CRITICAL"}


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class AlertDecision(BaseModel):
    """
    Immutable output record produced by AlertPolicyEngine.evaluate_alert().

    Fields
    ------
    alert_triggered : bool
        True only when ALL gating rules pass and risk_level is HIGH/CRITICAL.
    alert_level : str
        One of NONE | MONITORING | WARNING | IMMEDIATE.
    triggering_risk_level : str
        Canonical risk label: LOW | MODERATE | HIGH | CRITICAL.
    probability : float
        Raw susceptibility probability from the RiskResponse.
    reason : str
        Human-readable explanation of the decision (or suppression cause).
    data_quality : str
        Data quality flag forwarded from the RiskResponse.
    stale : bool
        Whether the dynamic data timestamp exceeded max_staleness_hours.
    allowed_channels : List[str]
        Notification channels permitted for this alert level per policy.
        Empty list when alert_triggered is False.
    triggered_at : str
        UTC ISO 8601 timestamp of when this decision was produced.
    target_id : Optional[str]
        Location / target identifier, if available.

    # ── Phase 8.1 Ext: Telegram fields (backwards-compatible defaults) ──────
    telegram_alert_level : str
        One of NO_ALERT | TELEGRAM_WARNING | TELEGRAM_CRITICAL.
        Defaults to NO_ALERT when Telegram policy is not loaded or gating fails.
    telegram_chat_id : Optional[str]
        Resolved Telegram Chat ID for this target, or None when unavailable.
    telegram_enabled : bool
        True when the Telegram policy is loaded, enabled, and all gating passes.
    """
    alert_triggered:       bool
    alert_level:           str
    triggering_risk_level: str
    probability:           float
    reason:                str
    data_quality:          str
    stale:                 bool
    allowed_channels:      List[str] = Field(default_factory=list)
    triggered_at:          str
    target_id:             Optional[str] = None
    # Phase 8.1 Ext — Telegram (backwards-compatible: safe defaults)
    telegram_alert_level:  str            = "NO_ALERT"
    telegram_chat_id:      Optional[str]  = None
    telegram_enabled:      bool           = False


# ---------------------------------------------------------------------------
# Policy loader
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def _load_policy(policy_path: str) -> dict:
    """
    Load and validate alert_policy.yaml.  Cached per path.

    Returns the raw dict with guaranteed required keys.
    """
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required. Install with: pip install pyyaml"
        ) from exc

    if not os.path.exists(policy_path):
        raise FileNotFoundError(
            f"Alert policy config not found: {policy_path}"
        )

    with open(policy_path, 'r', encoding='utf-8') as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError("alert_policy.yaml must be a YAML mapping.")

    required_keys = {
        'max_staleness_hours',
        'require_valid_dynamic_data',
        'active_model_version',
        'risk_alert_mapping',
        'channels',
        'cooldown_minutes',
    }
    missing = required_keys - set(raw.keys())
    if missing:
        raise ValueError(
            f"alert_policy.yaml is missing required keys: {sorted(missing)}"
        )

    logger.debug("alert_policy.yaml loaded from: %s", policy_path)
    return raw


@lru_cache(maxsize=4)
def _load_telegram_policy(telegram_policy_path: str) -> dict:
    """
    Load and validate telegram_alert_policy.yaml.  Cached per path.

    Returns the raw dict on success, or raises FileNotFoundError / ValueError.
    The caller is responsible for deciding whether a missing Telegram policy
    is fatal (it is not — Telegram gating simply stays suppressed).
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PyYAML is required. Install with: pip install pyyaml"
        ) from exc

    if not os.path.exists(telegram_policy_path):
        raise FileNotFoundError(
            f"Telegram policy config not found: {telegram_policy_path}"
        )

    with open(telegram_policy_path, 'r', encoding='utf-8') as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError("telegram_alert_policy.yaml must be a YAML mapping.")

    required_keys = {
        'enabled',
        'minimum_risk_level',
        'bot_token_env_var',
        'default_chat_id_env_var',
        'max_staleness_hours',
        'allow_stale_alerts',
        'risk_alert_mapping',
    }
    missing = required_keys - set(raw.keys())
    if missing:
        raise ValueError(
            f"telegram_alert_policy.yaml is missing required keys: {sorted(missing)}"
        )

    logger.debug("telegram_alert_policy.yaml loaded from: %s", telegram_policy_path)
    return raw


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _classify_risk_level(probability: float) -> str:
    """
    Classify a probability score using the LOCKED Phase-5/FC-4 thresholds.

    Thresholds (inclusive upper, exclusive lower except LOW):
        LOW:      [0.00, 0.30)
        MODERATE: [0.30, 0.55)
        HIGH:     [0.55, 0.75)
        CRITICAL: [0.75, 1.00]
    """
    if probability >= 0.75:
        return "CRITICAL"
    if probability >= 0.55:
        return "HIGH"
    if probability >= 0.30:
        return "MODERATE"
    return "LOW"


def _suppressed_decision(
    *,
    alert_level:           str,
    triggering_risk_level: str,
    probability:           float,
    reason:                str,
    data_quality:          str,
    stale:                 bool,
    target_id:             Optional[str],
    # Phase 8.1 Ext — Telegram fields (safe defaults keep existing callers intact)
    telegram_alert_level:  str           = "NO_ALERT",
    telegram_chat_id:      Optional[str] = None,
    telegram_enabled:      bool          = False,
) -> AlertDecision:
    """Convenience constructor for a suppressed (alert_triggered=False) decision."""
    return AlertDecision(
        alert_triggered       = False,
        alert_level           = alert_level,
        triggering_risk_level = triggering_risk_level,
        probability           = round(probability, 6),
        reason                = reason,
        data_quality          = data_quality,
        stale                 = stale,
        allowed_channels      = [],
        triggered_at          = _now_utc_iso(),
        target_id             = target_id,
        telegram_alert_level  = telegram_alert_level,
        telegram_chat_id      = telegram_chat_id,
        telegram_enabled      = telegram_enabled,
    )


def _resolve_telegram_level(risk_level: str, tpol: dict) -> str:
    """
    Map a canonical risk level to the configured Telegram alert level.

    Returns one of: NO_ALERT | TELEGRAM_WARNING | TELEGRAM_CRITICAL.
    Falls back to NO_ALERT for any unknown key.
    """
    mapping = tpol.get("risk_alert_mapping", {})
    raw     = str(mapping.get(risk_level, "NO_ALERT")).upper()
    return raw if raw in _VALID_TELEGRAM_ALERT_LEVELS else "NO_ALERT"


# ---------------------------------------------------------------------------
# AlertPolicyEngine
# ---------------------------------------------------------------------------

class AlertPolicyEngine:
    """
    Evaluates a RiskResponse dict against alert_policy.yaml gating rules
    and produces a deterministic AlertDecision.

    Parameters
    ----------
    policy_path : str | Path | None
        Path to alert_policy.yaml.  Defaults to the project-root location.

    Usage
    -----
    >>> engine = AlertPolicyEngine()
    >>> decision = engine.evaluate_alert(risk_response, target_config)
    >>> print(decision.alert_triggered, decision.reason)
    """

    def __init__(self, policy_path: Optional[str | Path] = None) -> None:
        self._policy_path = str(policy_path) if policy_path else _DEFAULT_POLICY_PATH
        # Telegram policy defaults to the standard config location unless overridden by user
        self._telegram_policy_path = _DEFAULT_TELEGRAM_POLICY_PATH

    @property
    def policy(self) -> dict:
        """Loaded (and cached) policy dict."""
        return _load_policy(self._policy_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_alert(
        self,
        risk_response: dict,
        target_config: Optional[dict] = None,
    ) -> AlertDecision:
        """
        Evaluate a risk response against all gating rules.

        Parameters
        ----------
        risk_response : dict
            Expected keys (subset used here):
                status          : str   ("success" | "error" | …)
                risk_level      : str   ("LOW" | "MODERATE" | "HIGH" | "CRITICAL")
                probability     : float  [0.0, 1.0]
                data_quality    : str   ("VALID" | "DEGRADED" | "INVALID" | …)
                stale           : bool
                data_timestamp  : str   ISO 8601 UTC — used for staleness check
                model_version   : str   (e.g. "v2")
                target_id       : str   (optional)

        target_config : dict | None
            Optional per-location overrides:
                notifications_enabled : bool  (default True if absent)
                channels              : dict  per-level channel overrides

        Returns
        -------
        AlertDecision
        """
        pol       = self.policy
        tc        = target_config or {}
        target_id = risk_response.get("target_id") or tc.get("target_id")

        # --- Extract core fields from risk_response ---
        status       = str(risk_response.get("status", "")).lower()
        probability  = float(risk_response.get("probability", 0.0))
        data_quality = str(risk_response.get("data_quality", "UNKNOWN")).upper()
        stale        = bool(risk_response.get("stale", False))
        model_ver    = str(risk_response.get("model_version", ""))
        data_ts_raw  = risk_response.get("data_timestamp")

        # Determine risk level — prefer explicit label, derive from probability as fallback
        risk_level_raw = str(risk_response.get("risk_level", "")).upper()
        if risk_level_raw not in _RISK_THRESHOLDS:
            risk_level = _classify_risk_level(probability)
        else:
            risk_level = risk_level_raw

        # Determine alert level from policy mapping
        risk_alert_map = pol.get("risk_alert_mapping", {})
        alert_level    = str(risk_alert_map.get(risk_level, "NONE")).upper()

        # ----------------------------------------------------------------
        # GATE 0 — Non-actionable risk levels (LOW / MODERATE)
        # ----------------------------------------------------------------
        if risk_level not in _ACTIONABLE_RISK_LEVELS:
            reason = (
                f"Risk level {risk_level} does not meet the threshold for alerts. "
                f"Alert level: {alert_level}."
            )
            logger.info(
                "AlertPolicyEngine: non-actionable risk level %s -> %s",
                risk_level, alert_level,
            )
            return _suppressed_decision(
                alert_level           = alert_level,
                triggering_risk_level = risk_level,
                probability           = probability,
                reason                = reason,
                data_quality          = data_quality,
                stale                 = stale,
                target_id             = target_id,
            )

        # ----------------------------------------------------------------
        # GATE 1 — Evaluation status must be "success"
        # ----------------------------------------------------------------
        if status != "success":
            reason = (
                f"ALERT_SUPPRESSED: Evaluation status is '{status}', "
                f"expected 'success'. Alert cannot be triggered on a failed evaluation."
            )
            logger.warning("AlertPolicyEngine: GATE 1 failed — %s", reason)
            return _suppressed_decision(
                alert_level           = alert_level,
                triggering_risk_level = risk_level,
                probability           = probability,
                reason                = reason,
                data_quality          = data_quality,
                stale                 = stale,
                target_id             = target_id,
            )

        # ----------------------------------------------------------------
        # GATE 2 — Dynamic data availability (data_quality != "INVALID")
        # ----------------------------------------------------------------
        if pol.get("require_valid_dynamic_data", True):
            if data_quality == "INVALID":
                reason = (
                    "ALERT_SUPPRESSED: Dynamic data quality is INVALID. "
                    "Required dynamic factors (rainfall, NDVI, SAR proxy) "
                    "are missing or corrupt."
                )
                logger.warning("AlertPolicyEngine: GATE 2 failed — %s", reason)
                return _suppressed_decision(
                    alert_level           = alert_level,
                    triggering_risk_level = risk_level,
                    probability           = probability,
                    reason                = reason,
                    data_quality          = data_quality,
                    stale                 = stale,
                    target_id             = target_id,
                )

        # ----------------------------------------------------------------
        # GATE 3 — Data freshness / staleness
        # ----------------------------------------------------------------
        max_staleness_hours: int = pol.get("max_staleness_hours", 24)

        # Re-derive staleness from timestamp if data_timestamp is available
        if data_ts_raw:
            try:
                data_ts = datetime.datetime.fromisoformat(
                    str(data_ts_raw).replace("Z", "+00:00")
                )
                if data_ts.tzinfo is None:
                    data_ts = data_ts.replace(tzinfo=datetime.timezone.utc)
                age_hours = (
                    datetime.datetime.now(datetime.timezone.utc) - data_ts
                ).total_seconds() / 3600.0
                if age_hours > max_staleness_hours:
                    stale = True
            except (ValueError, TypeError) as exc:
                logger.debug(
                    "AlertPolicyEngine: Could not parse data_timestamp '%s': %s",
                    data_ts_raw, exc,
                )

        if stale:
            reason = (
                f"ALERT_SUPPRESSED: Data stale beyond {max_staleness_hours} hours. "
                "Stale dynamic data cannot be used to trigger an alert."
            )
            logger.warning("AlertPolicyEngine: GATE 3 failed — %s", reason)
            return _suppressed_decision(
                alert_level           = alert_level,
                triggering_risk_level = risk_level,
                probability           = probability,
                reason                = reason,
                data_quality          = data_quality,
                stale                 = True,
                target_id             = target_id,
            )

        # ----------------------------------------------------------------
        # GATE 4 — Model integrity (version must match active_model_version)
        # ----------------------------------------------------------------
        active_model_ver = str(pol.get("active_model_version", "")).strip()
        if active_model_ver and model_ver and model_ver != active_model_ver:
            reason = (
                f"ALERT_SUPPRESSED: Model version mismatch. "
                f"Active model version is '{active_model_ver}', "
                f"but risk response was produced by '{model_ver}'."
            )
            logger.warning("AlertPolicyEngine: GATE 4 failed — %s", reason)
            return _suppressed_decision(
                alert_level           = alert_level,
                triggering_risk_level = risk_level,
                probability           = probability,
                reason                = reason,
                data_quality          = data_quality,
                stale                 = stale,
                target_id             = target_id,
            )

        # ----------------------------------------------------------------
        # GATE 5 — Target notifications_enabled
        # ----------------------------------------------------------------
        notifications_enabled = tc.get("notifications_enabled", True)
        if not notifications_enabled:
            reason = (
                "ALERT_SUPPRESSED: Target notifications disabled. "
                f"Target '{target_id}' has notifications_enabled=False."
            )
            logger.warning("AlertPolicyEngine: GATE 5 failed — %s", reason)
            return _suppressed_decision(
                alert_level           = alert_level,
                triggering_risk_level = risk_level,
                probability           = probability,
                reason                = reason,
                data_quality          = data_quality,
                stale                 = stale,
                target_id             = target_id,
            )

        # ----------------------------------------------------------------
        # GATE 6 — Channel eligibility
        # ----------------------------------------------------------------
        policy_channels: dict = pol.get("channels", {})
        # target_config may override channels per alert level
        tc_channels: dict = tc.get("channels", {})
        merged_channels: dict = {**policy_channels, **tc_channels}

        allowed_channels: list[str] = merged_channels.get(alert_level, [])
        if not allowed_channels:
            reason = (
                f"ALERT_SUPPRESSED: No notification channels configured for "
                f"alert level '{alert_level}'. "
                "Enable at least one channel (email, sms, webhook) in alert_policy.yaml."
            )
            logger.warning("AlertPolicyEngine: GATE 6 failed — %s", reason)
            return _suppressed_decision(
                alert_level           = alert_level,
                triggering_risk_level = risk_level,
                probability           = probability,
                reason                = reason,
                data_quality          = data_quality,
                stale                 = stale,
                target_id             = target_id,
            )

        # ----------------------------------------------------------------
        # All gates passed — alert IS triggered
        # ----------------------------------------------------------------
        reason = (
            f"All gating checks passed. {risk_level} risk (p={probability:.4f}) "
            f"triggers a {alert_level} alert. "
            f"Channels: {', '.join(allowed_channels)}."
        )
        logger.info(
            "AlertPolicyEngine: alert TRIGGERED — level=%s risk=%s p=%.4f",
            alert_level, risk_level, probability,
        )

        # ----------------------------------------------------------------
        # Phase 8.1 Ext — Telegram gating (runs ONLY when primary gates pass)
        # ----------------------------------------------------------------
        tg_level, tg_chat_id, tg_enabled, tg_reason = self._evaluate_telegram(
            risk_level     = risk_level,
            probability    = probability,
            data_quality   = data_quality,
            stale          = stale,
            target_config  = tc,
            target_id      = target_id,
        )

        # Telegram gating failure does NOT suppress the primary alert —
        # it only nullifies the Telegram-specific fields.
        final_reason = reason
        if not tg_enabled and tg_reason:
            final_reason = f"{reason} | TELEGRAM: {tg_reason}"

        return AlertDecision(
            alert_triggered       = True,
            alert_level           = alert_level,
            triggering_risk_level = risk_level,
            probability           = round(probability, 6),
            reason                = final_reason,
            data_quality          = data_quality,
            stale                 = stale,
            allowed_channels      = list(allowed_channels),
            triggered_at          = _now_utc_iso(),
            target_id             = target_id,
            telegram_alert_level  = tg_level,
            telegram_chat_id      = tg_chat_id,
            telegram_enabled      = tg_enabled,
        )

    # ------------------------------------------------------------------
    # Phase 8.1 Ext — Telegram gating
    # ------------------------------------------------------------------

    def _evaluate_telegram(
        self,
        *,
        risk_level:    str,
        probability:   float,
        data_quality:  str,
        stale:         bool,
        target_config: dict,
        target_id:     Optional[str],
    ) -> tuple[str, Optional[str], bool, str]:
        """
        Evaluate the Telegram-specific gating rules.

        Returns
        -------
        (telegram_alert_level, telegram_chat_id, telegram_enabled, reason)

        telegram_enabled is True only when ALL Telegram gates pass.
        """
        _suppress = lambda reason: ("NO_ALERT", None, False, reason)

        # --- Load Telegram policy (graceful fallback if file absent) ---
        tpol_path = self._telegram_policy_path
        try:
            tpol = _load_telegram_policy(tpol_path)
        except FileNotFoundError:
            logger.debug(
                "AlertPolicyEngine: Telegram policy not found at '%s' — "
                "Telegram alerting disabled.", tpol_path,
            )
            return _suppress("Telegram policy file not found.")
        except (ValueError, Exception) as exc:  # pragma: no cover
            logger.warning(
                "AlertPolicyEngine: Failed to load Telegram policy: %s", exc
            )
            return _suppress(f"Telegram policy load error: {exc}")

        # TELEGRAM GATE 1 — master enabled switch
        if not tpol.get("enabled", False):
            return _suppress(
                "TELEGRAM_SUPPRESSED: Telegram alerts disabled in policy "
                "(enabled: false)."
            )

        # TELEGRAM GATE 2 — minimum risk level
        min_level   = str(tpol.get("minimum_risk_level", "HIGH")).upper()
        _sev: dict[str, int] = {
            "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4
        }
        if _sev.get(risk_level, 0) < _sev.get(min_level, 3):
            return _suppress(
                f"TELEGRAM_SUPPRESSED: Risk level {risk_level} is below "
                f"minimum_risk_level ({min_level})."
            )

        # TELEGRAM GATE 3 — data quality must not be INVALID
        if data_quality == "INVALID":
            return _suppress(
                "TELEGRAM_SUPPRESSED: Dynamic data quality is INVALID. "
                "Telegram alert requires valid dynamic data."
            )

        # TELEGRAM GATE 4 — staleness
        if not tpol.get("allow_stale_alerts", False) and stale:
            max_h = tpol.get("max_staleness_hours", 24)
            return _suppress(
                f"TELEGRAM_SUPPRESSED: Data stale beyond {max_h} hours. "
                "allow_stale_alerts is false."
            )

        # TELEGRAM GATE 5 — per-target Telegram notifications flag
        tg_notif_enabled = target_config.get("telegram_notifications_enabled", True)
        if not tg_notif_enabled:
            return _suppress(
                "TELEGRAM_SUPPRESSED: Target has "
                "telegram_notifications_enabled=False."
            )

        # TELEGRAM GATE 6 — resolve chat ID
        #   Priority: target_config.telegram_chat_id > env-var fallback name
        chat_id: Optional[str] = (
            target_config.get("telegram_chat_id")
            or os.environ.get(tpol.get("default_chat_id_env_var", ""), "")
            or None
        )
        if not chat_id:
            return _suppress(
                "TELEGRAM_SUPPRESSED: Missing Telegram chat ID. "
                "Set target_config.telegram_chat_id or the env var "
                f"'{tpol.get('default_chat_id_env_var', 'TELEGRAM_CHAT_ID')}'."
            )

        # All Telegram gates passed
        tg_level = _resolve_telegram_level(risk_level, tpol)
        logger.info(
            "AlertPolicyEngine: Telegram ENABLED — level=%s chat_id=%s risk=%s",
            tg_level, chat_id, risk_level,
        )
        return tg_level, chat_id, True, ""
