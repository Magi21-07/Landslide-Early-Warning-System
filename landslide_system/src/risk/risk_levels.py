"""
src/risk/risk_levels.py
------------------------
Phase 5.7: Standardized Risk Classification.

Single source of truth for the 4-tier canonical risk level system.
All metadata (hex codes, descriptions, numeric codes) is loaded strictly
from config/risk_definitions.yaml — nothing is hardcoded here.

Provides:
  - RiskLevelEnum   : canonical 4-tier string enum
  - RiskLevel       : full metadata dataclass
  - classify_risk() : unified entry-point for float OR string input
"""

import os
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class RiskLevelEnum(str, Enum):
    """Canonical 4-tier risk level names (compatible with str comparisons)."""
    LOW      = "LOW"
    MODERATE = "MODERATE"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class RiskLevel:
    """
    Full metadata for a single canonical risk level.

    All fields are populated from config/risk_definitions.yaml.
    No values are hardcoded in Python.
    """
    level_enum:        RiskLevelEnum
    numeric_code:      int
    machine_name:      str
    human_description: str
    color_hex:         str
    ui_severity:       str
    min_score:         float
    max_score:         float

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict (JSON-serialisable) representation."""
        d = asdict(self)
        d['level_enum'] = self.level_enum.value   # str, not Enum object
        return d


# ---------------------------------------------------------------------------
# Config loader (cached per path)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = "config/risk_definitions.yaml"


def _resolve_default_config() -> str:
    root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..')
    )
    return os.path.join(root, _DEFAULT_CONFIG)


@lru_cache(maxsize=8)
def _load_definitions(config_path: str) -> Dict[str, Any]:
    """
    Load and validate the risk_definitions.yaml. Cached per config_path.

    Returns
    -------
    dict with keys 'risk_levels' and 'string_mappings'.
    """
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required. Install with: pip install pyyaml"
        ) from exc

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Risk definitions config not found: {config_path}"
        )

    with open(config_path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("risk_definitions.yaml must be a YAML mapping.")

    if 'risk_levels' not in raw:
        raise ValueError(
            "risk_definitions.yaml must contain a top-level 'risk_levels' key."
        )
    if 'string_mappings' not in raw:
        raise ValueError(
            "risk_definitions.yaml must contain a top-level 'string_mappings' key."
        )

    required_fields = {
        'numeric_code', 'machine_name', 'human_description',
        'color_hex', 'ui_severity', 'min_score', 'max_score',
    }
    for level_name, cfg in raw['risk_levels'].items():
        missing = required_fields - set(cfg.keys())
        if missing:
            raise ValueError(
                f"risk_levels.{level_name} is missing required fields: {missing}"
            )

    logger.info(
        "risk_definitions.yaml loaded: %d levels, %d string mappings",
        len(raw['risk_levels']), len(raw['string_mappings'])
    )
    return raw


def _build_risk_level(level_name: str, cfg: Dict[str, Any]) -> RiskLevel:
    """Construct a RiskLevel dataclass from a YAML config dict entry."""
    return RiskLevel(
        level_enum        = RiskLevelEnum(level_name),
        numeric_code      = int(cfg['numeric_code']),
        machine_name      = str(cfg['machine_name']),
        human_description = str(cfg['human_description']),
        color_hex         = str(cfg['color_hex']),
        ui_severity       = str(cfg['ui_severity']),
        min_score         = float(cfg['min_score']),
        max_score         = float(cfg['max_score']),
    )


# ---------------------------------------------------------------------------
# Public classify_risk() entry-point
# ---------------------------------------------------------------------------

def classify_risk(
    input_val:   Union[float, int, str],
    config_path: Optional[Union[str, Path]] = None,
) -> RiskLevel:
    """
    Classify a risk value into a canonical RiskLevel.

    Parameters
    ----------
    input_val : float | int | str
        - **Numeric** (float or int in [0.0, 1.0]):
          Finds the RiskLevel whose [min_score, max_score] interval contains
          the value. Boundaries are inclusive; overlapping boundaries (e.g.
          0.25 shared by LOW and MODERATE) always resolve to the *higher* tier
          (MODERATE wins at exactly 0.25).
        - **String**: Normalised to upper-case then looked up in
          string_mappings (e.g. "minimal" -> "LOW", "severe" -> "CRITICAL").
          Raises ValueError if not found.

    config_path : str | Path | None
        Path to risk_definitions.yaml. Defaults to the project-root location.

    Returns
    -------
    RiskLevel

    Raises
    ------
    ValueError  : numeric out of [0, 1], or unknown string.
    FileNotFoundError : config_path does not exist.
    """
    path = str(config_path) if config_path else _resolve_default_config()
    defs = _load_definitions(path)

    # --- Numeric path ---
    if isinstance(input_val, (int, float)) and not isinstance(input_val, bool):
        return _classify_numeric(float(input_val), defs, path)

    # --- String path ---
    if isinstance(input_val, str):
        return _classify_string(input_val, defs, path)

    raise TypeError(
        f"input_val must be a float, int, or str. Got: {type(input_val).__name__}"
    )


def _classify_numeric(value: float, defs: Dict, path: str) -> RiskLevel:
    """Classify a probability score in [0.0, 1.0]."""
    if value < 0.0 or value > 1.0:
        raise ValueError(
            f"Numeric input must be in [0.0, 1.0]. Got: {value}"
        )

    # Sort levels by min_score descending so the highest matching tier wins
    # at shared boundaries (e.g. 0.25 -> MODERATE, not LOW).
    levels_sorted = sorted(
        defs['risk_levels'].items(),
        key=lambda kv: float(kv[1]['min_score']),
        reverse=True,  # highest min_score first
    )

    for level_name, cfg in levels_sorted:
        lo = float(cfg['min_score'])
        hi = float(cfg['max_score'])
        if lo <= value <= hi:
            logger.debug(
                "classify_risk(%.4f) -> %s [%.2f, %.2f]", value, level_name, lo, hi
            )
            return _build_risk_level(level_name, cfg)

    # Fallback — should never reach here for a valid [0,1] input
    raise ValueError(
        f"No risk level matched for value={value}. "
        f"Check risk_definitions.yaml score intervals."
    )


def _classify_string(value: str, defs: Dict, path: str) -> RiskLevel:
    """Classify a string label via string_mappings."""
    normalised = value.strip().upper()
    mappings   = defs['string_mappings']

    canonical = mappings.get(normalised)
    if canonical is None:
        raise ValueError(
            f"Unknown risk string: '{value}'. "
            f"Valid inputs: {sorted(mappings.keys())}"
        )

    canonical_upper = str(canonical).upper()
    cfg = defs['risk_levels'].get(canonical_upper)
    if cfg is None:
        raise ValueError(
            f"string_mappings points '{value}' -> '{canonical}' but "
            f"'{canonical_upper}' is not defined in risk_levels."
        )

    logger.debug(
        "classify_risk('%s') -> normalised='%s' -> canonical='%s'",
        value, normalised, canonical_upper
    )
    return _build_risk_level(canonical_upper, cfg)
