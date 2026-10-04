"""
tests/test_chirps.py
---------------------
Unit tests for src/risk/chirps_client.py (ChirpsClient).
All GEE calls are mocked via unittest.mock so tests run fully offline.
"""

import sys
import os
import importlib
import datetime
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ---------------------------------------------------------------------------
# Mock the GEE library before any project imports touch it
# ---------------------------------------------------------------------------

# We need to mock 'ee' at the top level so imports don't fail offline
ee_mock = MagicMock()
sys.modules['ee'] = ee_mock

# Also mock earthengine-api sub-imports that might surface
sys.modules['ee.ee_exception'] = MagicMock()


@pytest.fixture(autouse=True, scope='function')
def _ensure_ee_mock():
    """
    Before each test:
      1. Replace sys.modules['ee'] with a FRESH MagicMock so any side_effects
         or return_value mutations from prior test files are wiped.
      2. Reload chirps_client so its module-level `import ee` resolves to the
         new mock, regardless of import order in the full test suite.
    After each test, restore to the same fresh state.
    """
    global ee_mock
    fresh = MagicMock()
    sys.modules['ee']              = fresh
    sys.modules['ee.ee_exception'] = MagicMock()
    ee_mock = fresh                # update module-level reference
    import src.risk.chirps_client as _mod
    importlib.reload(_mod)
    yield
    # Reset side_effects that might bleed from test_both_collections_fail
    sys.modules['ee'] = MagicMock()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_LAT  =  27.5
VALID_LON  =  85.5
START_DATE = '2026-09-15'
END_DATE   = '2026-09-20'

MOCK_GEE_CONFIG = 'fake-gee-project'


def _make_client() -> 'ChirpsClient':
    """Create a ChirpsClient with all GEE calls mocked."""
    with patch('src.risk.chirps_client.initialize_gee', return_value=True):
        from src.risk.chirps_client import ChirpsClient
        return ChirpsClient(gee_config=MOCK_GEE_CONFIG)


def _mock_gee_features(dates: list, values: list) -> dict:
    """Build a fake GEE .getInfo() features payload."""
    features = []
    for d, v in zip(dates, values):
        features.append({
            'type': 'Feature',
            'properties': {
                'date': d,
                'precipitation_mm': v
            }
        })
    return {'features': features}


# ---------------------------------------------------------------------------
# 1. Coordinate validation
# ---------------------------------------------------------------------------

class TestCoordinateValidation:

    def test_valid_coordinates_pass(self):
        client = _make_client()
        from src.risk.chirps_client import _validate_coordinates
        # Must not raise
        _validate_coordinates(VALID_LAT, VALID_LON)

    def test_latitude_too_high_raises(self):
        from src.risk.chirps_client import _validate_coordinates
        with pytest.raises(ValueError, match="Latitude"):
            _validate_coordinates(91.0, VALID_LON)

    def test_latitude_too_low_raises(self):
        from src.risk.chirps_client import _validate_coordinates
        with pytest.raises(ValueError, match="Latitude"):
            _validate_coordinates(-91.0, VALID_LON)

    def test_longitude_too_high_raises(self):
        from src.risk.chirps_client import _validate_coordinates
        with pytest.raises(ValueError, match="Longitude"):
            _validate_coordinates(VALID_LAT, 181.0)

    def test_longitude_too_low_raises(self):
        from src.risk.chirps_client import _validate_coordinates
        with pytest.raises(ValueError, match="Longitude"):
            _validate_coordinates(VALID_LAT, -181.0)

    def test_boundary_values_pass(self):
        from src.risk.chirps_client import _validate_coordinates
        _validate_coordinates(-90.0,  -180.0)
        _validate_coordinates( 90.0,   180.0)
        _validate_coordinates(  0.0,     0.0)

    def test_fetch_raises_on_invalid_lat(self):
        client = _make_client()
        with pytest.raises(ValueError, match="Latitude"):
            client.fetch(lat=95.0, lon=VALID_LON,
                         start_date=START_DATE, end_date=END_DATE)

    def test_fetch_raises_on_invalid_lon(self):
        client = _make_client()
        with pytest.raises(ValueError, match="Longitude"):
            client.fetch(lat=VALID_LAT, lon=200.0,
                         start_date=START_DATE, end_date=END_DATE)


# ---------------------------------------------------------------------------
# 2. Date ordering validation
# ---------------------------------------------------------------------------

class TestDateValidation:

    def test_valid_date_range_passes(self):
        from src.risk.chirps_client import _validate_date_order
        _validate_date_order(
            datetime.date(2026, 9, 1),
            datetime.date(2026, 9, 30)
        )

    def test_same_start_and_end_passes(self):
        from src.risk.chirps_client import _validate_date_order
        d = datetime.date(2026, 9, 15)
        _validate_date_order(d, d)   # must not raise

    def test_start_after_end_raises(self):
        from src.risk.chirps_client import _validate_date_order
        with pytest.raises(ValueError, match="start_date"):
            _validate_date_order(
                datetime.date(2026, 9, 30),
                datetime.date(2026, 9, 1)
            )

    def test_invalid_date_string_raises(self):
        from src.risk.chirps_client import _to_date
        with pytest.raises(ValueError, match="ISO string"):
            _to_date("not-a-date", "start_date")

    def test_date_object_input_accepted(self):
        from src.risk.chirps_client import _to_date
        d = datetime.date(2026, 9, 15)
        result = _to_date(d, 'start_date')
        assert result == d

    def test_iso_string_input_accepted(self):
        from src.risk.chirps_client import _to_date
        result = _to_date('2026-09-15', 'start_date')
        assert result == datetime.date(2026, 9, 15)

    def test_fetch_raises_on_inverted_dates(self):
        client = _make_client()
        with pytest.raises(ValueError, match="start_date"):
            client.fetch(lat=VALID_LAT, lon=VALID_LON,
                         start_date='2026-09-30', end_date='2026-09-01')


# ---------------------------------------------------------------------------
# 3. Mocked GEE extraction — valid payload
# ---------------------------------------------------------------------------

class TestMockedExtraction:

    def _run_fetch_with_mock(self, mock_features: dict, collection_size: int = 6):
        """Helper that runs client.fetch() with fully mocked GEE calls."""
        # Build mock image collection
        mock_collection = MagicMock()
        mock_collection.size.return_value.getInfo.return_value = collection_size
        mock_collection.map.return_value.getInfo.return_value = mock_features
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value   = mock_collection
        mock_collection.select.return_value       = mock_collection

        # Set BEFORE importing ChirpsClient so the reloaded module sees it
        ee_mock.ImageCollection.return_value = mock_collection
        ee_mock.Geometry.Point.return_value  = MagicMock()

        # Reload again so the module picks up the freshly configured mock
        import src.risk.chirps_client as _mod
        importlib.reload(_mod)
        from src.risk.chirps_client import ChirpsClient

        with patch('src.risk.chirps_client.initialize_gee', return_value=True):
            client = ChirpsClient(gee_config=MOCK_GEE_CONFIG)

        return client.fetch(
            lat=VALID_LAT, lon=VALID_LON,
            start_date=START_DATE, end_date=END_DATE
        )

    def test_returns_dict_with_data_and_metadata(self):
        dates  = ['2026-09-15', '2026-09-16', '2026-09-17',
                  '2026-09-18', '2026-09-19', '2026-09-20']
        values = [2.5, 10.3, 0.0, 5.1, 8.8, 3.3]
        features = _mock_gee_features(dates, values)
        result = self._run_fetch_with_mock(features, len(dates))

        assert isinstance(result, dict)
        assert 'data' in result
        assert 'metadata' in result

    def test_data_is_dataframe_with_correct_columns(self):
        dates  = ['2026-09-15', '2026-09-16']
        values = [5.0, 12.0]
        features = _mock_gee_features(dates, values)
        result = self._run_fetch_with_mock(features, 2)

        df = result['data']
        assert isinstance(df, pd.DataFrame)
        assert 'date' in df.columns
        assert 'precipitation_mm' in df.columns

    def test_data_row_count_matches_images(self):
        dates  = ['2026-09-15', '2026-09-16', '2026-09-17']
        values = [1.0, 2.0, 3.0]
        features = _mock_gee_features(dates, values)
        result = self._run_fetch_with_mock(features, 3)

        assert len(result['data']) == 3

    def test_metadata_contains_required_keys(self):
        dates = ['2026-09-15']
        features = _mock_gee_features(dates, [5.0])
        result = self._run_fetch_with_mock(features, 1)

        meta = result['metadata']
        for key in ['data_source', 'collection_id', 'retrieved_at',
                    'date_range', 'coordinate', 'units']:
            assert key in meta, f"Missing metadata key: {key}"

    def test_metadata_data_source_is_chirps(self):
        features = _mock_gee_features(['2026-09-15'], [3.0])
        result = self._run_fetch_with_mock(features, 1)
        assert result['metadata']['data_source'] == 'CHIRPS'

    def test_metadata_units_is_mm_per_day(self):
        features = _mock_gee_features(['2026-09-15'], [3.0])
        result = self._run_fetch_with_mock(features, 1)
        assert result['metadata']['units'] == 'mm/day'

    def test_metadata_coordinate_matches_input(self):
        features = _mock_gee_features(['2026-09-15'], [3.0])
        result = self._run_fetch_with_mock(features, 1)
        coord = result['metadata']['coordinate']
        assert coord['latitude']  == VALID_LAT
        assert coord['longitude'] == VALID_LON

    def test_precipitation_values_are_float(self):
        features = _mock_gee_features(['2026-09-15', '2026-09-16'], [7.2, 0.5])
        result = self._run_fetch_with_mock(features, 2)
        for val in result['data']['precipitation_mm']:
            assert isinstance(val, float)


# ---------------------------------------------------------------------------
# 4. Empty result handling
# ---------------------------------------------------------------------------

class TestEmptyResultHandling:

    def test_empty_collection_returns_empty_dataframe(self):
        from src.risk.chirps_client import ChirpsClient

        mock_collection = MagicMock()
        mock_collection.size.return_value.getInfo.return_value = 0  # empty!
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value   = mock_collection
        mock_collection.select.return_value       = mock_collection

        ee_mock.ImageCollection.return_value = mock_collection
        ee_mock.Geometry.Point.return_value  = MagicMock()

        with patch('src.risk.chirps_client.initialize_gee', return_value=True):
            client = ChirpsClient(gee_config=MOCK_GEE_CONFIG)

        result = client.fetch(
            lat=VALID_LAT, lon=VALID_LON,
            start_date=START_DATE, end_date=END_DATE
        )

        assert isinstance(result['data'], pd.DataFrame)
        assert len(result['data']) == 0
        assert 'date' in result['data'].columns
        assert 'precipitation_mm' in result['data'].columns

    def test_both_collections_fail_returns_synthetic_data(self):
        from src.risk.chirps_client import ChirpsClient

        # Make ImageCollection raise for both primary and fallback
        ee_mock.ImageCollection.side_effect = Exception("GEE unavailable")

        with patch('src.risk.chirps_client.initialize_gee', return_value=True):
            client = ChirpsClient(gee_config=MOCK_GEE_CONFIG)

        result = client.fetch(
            lat=VALID_LAT, lon=VALID_LON,
            start_date=START_DATE, end_date=END_DATE
        )
        assert isinstance(result, dict)
        assert 'data' in result
        assert 'metadata' in result
        assert result['metadata']['data_source'] == 'SYNTHETIC/MOCK'

        # Reset side_effect so it doesn't bleed into other tests
        ee_mock.ImageCollection.side_effect = None

    def test_gee_init_failure_returns_synthetic_client(self):
        from src.risk.chirps_client import ChirpsClient
        with patch('src.risk.chirps_client.initialize_gee', return_value=False):
            client = ChirpsClient(gee_config='bad-config')
            result = client.fetch(VALID_LAT, VALID_LON, START_DATE, END_DATE)
            assert result['metadata']['data_source'] == 'SYNTHETIC/MOCK'


# ---------------------------------------------------------------------------
# 5. Data gap / NaN handling
# ---------------------------------------------------------------------------

class TestDataGapHandling:

    def test_none_value_stored_as_nan_not_zero(self):
        """None returned by GEE for a pixel must become NaN, not 0."""
        from src.risk.chirps_client import ChirpsClient

        mock_features = _mock_gee_features(
            ['2026-09-15', '2026-09-16'],
            [5.0, None]          # second day missing
        )
        mock_collection = MagicMock()
        mock_collection.size.return_value.getInfo.return_value = 2
        mock_collection.map.return_value.getInfo.return_value = mock_features
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.filterDate.return_value   = mock_collection
        mock_collection.select.return_value       = mock_collection

        ee_mock.ImageCollection.return_value = mock_collection
        ee_mock.Geometry.Point.return_value  = MagicMock()

        with patch('src.risk.chirps_client.initialize_gee', return_value=True):
            client = ChirpsClient(gee_config=MOCK_GEE_CONFIG)

        result = client.fetch(
            lat=VALID_LAT, lon=VALID_LON,
            start_date='2026-09-15', end_date='2026-09-16'
        )

        df = result['data']
        assert df['precipitation_mm'].isna().sum() == 1
        assert df.loc[df['date'] == pd.Timestamp('2026-09-15'),
                      'precipitation_mm'].values[0] == 5.0
