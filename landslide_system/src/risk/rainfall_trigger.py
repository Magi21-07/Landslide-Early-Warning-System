"""
src/risk/rainfall_trigger.py
-----------------------------
Phase 5.5: Rainfall Trigger Engine.

Evaluates engineered rainfall features (from Phase 5.4) against configurable
YAML thresholds and emits a deterministic Trigger State.

Rule: Highest severity wins across all evaluated features.
Missing feature values (None) are skipped — never treated as 0.

NO alert dispatch, NO hardcoded thresholds, NO scientific calibration claims.
"""

import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

TRIGGER_STATES  = ["NORMAL", "WATCH", "WARNING", "CRITICAL"]
TRIGGER_SCORES  = {s: i for i, s in enumerate(TRIGGER_STATES)}
# NORMAL=0, WATCH=1, WARNING=2, CRITICAL=3

# Ordered list of sub-thresholds within each feature, highest first
_SEVERITY_LADDER = [
    ("critical", "CRITICAL"),
    ("warning",  "WARNING"),
    ("watch",    "WATCH"),
]

# Human-readable label for each feature key
_FEATURE_LABELS: Dict[str, str] = {
    "rainfall_1d":  "1-day cumulative rainfall",
    "rainfall_3d":  "3-day cumulative rainfall",
    "rainfall_7d":  "7-day cumulative rainfall",
    "rainfall_15d": "15-day cumulative rainfall",
}


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

@dataclass
class TriggerResult:
    """
    Structured output from RainfallTriggerEngine.evaluate().

    Attributes
    ----------
    trigger_state   : 'NORMAL', 'WATCH', 'WARNING', or 'CRITICAL'.
    trigger_score   : Integer severity (NORMAL=0 … CRITICAL=3).
    trigger_reasons : List of human-readable threshold breach descriptions.
    features_evaluated : Number of features with non-None values assessed.
    """
    trigger_state:      str
    trigger_score:      int
    trigger_reasons:    List[str]
    features_evaluated: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RainfallTriggerEngine:
    """
    Maps rainfall features against YAML-configured thresholds.

    Parameters
    ----------
    config_path : str, optional
        Path to the YAML threshold configuration file.
        Defaults to 'config/rainfall_thresholds.yaml' (relative to project root).
    """

    _DEFAULT_CONFIG = "config/rainfall_thresholds.yaml"

    def __init__(self, config_path: str = None):
        path = config_path or self._resolve_default_config()
        self._thresholds = self._load_config(path)
        logger.info(
            "RainfallTriggerEngine loaded thresholds from: %s  "
            "(%d feature(s) configured)",
            path, len(self._thresholds)
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def evaluate(self, features: Union[Dict[str, Any], Any]) -> TriggerResult:
        """
        Evaluate rainfall features and return a TriggerResult.

        Parameters
        ----------
        features : dict or RainfallFeatureSet (Phase 5.4 dataclass)
            Must contain at least one of: rainfall_1d, rainfall_3d,
            rainfall_7d, rainfall_15d.
            May also contain partial_day_flag (bool).

        Returns
        -------
        TriggerResult
        """
        # Normalise input to dict — use getattr so class-level attrs (plain classes) work too
        if isinstance(features, dict):
            feat_dict = features
        elif hasattr(features, '__dict__') and not isinstance(features, type):
            # dataclass, plain class instance, or any object with instance __dict__
            all_keys = list(_FEATURE_LABELS.keys()) + ["partial_day_flag"]
            feat_dict = {k: getattr(features, k, None) for k in all_keys}
        else:
            raise TypeError(
                "features must be a dict or object instance (e.g., RainfallFeatureSet). "
                f"Got: {type(features).__name__}"
            )

        highest_score  = 0          # NORMAL
        reasons:  List[str] = []
        evaluated = 0

        for feat_key, label in _FEATURE_LABELS.items():
            value = feat_dict.get(feat_key)

            # Skip missing / None values — never treat as zero
            if value is None:
                logger.debug("Skipping %s: value is None.", feat_key)
                continue

            feat_thresholds = self._thresholds.get(feat_key)
            if feat_thresholds is None:
                logger.warning(
                    "No threshold configured for feature '%s'. Skipping.", feat_key
                )
                continue

            evaluated += 1
            value_f = float(value)

            # Walk from most severe → least severe; first match wins per feature
            for thresh_key, state in _SEVERITY_LADDER:
                limit = float(feat_thresholds[thresh_key])
                if value_f >= limit:
                    score = TRIGGER_SCORES[state]
                    reasons.append(
                        f"{label} ({value_f:.1f} mm) exceeded "
                        f"{thresh_key} threshold ({limit:.1f} mm)"
                    )
                    if score > highest_score:
                        highest_score = score
                    break   # Only report the highest breach per feature

        # Partial-day flag annotation
        if feat_dict.get("partial_day_flag") is True:
            reasons.append(
                "Note: 1-day evaluation based on incomplete current-day data."
            )

        # Default reason if nothing was breached
        if highest_score == 0 and not any(
            r.startswith("Note:") for r in reasons
        ):
            reasons = ["Rainfall within safe limits."]
            if feat_dict.get("partial_day_flag") is True:
                reasons.append(
                    "Note: 1-day evaluation based on incomplete current-day data."
                )

        final_state = TRIGGER_STATES[highest_score]

        logger.info(
            "Trigger evaluation complete: state=%s score=%d reasons=%d "
            "features_evaluated=%d",
            final_state, highest_score, len(reasons), evaluated
        )

        return TriggerResult(
            trigger_state      = final_state,
            trigger_score      = highest_score,
            trigger_reasons    = reasons,
            features_evaluated = evaluated,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @classmethod
    def _resolve_default_config(cls) -> str:
        """Resolve the default config path relative to the project root."""
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..')
        )
        return os.path.join(root, cls._DEFAULT_CONFIG)

    @staticmethod
    def _load_config(path: str) -> Dict[str, Dict[str, float]]:
        """Load and validate the YAML threshold config. Uses yaml.safe_load()."""
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required for RainfallTriggerEngine. "
                "Install with: pip install pyyaml"
            ) from exc

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Threshold config not found: {path}"
            )

        with open(path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict) or 'thresholds' not in raw:
            raise ValueError(
                "YAML config must have a top-level 'thresholds' key."
            )

        thresholds = raw['thresholds']

        # Validate each feature has watch / warning / critical
        for feat, cfg in thresholds.items():
            for level in ('watch', 'warning', 'critical'):
                if level not in cfg:
                    raise ValueError(
                        f"Missing '{level}' under thresholds.{feat} in {path}"
                    )

        return thresholds
