"""
tests/test_risk_store.py
--------------------------
Unit tests for src/risk/risk_store.py (SQLiteRiskStore).
All tests use ':memory:' SQLite — fast, isolated, no disk I/O.
No external dependencies.
"""

import sys
import os
import datetime
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.risk_store import SQLiteRiskStore, RiskStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store() -> SQLiteRiskStore:
    """Fresh in-memory SQLiteRiskStore for each test."""
    return SQLiteRiskStore(db_path=":memory:")


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _make_result(
    location_id:  str = "LOC-A",
    timestamp:    str = None,
    obs_date:     str = "2026-10-01",
    sus_prob:     float = 0.72,
    sus_class:    str = "HIGH",
    r1d:          float = 5.0,
    r3d:          float = 15.0,
    r7d:          float = 35.0,
    r15d:         float = 75.0,
    trig_score:   int = 1,
    trig_state:   str = "WATCH",
    dyn_risk:     str = "MODERATE",
    risk_level:   str = "MODERATE",
    data_source:  str = "CHIRPS",
    stale:        bool = False,
    error_info:   str = None,
    lat:          float = 27.5,
    lon:          float = 85.5,
) -> dict:
    return {
        "location_id":               location_id,
        "latitude":                  lat,
        "longitude":                 lon,
        "timestamp":                 timestamp or _now_utc(),
        "observation_date":          obs_date,
        "susceptibility_probability": sus_prob,
        "susceptibility_class":      sus_class,
        "rainfall_1d":               r1d,
        "rainfall_3d":               r3d,
        "rainfall_7d":               r7d,
        "rainfall_15d":              r15d,
        "rainfall_trigger_score":    trig_score,
        "rainfall_trigger_state":    trig_state,
        "dynamic_risk":              dyn_risk,
        "risk_level":                risk_level,
        "data_source":               data_source,
        "stale":                     stale,
        "error_info":                error_info,
    }


# ---------------------------------------------------------------------------
# 1. Abstract interface contract
# ---------------------------------------------------------------------------

class TestAbstractInterface:

    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError):
            RiskStore()

    def test_sqlite_store_is_risk_store_instance(self, store):
        assert isinstance(store, RiskStore)

    def test_all_abstract_methods_implemented(self, store):
        """Verify all 5 interface methods exist and are callable."""
        for method in ['save_risk_result', 'get_latest_risk',
                       'get_risk_history', 'get_last_successful_update',
                       'mark_stale']:
            assert callable(getattr(store, method, None)), \
                f"Method {method} not found or not callable"


# ---------------------------------------------------------------------------
# 2. save_risk_result & get_latest_risk
# ---------------------------------------------------------------------------

class TestSaveAndGetLatest:

    def test_save_and_retrieve_basic_record(self, store):
        rec = _make_result()
        store.save_risk_result(rec)
        latest = store.get_latest_risk("LOC-A")
        assert latest is not None
        assert latest['location_id'] == "LOC-A"

    def test_get_latest_returns_newest_by_timestamp(self, store):
        """When multiple records exist, the newest timestamp wins."""
        old_ts  = "2026-09-30T12:00:00+00:00"
        new_ts  = "2026-10-01T12:00:00+00:00"
        store.save_risk_result(_make_result(timestamp=old_ts, r1d=1.0))
        store.save_risk_result(_make_result(timestamp=new_ts, r1d=99.0))
        latest = store.get_latest_risk("LOC-A")
        assert latest['rainfall_1d'] == 99.0
        assert latest['timestamp'] == new_ts

    def test_get_latest_returns_none_for_unknown_location(self, store):
        assert store.get_latest_risk("UNKNOWN-LOC") is None

    def test_save_requires_location_id(self, store):
        bad = {"timestamp": _now_utc(), "rainfall_1d": 5.0}
        with pytest.raises(ValueError, match="location_id"):
            store.save_risk_result(bad)

    def test_save_requires_timestamp(self, store):
        bad = {"location_id": "LOC-A", "rainfall_1d": 5.0}
        with pytest.raises(ValueError, match="timestamp"):
            store.save_risk_result(bad)

    def test_all_schema_fields_persisted_and_retrieved(self, store):
        rec = _make_result()
        store.save_risk_result(rec)
        latest = store.get_latest_risk("LOC-A")
        for field in ['latitude', 'longitude', 'observation_date',
                      'susceptibility_probability', 'susceptibility_class',
                      'rainfall_1d', 'rainfall_3d', 'rainfall_7d', 'rainfall_15d',
                      'rainfall_trigger_score', 'rainfall_trigger_state',
                      'dynamic_risk', 'risk_level', 'data_source', 'stale', 'error_info']:
            assert field in latest, f"Missing field: {field}"

    def test_latitude_longitude_preserved(self, store):
        store.save_risk_result(_make_result(lat=12.34, lon=56.78))
        latest = store.get_latest_risk("LOC-A")
        assert latest['latitude']  == 12.34
        assert latest['longitude'] == 56.78

    def test_susceptibility_values_preserved(self, store):
        store.save_risk_result(_make_result(sus_prob=0.8765, sus_class="VERY_HIGH"))
        latest = store.get_latest_risk("LOC-A")
        assert abs(latest['susceptibility_probability'] - 0.8765) < 1e-6
        assert latest['susceptibility_class'] == "VERY_HIGH"

    def test_rainfall_features_preserved(self, store):
        store.save_risk_result(_make_result(r1d=10.5, r3d=30.0, r7d=55.0, r15d=120.0))
        latest = store.get_latest_risk("LOC-A")
        assert latest['rainfall_1d']  == 10.5
        assert latest['rainfall_3d']  == 30.0
        assert latest['rainfall_7d']  == 55.0
        assert latest['rainfall_15d'] == 120.0

    def test_multiple_locations_isolated(self, store):
        store.save_risk_result(_make_result(location_id="LOC-A", r1d=1.0))
        store.save_risk_result(_make_result(location_id="LOC-B", r1d=99.0))
        assert store.get_latest_risk("LOC-A")['rainfall_1d'] == 1.0
        assert store.get_latest_risk("LOC-B")['rainfall_1d'] == 99.0

    def test_append_only_does_not_overwrite_previous(self, store):
        """Saving a new record must not delete the old one."""
        store.save_risk_result(_make_result(timestamp="2026-09-30T12:00:00+00:00"))
        store.save_risk_result(_make_result(timestamp="2026-10-01T12:00:00+00:00"))
        history = store.get_risk_history("LOC-A")
        assert len(history) == 2


# ---------------------------------------------------------------------------
# 3. get_risk_history
# ---------------------------------------------------------------------------

class TestGetRiskHistory:

    def _insert_n(self, store: SQLiteRiskStore, n: int, loc: str = "LOC-A") -> list:
        """Insert n records with distinct timestamps (1 second apart)."""
        timestamps = []
        base = datetime.datetime(2026, 9, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
        for i in range(n):
            ts = (base + datetime.timedelta(seconds=i)).isoformat()
            store.save_risk_result(_make_result(location_id=loc, timestamp=ts))
            timestamps.append(ts)
        return timestamps

    def test_returns_all_records_when_below_limit(self, store):
        self._insert_n(store, 5)
        history = store.get_risk_history("LOC-A", limit=30)
        assert len(history) == 5

    def test_history_sorted_newest_first(self, store):
        self._insert_n(store, 3)
        history = store.get_risk_history("LOC-A")
        ts_list = [h['timestamp'] for h in history]
        assert ts_list == sorted(ts_list, reverse=True)

    def test_limit_respected(self, store):
        self._insert_n(store, 10)
        history = store.get_risk_history("LOC-A", limit=3)
        assert len(history) == 3

    def test_limit_1_returns_single_newest(self, store):
        timestamps = self._insert_n(store, 5)
        newest_ts  = max(timestamps)
        history = store.get_risk_history("LOC-A", limit=1)
        assert len(history) == 1
        assert history[0]['timestamp'] == newest_ts

    def test_empty_history_for_unknown_location(self, store):
        history = store.get_risk_history("NONEXISTENT")
        assert history == []

    def test_locations_do_not_bleed_into_each_other(self, store):
        self._insert_n(store, 5, loc="LOC-A")
        self._insert_n(store, 3, loc="LOC-B")
        assert len(store.get_risk_history("LOC-A")) == 5
        assert len(store.get_risk_history("LOC-B")) == 3


# ---------------------------------------------------------------------------
# 4. mark_stale
# ---------------------------------------------------------------------------

class TestMarkStale:

    def test_mark_stale_inserts_new_stale_row(self, store):
        store.save_risk_result(_make_result(stale=False))
        store.mark_stale("LOC-A", "GEE timeout")
        history = store.get_risk_history("LOC-A")
        assert len(history) == 2   # original + stale copy

    def test_latest_after_mark_stale_has_stale_true(self, store):
        store.save_risk_result(_make_result(stale=False))
        store.mark_stale("LOC-A", "Connection error")
        latest = store.get_latest_risk("LOC-A")
        assert latest['stale'] in (1, True)

    def test_error_reason_stored_in_error_info(self, store):
        store.save_risk_result(_make_result())
        store.mark_stale("LOC-A", "Timeout after 30s")
        latest = store.get_latest_risk("LOC-A")
        assert "Timeout after 30s" in str(latest['error_info'])

    def test_mark_stale_on_unknown_location_creates_sentinel(self, store):
        """mark_stale on a never-seen location must not raise; inserts sentinel."""
        store.mark_stale("BRAND-NEW", "First failure")
        latest = store.get_latest_risk("BRAND-NEW")
        assert latest is not None
        assert latest['stale'] in (1, True)
        assert "First failure" in str(latest['error_info'])

    def test_previous_good_record_preserved_after_stale(self, store):
        """The original non-stale record must still be in history."""
        store.save_risk_result(_make_result(stale=False, r1d=42.0))
        store.mark_stale("LOC-A", "Error")
        history = store.get_risk_history("LOC-A")
        non_stale = [h for h in history if not h['stale']]
        assert len(non_stale) == 1
        assert non_stale[0]['rainfall_1d'] == 42.0


# ---------------------------------------------------------------------------
# 5. get_last_successful_update
# ---------------------------------------------------------------------------

class TestGetLastSuccessfulUpdate:

    def test_returns_datetime_for_non_stale_record(self, store):
        store.save_risk_result(_make_result(stale=False,
                                             timestamp="2026-10-01T12:00:00+00:00"))
        result = store.get_last_successful_update("LOC-A")
        assert isinstance(result, datetime.datetime)

    def test_datetime_is_timezone_aware(self, store):
        store.save_risk_result(_make_result(stale=False,
                                             timestamp="2026-10-01T12:00:00+00:00"))
        result = store.get_last_successful_update("LOC-A")
        assert result.tzinfo is not None

    def test_returns_none_when_only_stale_records(self, store):
        store.save_risk_result(_make_result(stale=True,
                                             timestamp="2026-10-01T12:00:00+00:00"))
        result = store.get_last_successful_update("LOC-A")
        assert result is None

    def test_returns_none_for_unknown_location(self, store):
        assert store.get_last_successful_update("UNKNOWN") is None

    def test_returns_most_recent_non_stale_timestamp(self, store):
        ts_old  = "2026-09-30T12:00:00+00:00"
        ts_new  = "2026-10-01T12:00:00+00:00"
        ts_stale= "2026-10-01T15:00:00+00:00"
        store.save_risk_result(_make_result(stale=False, timestamp=ts_old))
        store.save_risk_result(_make_result(stale=False, timestamp=ts_new))
        store.save_risk_result(_make_result(stale=True,  timestamp=ts_stale))
        result = store.get_last_successful_update("LOC-A")
        assert result.isoformat().startswith("2026-10-01T12:00:00")

    def test_stale_record_after_mark_stale_not_returned(self, store):
        store.save_risk_result(_make_result(stale=False,
                                             timestamp="2026-10-01T10:00:00+00:00"))
        store.mark_stale("LOC-A", "Error")
        result = store.get_last_successful_update("LOC-A")
        # Must return the original non-stale record's timestamp
        assert result is not None
        assert result.year == 2026


# ---------------------------------------------------------------------------
# 6. Data integrity & schema validation
# ---------------------------------------------------------------------------

class TestDataIntegrity:

    def test_id_is_auto_assigned(self, store):
        store.save_risk_result(_make_result())
        latest = store.get_latest_risk("LOC-A")
        assert 'id' in latest
        assert latest['id'] is not None

    def test_ids_are_unique_across_rows(self, store):
        store.save_risk_result(_make_result(timestamp="2026-09-30T00:00:00+00:00"))
        store.save_risk_result(_make_result(timestamp="2026-10-01T00:00:00+00:00"))
        history = store.get_risk_history("LOC-A")
        ids = [h['id'] for h in history]
        assert len(ids) == len(set(ids))

    def test_none_values_stored_and_retrieved_as_none(self, store):
        rec = _make_result(error_info=None, r3d=None)
        store.save_risk_result(rec)
        latest = store.get_latest_risk("LOC-A")
        assert latest['error_info'] is None
        assert latest['rainfall_3d'] is None

    def test_stale_stored_as_integer(self, store):
        store.save_risk_result(_make_result(stale=True))
        latest = store.get_latest_risk("LOC-A")
        # SQLite stores as INTEGER; value must be truthy
        assert latest['stale'] in (1, True)

    def test_returns_dict_not_sqlite_row(self, store):
        store.save_risk_result(_make_result())
        latest = store.get_latest_risk("LOC-A")
        assert isinstance(latest, dict)

    def test_history_list_contains_dicts(self, store):
        store.save_risk_result(_make_result())
        history = store.get_risk_history("LOC-A")
        for item in history:
            assert isinstance(item, dict)
