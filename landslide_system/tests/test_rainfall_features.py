"""
tests/test_rainfall_features.py
---------------------------------
Unit tests for src/risk/rainfall_features.py (RainfallFeatureCalculator).
All expected outputs are hand-calculated from deterministic fixture arrays.
No GEE / network calls occur.

Fixture daily rainfall (index 0 = T_ref, index 1 = T_ref-1, ...):
    P = [10.0,  0.0,  5.0, 20.0,  0.0, 15.0, 8.0,
          3.0,  0.0, 12.0,  7.0,  4.0,  0.0, 9.0, 6.0]

Hand-calculated expectations (k=0.85):
    rainfall_1d   = 10.0
    rainfall_3d   = 10 + 0 + 5 = 15.0
    rainfall_7d   = 10 + 0 + 5 + 20 + 0 + 15 + 8 = 58.0
    rainfall_15d  = sum of all 15 = 99.0
    max_3d        = max(10,  0, 5)  = 10.0
    max_7d        = max(10,  0, 5, 20,  0, 15, 8) = 20.0
    max_15d       = max(all) = 20.0

    API_15 = sum_{t=1}^{14} k^t * P[t]  (T_ref excluded from antecedent)
           = 0.85^1*0 + 0.85^2*5 + 0.85^3*20 + 0.85^4*0 + 0.85^5*15
             + 0.85^6*8 + 0.85^7*3 + 0.85^8*0 + 0.85^9*12 + 0.85^10*7
             + 0.85^11*4 + 0.85^12*0 + 0.85^13*9 + 0.85^14*6
"""

import sys
import os
import datetime
import math
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.rainfall_features import (
    DailyRecord,
    RainfallFeatureCalculator,
    RainfallFeatureSet,
    DEFAULT_API_DECAY_K,
)

# ---------------------------------------------------------------------------
# Deterministic test fixtures
# ---------------------------------------------------------------------------

REF_DATE = datetime.date(2026, 9, 20)

# Fixture: 15 days ending on REF_DATE
# P[0] = T_ref (2026-09-20), P[1] = T_ref-1 (2026-09-19), ...
FIXTURE_VALUES = [10.0, 0.0, 5.0, 20.0, 0.0, 15.0, 8.0,
                  3.0,  0.0, 12.0, 7.0,  4.0, 0.0,  9.0, 6.0]


def _make_records(
    values: list,
    ref_date: datetime.date = REF_DATE,
    is_complete_flags: list = None,
) -> list:
    """Build DailyRecord list from values (index 0 = ref_date)."""
    records = []
    for i, val in enumerate(values):
        d = ref_date - datetime.timedelta(days=i)
        complete = True
        if is_complete_flags is not None:
            complete = is_complete_flags[i] if i < len(is_complete_flags) else True
        records.append(DailyRecord(
            date=d.isoformat(),
            rainfall_mm=val,
            is_complete=complete,
        ))
    return records


def _calc(records, ref_date=REF_DATE, decay_k=DEFAULT_API_DECAY_K):
    """Shortcut: create calc and return features."""
    calc = RainfallFeatureCalculator(decay_k=decay_k)
    return calc.calculate(records, ref_date)


def _expected_api(values, k=DEFAULT_API_DECAY_K):
    """Hand-compute API_15: antecedent[t=1..14] (excludes index 0 / T_ref)."""
    total = 0.0
    for i, val in enumerate(values[1:15]):   # indices 1..14
        t = i + 1
        p = val if val is not None else 0.0
        total += (k ** t) * p
    return round(total, 4)


# ---------------------------------------------------------------------------
# 1. Cumulative rainfall features
# ---------------------------------------------------------------------------

class TestCumulativeFeatures:

    def test_rainfall_1d(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.rainfall_1d == 10.0

    def test_rainfall_3d(self):
        # 10 + 0 + 5 = 15.0
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.rainfall_3d == 15.0

    def test_rainfall_7d(self):
        # 10 + 0 + 5 + 20 + 0 + 15 + 8 = 58.0
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.rainfall_7d == 58.0

    def test_rainfall_15d(self):
        # sum of all 15 = 99.0
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.rainfall_15d == sum(FIXTURE_VALUES)

    def test_all_zeros_cumulative(self):
        records = _make_records([0.0] * 15)
        fs = _calc(records)
        assert fs.rainfall_1d  == 0.0
        assert fs.rainfall_3d  == 0.0
        assert fs.rainfall_7d  == 0.0
        assert fs.rainfall_15d == 0.0

    def test_rounding_to_2_decimal_places(self):
        # 1/3 = 0.333... should be rounded to 2 d.p.
        records = _make_records([1/3] * 15)
        fs = _calc(records)
        assert fs.rainfall_1d == round(1/3, 2)
        assert fs.rainfall_3d == round(3 * (1/3), 2)


# ---------------------------------------------------------------------------
# 2. Peak-intensity (max) features
# ---------------------------------------------------------------------------

class TestMaxFeatures:

    def test_max_daily_rainfall_3d(self):
        # window[:3] = [10.0, 0.0, 5.0] -> max = 10.0
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.max_daily_rainfall_3d == 10.0

    def test_max_daily_rainfall_7d(self):
        # window[:7] = [10,0,5,20,0,15,8] -> max = 20.0
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.max_daily_rainfall_7d == 20.0

    def test_max_daily_rainfall_15d(self):
        # max of all 15 values
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.max_daily_rainfall_15d == max(FIXTURE_VALUES)

    def test_max_with_uniform_values(self):
        records = _make_records([5.0] * 15)
        fs = _calc(records)
        assert fs.max_daily_rainfall_3d  == 5.0
        assert fs.max_daily_rainfall_7d  == 5.0
        assert fs.max_daily_rainfall_15d == 5.0


# ---------------------------------------------------------------------------
# 3. Antecedent Precipitation Index
# ---------------------------------------------------------------------------

class TestAPIFeature:

    def test_api_hand_calculated_value(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        expected = _expected_api(FIXTURE_VALUES)
        assert fs.antecedent_precipitation_index == expected

    def test_api_excludes_t_ref(self):
        """API must not include the current day (index 0 = T_ref)."""
        # Only T_ref has rainfall; all antecedent days are 0
        values = [100.0] + [0.0] * 14
        records = _make_records(values)
        fs = _calc(records)
        # API should be 0 since P_t=0 for all t>=1
        assert fs.antecedent_precipitation_index == 0.0

    def test_api_decay_weight_applied(self):
        """Yesterday (t=1) should carry k^1 weight."""
        # Only yesterday has rainfall = 100; all others = 0
        values = [0.0, 100.0] + [0.0] * 13
        records = _make_records(values)
        k = DEFAULT_API_DECAY_K
        expected = round((k ** 1) * 100.0, 4)
        fs = _calc(records)
        assert fs.antecedent_precipitation_index == expected

    def test_api_custom_decay_k(self):
        """Custom k=0.5 should change API value."""
        values = [0.0, 10.0] + [0.0] * 13
        records = _make_records(values)
        k = 0.5
        expected = round((k ** 1) * 10.0, 4)
        fs = _calc(records, decay_k=k)
        assert fs.antecedent_precipitation_index == expected

    def test_api_zero_rainfall_all_days(self):
        records = _make_records([0.0] * 15)
        fs = _calc(records)
        assert fs.antecedent_precipitation_index == 0.0

    def test_invalid_decay_k_raises(self):
        with pytest.raises(ValueError, match="decay_k"):
            RainfallFeatureCalculator(decay_k=1.5)

    def test_zero_decay_k_raises(self):
        with pytest.raises(ValueError, match="decay_k"):
            RainfallFeatureCalculator(decay_k=0.0)


# ---------------------------------------------------------------------------
# 4. Window boundary — no future leakage
# ---------------------------------------------------------------------------

class TestWindowBoundary:

    def test_future_records_are_excluded(self):
        """Records dated after reference_date must be ignored."""
        records = _make_records(FIXTURE_VALUES)
        # Add a future record with enormous rainfall
        future = REF_DATE + datetime.timedelta(days=1)
        records.append(DailyRecord(
            date=future.isoformat(),
            rainfall_mm=9999.0,
            is_complete=True
        ))
        fs = _calc(records)
        # None of the cumulative features should include 9999.0
        assert fs.rainfall_1d  == 10.0
        assert fs.rainfall_7d  == 58.0
        assert fs.rainfall_15d == sum(FIXTURE_VALUES)

    def test_window_strictly_15_days(self):
        """Records older than 15 days must not affect features."""
        records = _make_records(FIXTURE_VALUES)
        # Add a 16-days-ago record
        old_date = REF_DATE - datetime.timedelta(days=15)
        records.append(DailyRecord(
            date=old_date.isoformat(),
            rainfall_mm=500.0,
            is_complete=True
        ))
        fs = _calc(records)
        # rainfall_15d covers [T_ref-14 .. T_ref] — 16-days-ago excluded
        assert fs.rainfall_15d == sum(FIXTURE_VALUES)

    def test_reference_date_is_included_in_1d(self):
        records = _make_records([42.0] + [0.0] * 14)
        fs = _calc(records)
        assert fs.rainfall_1d == 42.0


# ---------------------------------------------------------------------------
# 5. Partial-day flag and data quality
# ---------------------------------------------------------------------------

class TestDataQualityFlags:

    def test_is_complete_true_when_all_present_and_complete(self):
        records = _make_records(FIXTURE_VALUES)  # all is_complete=True by default
        fs = _calc(records)
        assert fs.is_complete is True
        assert fs.partial_day_flag is False
        assert fs.missing_days_count == 0

    def test_partial_day_flag_set_when_t_ref_incomplete(self):
        flags = [False] + [True] * 14   # T_ref incomplete
        records = _make_records(FIXTURE_VALUES, is_complete_flags=flags)
        fs = _calc(records)
        assert fs.partial_day_flag is True
        assert fs.is_complete is False

    def test_is_complete_false_when_any_day_missing(self):
        values = list(FIXTURE_VALUES)
        records = _make_records(values)
        # Replace one record with is_complete=False
        records[3] = DailyRecord(
            date=(REF_DATE - datetime.timedelta(days=3)).isoformat(),
            rainfall_mm=20.0,
            is_complete=False
        )
        fs = _calc(records)
        assert fs.is_complete is False

    def test_missing_days_count_none_values(self):
        """None rainfall values must increment missing_days_count."""
        values = list(FIXTURE_VALUES)
        records = _make_records(values)
        # Replace 2 records with None rainfall
        for gap_offset in [2, 5]:
            d = REF_DATE - datetime.timedelta(days=gap_offset)
            records = [r for r in records if r.date != d.isoformat()]
            records.append(DailyRecord(
                date=d.isoformat(),
                rainfall_mm=None,
                is_complete=False
            ))
        fs = _calc(records)
        assert fs.missing_days_count == 2

    def test_missing_cumulative_returns_none(self):
        """If ANY day in a window is None, cumulative sum returns None."""
        values = list(FIXTURE_VALUES)
        records = _make_records(values)
        # Insert a missing day at offset=1 (T_ref-1) -> breaks 3d, 7d, 15d sums
        d = REF_DATE - datetime.timedelta(days=1)
        records = [r for r in records if r.date != d.isoformat()]
        records.append(DailyRecord(
            date=d.isoformat(), rainfall_mm=None, is_complete=False
        ))
        fs = _calc(records)
        # 1d is fine (T_ref only)
        assert fs.rainfall_1d == FIXTURE_VALUES[0]
        # 3d, 7d, 15d should be None (missing day in window)
        assert fs.rainfall_3d  is None
        assert fs.rainfall_7d  is None
        assert fs.rainfall_15d is None

    def test_missing_max_uses_available_values(self):
        """max features should use available (non-None) values."""
        values = list(FIXTURE_VALUES)
        records = _make_records(values)
        # Insert a missing day at offset=2 (within 3d window)
        d = REF_DATE - datetime.timedelta(days=2)
        records = [r for r in records if r.date != d.isoformat()]
        records.append(DailyRecord(
            date=d.isoformat(), rainfall_mm=None, is_complete=False
        ))
        fs = _calc(records)
        # max_3d uses non-None values: [10.0, 0.0] -> max = 10.0
        assert fs.max_daily_rainfall_3d == 10.0


# ---------------------------------------------------------------------------
# 6. Output schema validation
# ---------------------------------------------------------------------------

class TestOutputSchema:

    def test_returns_rainfall_feature_set_instance(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert isinstance(fs, RainfallFeatureSet)

    def test_reference_date_preserved_in_output(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.reference_date == REF_DATE.isoformat()

    def test_lookback_days_is_15(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.lookback_days == 15

    def test_units_is_mm(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        assert fs.units == "mm"

    def test_to_dict_returns_dict(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records)
        d = fs.to_dict()
        assert isinstance(d, dict)
        assert 'rainfall_1d' in d
        assert 'antecedent_precipitation_index' in d

    def test_api_decay_k_stored_in_output(self):
        k = 0.7
        records = _make_records(FIXTURE_VALUES)
        calc = RainfallFeatureCalculator(decay_k=k)
        fs = calc.calculate(records, REF_DATE)
        assert fs.api_decay_k == k

    def test_accepts_datetime_date_reference(self):
        records = _make_records(FIXTURE_VALUES)
        fs = _calc(records, ref_date=REF_DATE)   # datetime.date object
        assert fs.reference_date == '2026-09-20'

    def test_accepts_string_reference_date(self):
        records = _make_records(FIXTURE_VALUES)
        calc = RainfallFeatureCalculator()
        fs = calc.calculate(records, '2026-09-20')  # string
        assert fs.reference_date == '2026-09-20'

    def test_empty_records_returns_all_none_features(self):
        calc = RainfallFeatureCalculator()
        fs = calc.calculate([], REF_DATE)
        assert fs.rainfall_1d  is None
        assert fs.rainfall_3d  is None
        assert fs.rainfall_7d  is None
        assert fs.rainfall_15d is None
        assert fs.antecedent_precipitation_index is None
        assert fs.missing_days_count == 15
