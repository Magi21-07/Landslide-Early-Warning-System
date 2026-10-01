"""
src/risk/rainfall_features.py
------------------------------
Phase 5.4: Rainfall Feature Engineering.

Calculates dynamic hazard indicators from a time-series of daily rainfall
records. These features feed the Phase 5 Dynamic Risk Overlay Engine and
are entirely separate from the 4 static Phase 4 XGBoost ML features.

NO model retraining, NO schema mutation, NO final risk scoring here.
"""

import logging
import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_API_DECAY_K: float = 0.85  # Antecedent Precipitation Index decay constant


# ---------------------------------------------------------------------------
# Data schemas
# ---------------------------------------------------------------------------

@dataclass
class DailyRecord:
    """
    A single day's rainfall observation with completeness metadata.

    Attributes
    ----------
    date         : ISO date string (YYYY-MM-DD). Must be the calendar date
                   for which the observation applies.
    rainfall_mm  : Observed rainfall in mm. None = missing / no data.
    is_complete  : True if the observation covers a full 24-hour period.
                   False if the record is partial (e.g., current day still
                   accumulating) or the completeness is unknown.
    """
    date:        str
    rainfall_mm: Optional[float]
    is_complete: bool = True


@dataclass
class RainfallFeatureSet:
    """
    Structured output from RainfallFeatureCalculator.calculate().

    All cumulative and max values are in mm, rounded to 2 decimal places.
    API_15 is dimensionless but expressed in mm-equivalent units.
    """
    # Reference context
    reference_date:  str        # ISO date string of T_ref
    lookback_days:   int        # Max lookback window used
    units:           str = "mm"

    # Cumulative rainfall features
    rainfall_1d:   Optional[float] = None
    rainfall_3d:   Optional[float] = None
    rainfall_7d:   Optional[float] = None
    rainfall_15d:  Optional[float] = None

    # Peak-intensity features
    max_daily_rainfall_3d:  Optional[float] = None
    max_daily_rainfall_7d:  Optional[float] = None
    max_daily_rainfall_15d: Optional[float] = None

    # Antecedent Precipitation Index
    antecedent_precipitation_index: Optional[float] = None
    api_decay_k: float = DEFAULT_API_DECAY_K

    # Data quality flags
    is_complete:        bool = True    # All days in window have complete 24-hr data
    partial_day_flag:   bool = False   # Current-day data is partial/incomplete
    missing_days_count: int  = 0       # Number of days with None rainfall

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class RainfallFeatureCalculator:
    """
    Calculates dynamic rainfall hazard features for the risk overlay engine.

    Parameters
    ----------
    decay_k : float
        Exponential decay constant for the Antecedent Precipitation Index.
        Default = 0.85.
    """

    def __init__(self, decay_k: float = DEFAULT_API_DECAY_K):
        if not (0.0 < decay_k <= 1.0):
            raise ValueError(
                f"decay_k must be in (0, 1]. Got: {decay_k}"
            )
        self.decay_k = decay_k
        logger.info("RainfallFeatureCalculator initialised (decay_k=%.2f)", decay_k)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def calculate(
        self,
        records:        List[DailyRecord],
        reference_date: Union[str, datetime.date],
    ) -> RainfallFeatureSet:
        """
        Calculate all rainfall hazard features for a reference date.

        Parameters
        ----------
        records : list of DailyRecord
            Daily rainfall observations. May contain records before AND after
            reference_date — future records are silently excluded.
        reference_date : str or datetime.date
            The reference day T_ref. The calculation window is
            strictly [T_ref - 14 days, T_ref] (15 days inclusive).

        Returns
        -------
        RainfallFeatureSet
        """
        ref_date = self._parse_date(reference_date)
        logger.info("Calculating rainfall features for T_ref=%s", ref_date)

        # --- Build a date-indexed lookup; exclude future observations ---
        lookup: Dict[datetime.date, DailyRecord] = {}
        for rec in records:
            d = self._parse_date(rec.date)
            if d > ref_date:
                logger.debug("Excluding future record: %s", rec.date)
                continue
            lookup[d] = rec

        # --- Build an ordered window of up to 15 days: [T_ref-14 .. T_ref] ---
        # Index 0 = T_ref, index 1 = T_ref-1, ..., index 14 = T_ref-14
        window: List[Optional[float]] = []
        completeness: List[bool]       = []

        for offset in range(15):
            day = ref_date - datetime.timedelta(days=offset)
            rec = lookup.get(day)
            if rec is None:
                window.append(None)
                completeness.append(False)
            else:
                window.append(rec.rainfall_mm)
                completeness.append(rec.is_complete)

        # --- Partial-day flag: T_ref record exists but is incomplete ---
        t_ref_rec = lookup.get(ref_date)
        partial_day_flag = (t_ref_rec is not None) and (not t_ref_rec.is_complete)

        # --- Missing count across the 15-day window ---
        missing_days_count = sum(1 for v in window if v is None)

        # --- is_complete: all 15 days present AND all fully complete ---
        is_complete = (
            missing_days_count == 0
            and all(completeness)
            and not partial_day_flag
        )

        # --- Helper: sum a sub-window, returning None if ANY day missing ---
        def _window_sum(n: int) -> Optional[float]:
            sub = window[:n]
            if any(v is None for v in sub):
                return None
            return round(float(np.sum(sub)), 2)

        # --- Helper: max of sub-window ---
        def _window_max(n: int) -> Optional[float]:
            sub = [v for v in window[:n] if v is not None]
            if not sub:
                return None
            return round(float(np.max(sub)), 2)

        # --- Cumulative features ---
        rainfall_1d  = _window_sum(1)
        rainfall_3d  = _window_sum(3)
        rainfall_7d  = _window_sum(7)
        rainfall_15d = _window_sum(15)

        # --- Peak-intensity features ---
        max_3d  = _window_max(3)
        max_7d  = _window_max(7)
        max_15d = _window_max(15)

        # --- Antecedent Precipitation Index (API_15) ---
        # API = sum_{t=1}^{15} k^t * P_t  where t=1 is yesterday (T_ref - 1)
        # t=0 (current day) is intentionally excluded from the antecedent sum
        api = self._compute_api(window[1:15])   # indices 1..14 = yesterday onward

        result = RainfallFeatureSet(
            reference_date  = ref_date.isoformat(),
            lookback_days   = 15,
            units           = "mm",

            rainfall_1d     = rainfall_1d,
            rainfall_3d     = rainfall_3d,
            rainfall_7d     = rainfall_7d,
            rainfall_15d    = rainfall_15d,

            max_daily_rainfall_3d  = max_3d,
            max_daily_rainfall_7d  = max_7d,
            max_daily_rainfall_15d = max_15d,

            antecedent_precipitation_index = api,
            api_decay_k = self.decay_k,

            is_complete        = is_complete,
            partial_day_flag   = partial_day_flag,
            missing_days_count = missing_days_count,
        )

        logger.info(
            "Features computed: 1d=%.2f 3d=%s 7d=%s 15d=%s "
            "API=%.4f complete=%s missing=%d",
            rainfall_1d or 0.0,
            rainfall_3d, rainfall_7d, rainfall_15d,
            api or 0.0, is_complete, missing_days_count
        )
        return result

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_date(value: Union[str, datetime.date]) -> datetime.date:
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        try:
            return datetime.date.fromisoformat(str(value))
        except ValueError as exc:
            raise ValueError(
                f"Cannot parse date: {value!r}. Expected YYYY-MM-DD."
            ) from exc

    def _compute_api(self, antecedent_values: List[Optional[float]]) -> Optional[float]:
        """
        API = sum_{t=1}^{N} k^t * P_t
        where antecedent_values[i] = P_{i+1} (t=1 is yesterday).
        Returns None if ALL values are missing; uses 0.0 for individual missing days.
        """
        if not antecedent_values:
            return None

        total  = 0.0
        all_missing = True

        for i, val in enumerate(antecedent_values):
            t = i + 1           # t=1 for yesterday
            p_t = 0.0 if val is None else float(val)
            if val is not None:
                all_missing = False
            total += (self.decay_k ** t) * p_t

        if all_missing:
            return None

        return round(total, 4)
