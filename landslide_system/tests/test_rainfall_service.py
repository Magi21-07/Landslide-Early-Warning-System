"""
tests/test_rainfall_service.py
--------------------------------
Unit tests for src/risk/rainfall_service.py (RainfallService).
All ChirpsClient / GEE calls are mocked; zero live network calls occur.
"""

import sys
import os
import datetime
import math
import logging
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ---------------------------------------------------------------------------
# Mock the 'ee' library globally so imports don't fail offline
# ---------------------------------------------------------------------------
ee_mock = MagicMock()
sys.modules['ee'] = ee_mock
sys.modules['ee.ee_exception'] = MagicMock()

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

VALID_LAT  =  27.5
VALID_LON  =  85.5
GEE_CONFIG = 'fake-gee-project'

TODAY       = datetime.date.today()
START_3DAYS = TODAY - datetime.timedelta(days=2)   # 3-day window start

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(dates: list, values: list) -> pd.DataFrame:
    """Build a tidy DataFrame as ChirpsClient would return."""
    return pd.DataFrame({
        'date':             pd.to_datetime(dates),
        'precipitation_mm': values,
    })


def _make_chirps_payload(df: pd.DataFrame, collection_id: str = "UCSB-CHC/CHIRPS/V3/DAILY_SAT") -> dict:
    return {
        "data": df,
        "metadata": {
            "data_source":   "CHIRPS",
            "collection_id": collection_id,
            "retrieved_at":  "2026-10-01T17:00:00+00:00",
            "date_range":    {"start": str(df['date'].min().date()),
                              "end":   str(df['date'].max().date())},
            "coordinate":    {"latitude": VALID_LAT, "longitude": VALID_LON},
            "units":         "mm/day",
        }
    }


def _make_service() -> 'RainfallService':
    """Create a RainfallService with ChirpsClient fully mocked (no GEE calls)."""
    from src.risk.rainfall_service import RainfallService
    svc = RainfallService.__new__(RainfallService)
    svc._client = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# 1. Successful extraction: 1, 3, 7, 15-day windows
# ---------------------------------------------------------------------------

class TestSuccessfulExtraction:

    def _svc_with_payload(self, df):
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)
        return svc

    def _make_n_day_df(self, n: int) -> pd.DataFrame:
        dates = [(TODAY - datetime.timedelta(days=n - 1 - i)).isoformat()
                 for i in range(n)]
        values = [float(i + 1) for i in range(n)]
        return _make_df(dates, values)

    def test_1_day_window_returns_1_record(self):
        df  = self._make_n_day_df(1)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=1)
        assert len(result) == 1

    def test_3_day_window_returns_3_records(self):
        df  = self._make_n_day_df(3)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=3)
        assert len(result) == 3

    def test_7_day_window_returns_7_records(self):
        df  = self._make_n_day_df(7)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=7)
        assert len(result) == 7

    def test_15_day_window_returns_15_records(self):
        df  = self._make_n_day_df(15)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=15)
        assert len(result) == 15

    def test_record_contains_required_keys(self):
        df  = self._make_n_day_df(3)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=3)
        for key in ['location_id', 'latitude', 'longitude', 'date',
                    'rainfall_mm', 'source', 'retrieved_at']:
            assert key in result[0], f"Missing key: {key}"

    def test_latitude_and_longitude_preserved_in_records(self):
        df  = self._make_n_day_df(3)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=3)
        for r in result:
            assert r['latitude']  == VALID_LAT
            assert r['longitude'] == VALID_LON

    def test_date_format_is_yyyy_mm_dd(self):
        df  = self._make_n_day_df(3)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=3)
        for r in result:
            datetime.datetime.strptime(r['date'], '%Y-%m-%d')  # must not raise

    def test_source_field_is_collection_id(self):
        df  = self._make_n_day_df(3)
        svc = self._svc_with_payload(df)
        result = svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=3)
        for r in result:
            assert 'CHIRPS' in r['source']


# ---------------------------------------------------------------------------
# 2. Invalid window sizes raise ValueError
# ---------------------------------------------------------------------------

class TestWindowValidation:

    def test_5_day_window_raises(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="Unsupported window"):
            svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=5)

    def test_30_day_window_raises(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="Unsupported window"):
            svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=30)

    def test_0_day_window_raises(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="Unsupported window"):
            svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=0)

    def test_10_day_window_raises(self):
        svc = _make_service()
        with pytest.raises(ValueError, match="Unsupported window"):
            svc.get_recent_rainfall(VALID_LAT, VALID_LON, days=10)

    def test_all_valid_windows_do_not_raise(self):
        """1, 3, 7, 15 must all be accepted."""
        from src.risk.rainfall_service import SUPPORTED_WINDOWS
        assert SUPPORTED_WINDOWS == {1, 3, 7, 15}

    def test_batch_invalid_window_raises(self):
        svc = _make_service()
        locs = [{'latitude': VALID_LAT, 'longitude': VALID_LON}]
        with pytest.raises(ValueError, match="Unsupported window"):
            svc.get_rainfall_for_locations(locs, days=5)


# ---------------------------------------------------------------------------
# 3. Missing data vs explicit 0.0 preservation
# ---------------------------------------------------------------------------

class TestMissingDataHandling:

    def test_nan_preserved_as_none_not_zero(self):
        df = _make_df(
            ['2026-09-15', '2026-09-16'],
            [5.0, np.nan]
        )
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)
        result = svc.get_daily_rainfall(
            VALID_LAT, VALID_LON,
            start_date='2026-09-15', end_date='2026-09-16'
        )
        values = [r['rainfall_mm'] for r in result]
        assert values[0] == 5.0
        assert values[1] is None       # NaN -> None, NOT 0.0

    def test_explicit_zero_is_preserved(self):
        """0.0 is a valid dry-day measurement and must NOT become None."""
        df = _make_df(['2026-09-15'], [0.0])
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)
        result = svc.get_daily_rainfall(
            VALID_LAT, VALID_LON,
            start_date='2026-09-15', end_date='2026-09-15'
        )
        assert result[0]['rainfall_mm'] == 0.0
        assert result[0]['rainfall_mm'] is not None

    def test_raw_value_not_rounded(self):
        """Values must not be rounded, scaled, or transformed."""
        raw = 12.345678
        df  = _make_df(['2026-09-15'], [raw])
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)
        result = svc.get_daily_rainfall(
            VALID_LAT, VALID_LON,
            start_date='2026-09-15', end_date='2026-09-15'
        )
        assert result[0]['rainfall_mm'] == raw

    def test_empty_dataframe_returns_empty_list(self):
        df = pd.DataFrame(columns=['date', 'precipitation_mm'])
        svc = _make_service()
        svc._client.fetch.return_value = {
            "data": df,
            "metadata": {
                "data_source":   "CHIRPS",
                "collection_id": "UCSB-CHC/CHIRPS/V3/DAILY_SAT",
                "retrieved_at":  "2026-10-01T17:00:00+00:00",
                "date_range":    {"start": "2026-09-15", "end": "2026-09-15"},
                "coordinate":    {"latitude": VALID_LAT, "longitude": VALID_LON},
                "units":         "mm/day",
            }
        }
        result = svc.get_daily_rainfall(
            VALID_LAT, VALID_LON,
            start_date='2026-09-15', end_date='2026-09-15'
        )
        assert result == []


# ---------------------------------------------------------------------------
# 4. location_id preservation
# ---------------------------------------------------------------------------

class TestLocationIdHandling:

    def test_location_id_preserved_in_records(self):
        df  = _make_df(['2026-09-15', '2026-09-16'], [3.0, 5.0])
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)
        result = svc.get_daily_rainfall(
            VALID_LAT, VALID_LON,
            start_date='2026-09-15', end_date='2026-09-16',
            location_id='SITE-001'
        )
        for r in result:
            assert r['location_id'] == 'SITE-001'

    def test_none_location_id_when_not_provided(self):
        df  = _make_df(['2026-09-15'], [4.0])
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)
        result = svc.get_daily_rainfall(
            VALID_LAT, VALID_LON,
            start_date='2026-09-15', end_date='2026-09-15'
        )
        assert result[0]['location_id'] is None

    def test_batch_location_id_mapped_per_location(self):
        df1 = _make_df(['2026-09-15'], [3.0])
        df2 = _make_df(['2026-09-15'], [7.0])

        svc = _make_service()
        # Return different payloads on successive calls
        svc._client.fetch.side_effect = [
            _make_chirps_payload(df1),
            _make_chirps_payload(df2),
        ]

        locs = [
            {'latitude': 27.5, 'longitude': 85.5, 'location_id': 'LOC-A'},
            {'latitude': 28.0, 'longitude': 86.0, 'location_id': 'LOC-B'},
        ]
        result = svc.get_rainfall_for_locations(locs, days=1)

        ids = {r['location_id'] for r in result}
        assert 'LOC-A' in ids
        assert 'LOC-B' in ids

    def test_location_dict_not_mutated(self):
        """Original location dict must not be altered by the service."""
        original = {'latitude': VALID_LAT, 'longitude': VALID_LON, 'location_id': 'TEST'}
        snapshot = dict(original)

        df  = _make_df(['2026-09-15'], [2.0])
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)

        svc.get_rainfall_for_locations([original], days=1)
        assert original == snapshot   # must be unchanged


# ---------------------------------------------------------------------------
# 5. Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_runtime_error_wrapped_in_rainfall_fetch_error(self):
        from src.risk.rainfall_service import RainfallFetchError
        svc = _make_service()
        svc._client.fetch.side_effect = RuntimeError("GEE unavailable")

        with pytest.raises(RainfallFetchError, match="Rainfall extraction failed"):
            svc.get_daily_rainfall(
                VALID_LAT, VALID_LON,
                start_date='2026-09-15', end_date='2026-09-15'
            )

    def test_batch_skips_failed_location_continues_others(self):
        """A failing location must not abort the whole batch."""
        from src.risk.rainfall_service import RainfallFetchError

        df_ok = _make_df(['2026-09-15'], [5.0])

        svc = _make_service()
        # First location raises; second succeeds
        svc._client.fetch.side_effect = [
            RuntimeError("GEE timeout"),
            _make_chirps_payload(df_ok),
        ]

        locs = [
            {'latitude': 27.5, 'longitude': 85.5, 'location_id': 'FAIL-LOC'},
            {'latitude': 28.0, 'longitude': 86.0, 'location_id': 'OK-LOC'},
        ]
        result = svc.get_rainfall_for_locations(locs, days=1)

        # Only the successful location's records should be present
        assert all(r['location_id'] == 'OK-LOC' for r in result)
        assert len(result) >= 1

    def test_missing_data_warning_logged(self, caplog):
        df = _make_df(['2026-09-15', '2026-09-16'], [5.0, np.nan])
        svc = _make_service()
        svc._client.fetch.return_value = _make_chirps_payload(df)

        with caplog.at_level(logging.WARNING, logger='src.risk.rainfall_service'):
            svc.get_daily_rainfall(
                VALID_LAT, VALID_LON,
                start_date='2026-09-15', end_date='2026-09-16'
            )

        assert any('Missing data' in msg for msg in caplog.messages)
