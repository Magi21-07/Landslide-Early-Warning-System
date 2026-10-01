"""
src/risk/risk_engine.py
------------------------
Phase 5.6: Combined Susceptibility and Rainfall Risk Engine.

Combines the static Phase-4 ML susceptibility output with the dynamic
Phase-5.5 Rainfall Trigger State to produce a single, operationally
meaningful Final Risk Level via a 2D YAML-driven decision matrix.

NO retraining, NO ML prediction here, NO web endpoints, NO alert dispatch.
"""

import os
import datetime
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid domain values (for validation)
# ---------------------------------------------------------------------------

VALID_SUSCEPTIBILITY_CLASSES = {
    "VERY_LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH"
}
VALID_TRIGGER_STATES = {"NORMAL", "WATCH", "WARNING", "CRITICAL"}
VALID_RISK_LEVELS    = {"MINIMAL", "LOW", "MODERATE", "HIGH", "SEVERE"}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class RiskMatrixLookupError(KeyError):
    """Raised when the risk matrix does not contain the requested combination."""


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

@dataclass
class DynamicRiskAssessment:
    """
    Structured output from DynamicRiskEngine.assess().

    Fields
    ------
    latitude, longitude          : Geographic coordinates (WGS84).
    susceptibility_probability   : ML model output probability (0.0 – 1.0).
    susceptibility_class         : 5-tier ML susceptibility label.
    rainfall_trigger_state       : Trigger engine state (NORMAL … CRITICAL).
    rainfall_trigger_score       : Integer severity (0=NORMAL … 3=CRITICAL).
    final_risk_level             : Operational risk level from the 2D matrix.
    reasons                      : Human-readable explanation list.
    timestamp                    : UTC ISO 8601 string of assessment creation.
    """
    latitude:                 float
    longitude:                float
    susceptibility_probability: float
    susceptibility_class:     str
    rainfall_trigger_state:   str
    rainfall_trigger_score:   int
    final_risk_level:         str
    reasons:                  List[str]
    timestamp:                str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DynamicRiskEngine:
    """
    Combines static ML susceptibility with dynamic rainfall trigger via a
    2D decision matrix loaded from YAML.

    Parameters
    ----------
    config_path : str, optional
        Path to risk_rules.yaml. Defaults to 'config/risk_rules.yaml'
        relative to the project root.
    """

    _DEFAULT_CONFIG = "config/risk_rules.yaml"

    def __init__(self, config_path: str = None):
        path = config_path or self._resolve_default_config()
        self._matrix = self._load_config(path)
        logger.info(
            "DynamicRiskEngine loaded risk matrix from: %s  "
            "(%d susceptibility classes)",
            path, len(self._matrix)
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def assess(
        self,
        latitude:                 float,
        longitude:                float,
        susceptibility_probability: float,
        susceptibility_class:     str,
        rainfall_trigger_state:   str,
        rainfall_trigger_score:   int,
        rainfall_reasons:         List[str],
    ) -> DynamicRiskAssessment:
        """
        Produce a DynamicRiskAssessment combining ML susceptibility and
        rainfall trigger state.

        Parameters
        ----------
        latitude, longitude              : WGS84 coordinates.
        susceptibility_probability       : Float in [0, 1] from LandslidePredictor.
        susceptibility_class             : One of VERY_LOW … VERY_HIGH.
        rainfall_trigger_state           : One of NORMAL, WATCH, WARNING, CRITICAL.
        rainfall_trigger_score           : Integer 0–3 (from TriggerResult).
        rainfall_reasons                 : Reason strings from TriggerResult.

        Returns
        -------
        DynamicRiskAssessment
        """
        # --- Input validation ---
        self._validate_inputs(
            susceptibility_probability,
            susceptibility_class,
            rainfall_trigger_state,
            rainfall_trigger_score,
        )

        # --- Matrix lookup ---
        final_risk_level = self._lookup(susceptibility_class, rainfall_trigger_state)

        # --- Compose reasons ---
        reasons = self._build_reasons(
            susceptibility_class,
            susceptibility_probability,
            rainfall_trigger_state,
            rainfall_reasons,
            final_risk_level,
        )

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        result = DynamicRiskAssessment(
            latitude                  = latitude,
            longitude                 = longitude,
            susceptibility_probability = round(float(susceptibility_probability), 4),
            susceptibility_class      = susceptibility_class,
            rainfall_trigger_state    = rainfall_trigger_state,
            rainfall_trigger_score    = rainfall_trigger_score,
            final_risk_level          = final_risk_level,
            reasons                   = reasons,
            timestamp                 = timestamp,
        )

        logger.info(
            "Risk assessment complete for (%.4f, %.4f): "
            "susceptibility=%s (%.4f) + trigger=%s -> final=%s",
            latitude, longitude,
            susceptibility_class, susceptibility_probability,
            rainfall_trigger_state, final_risk_level,
        )
        return result

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _lookup(self, susceptibility_class: str, trigger_state: str) -> str:
        """
        Look up the final risk level in the 2D matrix.
        Raises RiskMatrixLookupError on missing key.
        """
        sus_row = self._matrix.get(susceptibility_class)
        if sus_row is None:
            raise RiskMatrixLookupError(
                f"Susceptibility class '{susceptibility_class}' not found in "
                f"risk matrix. Valid classes: {sorted(self._matrix.keys())}"
            )

        risk_level = sus_row.get(trigger_state)
        if risk_level is None:
            raise RiskMatrixLookupError(
                f"Trigger state '{trigger_state}' not found under "
                f"susceptibility class '{susceptibility_class}' in risk matrix. "
                f"Available states: {sorted(sus_row.keys())}"
            )

        return str(risk_level)

    @staticmethod
    def _validate_inputs(
        probability:     float,
        sus_class:       str,
        trigger_state:   str,
        trigger_score:   int,
    ) -> None:
        if not (0.0 <= float(probability) <= 1.0):
            raise ValueError(
                f"susceptibility_probability must be in [0, 1]. Got: {probability}"
            )
        if sus_class not in VALID_SUSCEPTIBILITY_CLASSES:
            raise ValueError(
                f"susceptibility_class '{sus_class}' is invalid. "
                f"Valid values: {sorted(VALID_SUSCEPTIBILITY_CLASSES)}"
            )
        if trigger_state not in VALID_TRIGGER_STATES:
            raise ValueError(
                f"rainfall_trigger_state '{trigger_state}' is invalid. "
                f"Valid values: {sorted(VALID_TRIGGER_STATES)}"
            )
        if int(trigger_score) not in (0, 1, 2, 3):
            raise ValueError(
                f"rainfall_trigger_score must be 0–3. Got: {trigger_score}"
            )

    @staticmethod
    def _build_reasons(
        sus_class:       str,
        probability:     float,
        trigger_state:   str,
        rainfall_reasons: List[str],
        final_risk_level: str,
    ) -> List[str]:
        reasons = []

        # Static vulnerability note
        reasons.append(
            f"Terrain exhibits {sus_class.replace('_', ' ')} susceptibility "
            f"(ML probability: {probability:.4f})."
        )

        # Rainfall context
        if trigger_state == "NORMAL":
            reasons.append(
                "Rainfall trigger state is NORMAL: no dynamic rainfall thresholds breached."
            )
        else:
            reasons.append(
                f"Rainfall trigger state is {trigger_state}."
            )

        # Append individual rainfall reasons (from TriggerResult)
        for r in rainfall_reasons:
            if r not in reasons:
                reasons.append(r)

        # Final risk statement
        reasons.append(
            f"Combined risk matrix lookup "
            f"[{sus_class} x {trigger_state}] -> Final Risk Level: {final_risk_level}."
        )
        return reasons

    @classmethod
    def _resolve_default_config(cls) -> str:
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..')
        )
        return os.path.join(root, cls._DEFAULT_CONFIG)

    @staticmethod
    def _load_config(path: str) -> dict:
        """Load and validate the YAML risk matrix. Uses yaml.safe_load()."""
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required. Install with: pip install pyyaml"
            ) from exc

        if not os.path.exists(path):
            raise FileNotFoundError(f"Risk rules config not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict) or 'risk_matrix' not in raw:
            raise ValueError(
                "YAML config must have a top-level 'risk_matrix' key."
            )

        matrix = raw['risk_matrix']

        # Structural validation
        for sus_class, row in matrix.items():
            if sus_class not in VALID_SUSCEPTIBILITY_CLASSES:
                raise ValueError(
                    f"Unknown susceptibility class '{sus_class}' in risk matrix."
                )
            for trigger_state, risk_level in row.items():
                if trigger_state not in VALID_TRIGGER_STATES:
                    raise ValueError(
                        f"Unknown trigger state '{trigger_state}' under "
                        f"'{sus_class}' in risk matrix."
                    )
                if str(risk_level) not in VALID_RISK_LEVELS:
                    raise ValueError(
                        f"Unknown risk level '{risk_level}' at "
                        f"[{sus_class}][{trigger_state}] in risk matrix."
                    )

        return matrix
