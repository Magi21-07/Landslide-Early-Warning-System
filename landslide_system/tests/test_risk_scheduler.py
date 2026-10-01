"""
tests/test_risk_scheduler.py
------------------------------
Unit tests for src/risk/risk_scheduler.py (RiskScheduler).
All engines are replaced with lightweight MagicMocks so zero GEE / disk
I/O occurs during the test run (except against tmp_path for state files).
"""

import sys
import os
import json
import datetime
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.risk_scheduler import RiskScheduler, LocationRiskState, DEFAULT_STALE_THRESHOLD

# ---------------------------------------------------------------------------
# Shared constants / helpers
# ---------------------------------------------------------------------------

TODAY      = datetime.date.today().isoformat()
YESTERDAY  = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
OLD_DATE   = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()

LOC_A = {"latitude": 27.5, "longitude": 85.5, "location_id": "LOC-A"}
LOC_B = {"latitude": 28.0, "longitude": 86.0, "location_id": "LOC-B"}


def _make_rainfall_records(n: int = 15, base_mm: float = 5.0):
    """Create n fake DailyRainfallRecord dicts."""
    records = []
    for i in range(n):
        d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        records.append({
            "location_id": "LOC-A",
            "latitude": 27.5,
            "longitude": 85.5,
            "date": d,
            "rainfall_mm": base_mm,
            "source": "UCSB-CHC/CHIRPS/V3/DAILY_SAT",
            "retrieved_at": "2026-10-01T17:00:00+00:00",
        })
    return records


def _mock_risk_assess():
    """Build a fake DynamicRiskAssessment-like object."""
    m = MagicMock()
    m.to_dict.return_value = {
        "latitude": 27.5, "longitude": 85.5,
        "susceptibility_probability": 0.72,
        "susceptibility_class": "HIGH",
        "rainfall_trigger_state": "WATCH",
        "rainfall_trigger_score": 1,
        "final_risk_level": "MODERATE",
        "reasons": ["Terrain exhibits HIGH susceptibility (0.7200)."],
        "timestamp": "2026-10-01T17:00:00+00:00",
    }
    m.final_risk_level = "MODERATE"
    return m


def _mock_canonical():
    """Build a fake RiskLevel-like object."""
    m = MagicMock()
    m.to_dict.return_value = {
        "level_enum": "MODERATE",
        "numeric_code": 2,
        "machine_name": "RISK_MODERATE",
        "human_description": "Elevated risk.",
        "color_hex": "#ffc107",
        "ui_severity": "WARNING",
        "min_score": 0.25,
        "max_score": 0.50,
    }
    return m


def _mock_feature_set():
    """Build a fake RainfallFeatureSet-like object."""
    m = MagicMock()
    m.to_dict.return_value = {"rainfall_1d": 5.0, "rainfall_7d": 35.0}
    m.rainfall_1d  = 5.0
    m.rainfall_3d  = 15.0
    m.rainfall_7d  = 35.0
    m.rainfall_15d = 75.0
    m.partial_day_flag = False
    return m


def _mock_trigger_result():
    m = MagicMock()
    m.trigger_state   = "WATCH"
    m.trigger_score   = 1
    m.trigger_reasons = ["3-day cumulative rainfall (15.0 mm) exceeded watch threshold."]
    return m


def _build_scheduler(tmp_path, extra_kwargs=None) -> RiskScheduler:
    """
    Create a RiskScheduler with all external engines replaced by MagicMocks.
    All lazy engine slots are pre-filled so no real imports of GEE/YAML occur.
    """
    state_file = str(tmp_path / "state.json")
    sched = RiskScheduler.__new__(RiskScheduler)

    # Initialise attributes manually (avoids __init__ touching real files)
    sched._gee_config              = "fake-gee"
    sched._state_path              = state_file
    sched._stale_threshold_days    = DEFAULT_STALE_THRESHOLD
    sched._rainfall_days           = 15
    sched._model_path              = None
    sched._rainfall_trigger_config = None
    sched._risk_engine_config      = None
    sched._risk_levels_config      = None
    sched._cache                   = {}

    if extra_kwargs:
        for k, v in extra_kwargs.items():
            setattr(sched, k, v)

    # Pre-fill lazy engine slots with mocks
    predictor_mock = MagicMock()
    predictor_mock.predict.return_value = {
        "probability": 0.72,
        "susceptibility": "HIGH",
    }
    sched._predictor = predictor_mock

    rainfall_svc_mock = MagicMock()
    rainfall_svc_mock.get_recent_rainfall.return_value = _make_rainfall_records()
    sched._rainfall_svc = rainfall_svc_mock

    trigger_mock = MagicMock()
    trigger_mock.evaluate.return_value = _mock_trigger_result()
    sched._trigger_engine = trigger_mock

    risk_engine_mock = MagicMock()
    risk_engine_mock.assess.return_value = _mock_risk_assess()
    sched._risk_engine = risk_engine_mock

    return sched


# ---------------------------------------------------------------------------
# Patch classify_risk and RainfallFeatureCalculator for all tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_leaf_imports():
    """
    Patch the two lazily-imported module-level callables so they never
    touch real YAML / model files during tests.
    """
    canonical_mock = _mock_canonical()
    feat_set_mock  = _mock_feature_set()

    feat_calc_instance = MagicMock()
    feat_calc_instance.calculate.return_value = feat_set_mock

    with patch('src.risk.risk_scheduler.classify_risk',
               return_value=canonical_mock,
               create=True), \
         patch('src.risk.risk_scheduler.RainfallFeatureCalculator',
               return_value=feat_calc_instance,
               create=True), \
         patch('src.risk.risk_scheduler.DailyRecord',
               side_effect=lambda **kw: kw,
               create=True):
        yield


# ---------------------------------------------------------------------------
# 1. Successful end-to-end orchestration
# ---------------------------------------------------------------------------

class TestSuccessfulOrchestration:

    def test_returns_list_of_dicts(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A])
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_result_contains_required_keys(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A])
        state  = result[0]
        for key in ['location_id', 'latitude', 'longitude', 'last_updated',
                    'observation_date', 'stale', 'error_reason', 'risk_payload']:
            assert key in state, f"Missing key: {key}"

    def test_stale_is_false_on_success(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A])
        assert result[0]['stale'] is False

    def test_error_reason_is_none_on_success(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A])
        assert result[0]['error_reason'] is None

    def test_observation_date_is_today(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A])
        assert result[0]['observation_date'] == TODAY

    def test_risk_payload_is_not_none(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A])
        assert result[0]['risk_payload'] is not None

    def test_multiple_locations_processed(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A, LOC_B])
        assert len(result) == 2
        ids = {r['location_id'] for r in result}
        assert 'LOC-A' in ids
        assert 'LOC-B' in ids

    def test_rainfall_service_called_once_per_location(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        sched.refresh_locations([LOC_A, LOC_B])
        assert sched._rainfall_svc.get_recent_rainfall.call_count == 2

    def test_state_written_to_file_on_success(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        sched  = _build_scheduler(tmp_path)
        sched.refresh_locations([LOC_A])
        assert os.path.exists(state_file)
        with open(state_file, 'r', encoding='utf-8') as f:
            persisted = json.load(f)
        assert 'LOC-A' in persisted


# ---------------------------------------------------------------------------
# 2. Caching logic
# ---------------------------------------------------------------------------

class TestCachingLogic:

    def test_cache_hit_skips_rainfall_fetch(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        # Pre-populate cache with today's data
        sched._cache['LOC-A'] = {
            'location_id':      'LOC-A',
            'latitude':         27.5,
            'longitude':        85.5,
            'last_updated':     datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'observation_date': TODAY,
            'data_age_days':    0.0,
            'stale':            False,
            'error_reason':     None,
            'risk_payload':     {"final_risk_level": "LOW"},
        }
        sched.refresh_locations([LOC_A])
        sched._rainfall_svc.get_recent_rainfall.assert_not_called()

    def test_cache_hit_returns_cached_payload(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        cached_payload = {"final_risk_level": "CACHED_LEVEL"}
        sched._cache['LOC-A'] = {
            'location_id': 'LOC-A', 'latitude': 27.5, 'longitude': 85.5,
            'last_updated': TODAY, 'observation_date': TODAY,
            'data_age_days': 0.0, 'stale': False, 'error_reason': None,
            'risk_payload': cached_payload,
        }
        result = sched.refresh_locations([LOC_A])
        assert result[0]['risk_payload'] == cached_payload

    def test_force_true_bypasses_cache(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        sched._cache['LOC-A'] = {
            'location_id': 'LOC-A', 'latitude': 27.5, 'longitude': 85.5,
            'last_updated': TODAY, 'observation_date': TODAY,
            'data_age_days': 0.0, 'stale': False, 'error_reason': None,
            'risk_payload': {"final_risk_level": "OLD"},
        }
        sched.refresh_locations([LOC_A], force=True)
        sched._rainfall_svc.get_recent_rainfall.assert_called_once()

    def test_stale_cache_triggers_refetch(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        # Cached entry with OLD date (stale)
        sched._cache['LOC-A'] = {
            'location_id': 'LOC-A', 'latitude': 27.5, 'longitude': 85.5,
            'last_updated': OLD_DATE, 'observation_date': OLD_DATE,
            'data_age_days': 5.0, 'stale': True, 'error_reason': None,
            'risk_payload': None,
        }
        sched.refresh_locations([LOC_A])
        sched._rainfall_svc.get_recent_rainfall.assert_called_once()

    def test_yesterday_cache_triggers_refetch(self, tmp_path):
        """Cache from yesterday (different date) must trigger a fresh fetch."""
        sched = _build_scheduler(tmp_path)
        sched._cache['LOC-A'] = {
            'location_id': 'LOC-A', 'latitude': 27.5, 'longitude': 85.5,
            'last_updated': YESTERDAY, 'observation_date': YESTERDAY,
            'data_age_days': 1.0, 'stale': False, 'error_reason': None,
            'risk_payload': {"final_risk_level": "YESTERDAY"},
        }
        sched.refresh_locations([LOC_A])
        sched._rainfall_svc.get_recent_rainfall.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Failure handling — stale state retention
# ---------------------------------------------------------------------------

class TestFailureHandling:

    def test_previous_state_retained_on_api_failure(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        prev_payload = {"final_risk_level": "LOW"}
        sched._cache['LOC-A'] = {
            'location_id': 'LOC-A', 'latitude': 27.5, 'longitude': 85.5,
            'last_updated': YESTERDAY, 'observation_date': YESTERDAY,
            'data_age_days': 1.0, 'stale': False, 'error_reason': None,
            'risk_payload': prev_payload,
        }
        # Make the rainfall service fail
        sched._rainfall_svc.get_recent_rainfall.side_effect = RuntimeError("GEE timeout")
        result = sched.refresh_locations([LOC_A])
        # Previous payload retained
        assert result[0]['risk_payload'] == prev_payload

    def test_error_reason_set_on_failure(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        sched._rainfall_svc.get_recent_rainfall.side_effect = RuntimeError("Connection refused")
        result = sched.refresh_locations([LOC_A])
        assert result[0]['error_reason'] is not None
        assert "Connection refused" in result[0]['error_reason']

    def test_stale_true_when_data_old_enough(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        sched._cache['LOC-A'] = {
            'location_id': 'LOC-A', 'latitude': 27.5, 'longitude': 85.5,
            'last_updated': OLD_DATE, 'observation_date': OLD_DATE,
            'data_age_days': 5.0, 'stale': False, 'error_reason': None,
            'risk_payload': {"final_risk_level": "LOW"},
        }
        sched._rainfall_svc.get_recent_rainfall.side_effect = RuntimeError("Timeout")
        result = sched.refresh_locations([LOC_A])
        assert result[0]['stale'] is True

    def test_no_previous_state_on_first_failure(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        sched._rainfall_svc.get_recent_rainfall.side_effect = RuntimeError("First run fails")
        result = sched.refresh_locations([LOC_A])
        assert result[0]['risk_payload'] is None
        assert result[0]['stale'] is True
        assert result[0]['error_reason'] is not None

    def test_one_failure_does_not_abort_other_locations(self, tmp_path):
        """A failure for LOC-A must not prevent LOC-B from being processed."""
        sched = _build_scheduler(tmp_path)
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("LOC-A fails")
            return _make_rainfall_records()
        sched._rainfall_svc.get_recent_rainfall.side_effect = side_effect

        result = sched.refresh_locations([LOC_A, LOC_B])
        assert len(result) == 2
        loc_b_result = next(r for r in result if r['location_id'] == 'LOC-B')
        assert loc_b_result['stale'] is False


# ---------------------------------------------------------------------------
# 4. dry_run mode
# ---------------------------------------------------------------------------

class TestDryRun:

    def test_dry_run_does_not_write_state_file(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        sched = _build_scheduler(tmp_path)
        sched._state_path = state_file
        sched.refresh_locations([LOC_A], dry_run=True)
        assert not os.path.exists(state_file)

    def test_dry_run_returns_results(self, tmp_path):
        sched  = _build_scheduler(tmp_path)
        result = sched.refresh_locations([LOC_A], dry_run=True)
        assert len(result) == 1
        assert result[0]['location_id'] == 'LOC-A'

    def test_dry_run_does_not_update_in_memory_cache(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        assert 'LOC-A' not in sched._cache
        sched.refresh_locations([LOC_A], dry_run=True)
        assert 'LOC-A' not in sched._cache

    def test_normal_run_updates_in_memory_cache(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        sched.refresh_locations([LOC_A], dry_run=False)
        assert 'LOC-A' in sched._cache


# ---------------------------------------------------------------------------
# 5. State persistence helpers
# ---------------------------------------------------------------------------

class TestStatePersistence:

    def test_load_state_reads_existing_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        existing = {'LOC-Z': {'location_id': 'LOC-Z', 'stale': False}}
        state_file.write_text(json.dumps(existing), encoding='utf-8')

        sched = RiskScheduler.__new__(RiskScheduler)
        sched._state_path          = str(state_file)
        sched._gee_config          = "fake"
        sched._stale_threshold_days = 2
        sched._rainfall_days       = 15
        sched._model_path          = None
        sched._rainfall_trigger_config = None
        sched._risk_engine_config  = None
        sched._risk_levels_config  = None
        sched._predictor           = None
        sched._rainfall_svc        = None
        sched._trigger_engine      = None
        sched._risk_engine         = None
        sched._cache               = {}
        sched._load_state()

        assert 'LOC-Z' in sched._cache

    def test_load_state_handles_corrupt_json(self, tmp_path):
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("{broken json", encoding='utf-8')

        sched = RiskScheduler.__new__(RiskScheduler)
        sched._state_path          = str(state_file)
        sched._cache               = {}
        sched._load_state()   # must not raise
        assert sched._cache == {}

    def test_get_state_returns_none_for_unknown(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        assert sched.get_state("UNKNOWN-LOC") is None

    def test_get_all_states_returns_copy(self, tmp_path):
        sched = _build_scheduler(tmp_path)
        sched._cache = {'X': {'stale': False}}
        all_states = sched.get_all_states()
        assert 'X' in all_states
        # Mutating the returned dict must not affect internal cache
        all_states['Y'] = {}
        assert 'Y' not in sched._cache


# ---------------------------------------------------------------------------
# 6. LocationRiskState dataclass
# ---------------------------------------------------------------------------

class TestLocationRiskState:

    def test_to_dict_contains_all_fields(self):
        state = LocationRiskState(
            location_id='TEST', latitude=27.5, longitude=85.5,
            last_updated='2026-10-01T12:00:00+00:00',
            observation_date='2026-10-01', data_age_days=0.0,
            stale=False, error_reason=None, risk_payload={"key": "val"}
        )
        d = state.to_dict()
        for key in ['location_id', 'latitude', 'longitude', 'last_updated',
                    'observation_date', 'data_age_days', 'stale',
                    'error_reason', 'risk_payload']:
            assert key in d

    def test_stale_defaults_false(self):
        state = LocationRiskState(
            location_id=None, latitude=0.0, longitude=0.0,
            last_updated=None, observation_date=None, data_age_days=None,
        )
        assert state.stale is False

    def test_error_reason_defaults_none(self):
        state = LocationRiskState(
            location_id=None, latitude=0.0, longitude=0.0,
            last_updated=None, observation_date=None, data_age_days=None,
        )
        assert state.error_reason is None
