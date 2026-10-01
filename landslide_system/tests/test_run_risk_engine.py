"""
tests/test_run_risk_engine.py
------------------------------
Phase 5.10 CLI Integration Tests.

Tests run_risk_engine in --mock mode via both:
  1. Direct function call (run_assessment / format_report) for fast unit coverage.
  2. subprocess call to verify the full CLI entry-point end-to-end.

All tests are 100% offline (no GEE, no live CHIRPS).
"""

import sys
import os
import subprocess
import json
import datetime
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.run_risk_engine import (
    run_assessment,
    format_report,
    parse_args,
    main,
    SEPARATOR,
)
from src.risk.risk_store import SQLiteRiskStore

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

DEFAULT_LAT = 27.5
DEFAULT_LON = 85.5
DEFAULT_LOC = "TEST-LOC"

RUNNER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'src', 'risk', 'run_risk_engine.py')
)
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)


@pytest.fixture
def tmp_db(tmp_path) -> str:
    """Temporary SQLite file path (not :memory: — subprocess needs a real file)."""
    return str(tmp_path / "test_risk.db")


@pytest.fixture
def tmp_state(tmp_path) -> str:
    return str(tmp_path / "state.json")


def _run_mock(lat=DEFAULT_LAT, lon=DEFAULT_LON, loc=DEFAULT_LOC,
              db_path=":memory:", state_path=None, tmp_path=None) -> dict:
    """Run assessment in mock mode and return the result dict."""
    if db_path == ":memory:" and state_path is None and tmp_path is not None:
        state_path = str(tmp_path / "state.json")
    return run_assessment(
        lat=lat, lon=lon, location_id=loc, db_path=db_path,
        mock=True, state_path=state_path,
    )


# ---------------------------------------------------------------------------
# 1. run_assessment() — direct function tests (fastest, no subprocess)
# ---------------------------------------------------------------------------

class TestRunAssessmentMock:

    def test_returns_dict(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert isinstance(result, dict)

    def test_contains_state_key(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert 'state' in result

    def test_contains_payload_key(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert 'payload' in result

    def test_mock_flag_set_in_result(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert result['mock'] is True

    def test_location_id_preserved(self, tmp_path):
        result = _run_mock(loc="MY-LOC", tmp_path=tmp_path)
        assert result['location_id'] == "MY-LOC"

    def test_coordinates_preserved(self, tmp_path):
        result = _run_mock(lat=13.5, lon=100.2, tmp_path=tmp_path)
        assert result['lat'] == 13.5
        assert result['lon'] == 100.2

    def test_state_not_stale_on_success(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert result['state'].get('stale') is False

    def test_error_reason_none_on_success(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert result['state'].get('error_reason') is None

    def test_observation_date_is_today(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        assert result['state'].get('observation_date') == datetime.date.today().isoformat()

    def test_payload_has_susceptibility_fields(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        payload = result['payload']
        assert 'susceptibility_probability' in payload
        assert 'susceptibility_class' in payload

    def test_payload_has_rainfall_trigger_fields(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        payload = result['payload']
        assert 'rainfall_trigger_state' in payload
        assert 'rainfall_trigger_score' in payload

    def test_feat_has_rainfall_windows(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        feat = result['feat']
        for key in ['rainfall_1d', 'rainfall_3d', 'rainfall_7d', 'rainfall_15d']:
            assert key in feat

    def test_canon_has_ui_metadata(self, tmp_path):
        result = _run_mock(tmp_path=tmp_path)
        canon = result['canon']
        for key in ['level_enum', 'numeric_code', 'color_hex', 'ui_severity']:
            assert key in canon

    def test_persists_record_to_sqlite(self, tmp_path):
        db = str(tmp_path / "check.db")
        _run_mock(db_path=db, tmp_path=tmp_path)
        store = SQLiteRiskStore(db_path=db)
        latest = store.get_latest_risk(DEFAULT_LOC)
        assert latest is not None


# ---------------------------------------------------------------------------
# 2. format_report() — report content verification
# ---------------------------------------------------------------------------

class TestFormatReport:

    @pytest.fixture(autouse=True)
    def _result(self, tmp_path):
        self._res = _run_mock(tmp_path=tmp_path)

    def test_contains_separator(self):
        report = format_report(self._res)
        assert SEPARATOR in report

    def test_contains_title(self):
        report = format_report(self._res)
        assert "LANDSLIDE EARLY WARNING SYSTEM" in report

    def test_contains_mock_banner(self):
        report = format_report(self._res)
        assert "TEST / MOCK DATA MODE" in report

    def test_contains_mode_label(self):
        report = format_report(self._res)
        assert "[MODE: MOCK]" in report

    def test_contains_location_id(self):
        report = format_report(self._res)
        assert DEFAULT_LOC in report

    def test_contains_static_susceptibility_header(self):
        report = format_report(self._res)
        assert "--- STATIC SUSCEPTIBILITY ---" in report

    def test_contains_dynamic_rainfall_header(self):
        report = format_report(self._res)
        assert "--- DYNAMIC RAINFALL ---" in report

    def test_contains_composite_risk_header(self):
        report = format_report(self._res)
        assert "--- COMPOSITE OPERATIONAL RISK ---" in report

    def test_contains_probability_line(self):
        report = format_report(self._res)
        assert "Probability:" in report

    def test_contains_class_line(self):
        report = format_report(self._res)
        assert "Class:" in report

    def test_contains_rainfall_1d(self):
        report = format_report(self._res)
        assert "Rainfall 1D:" in report

    def test_contains_rainfall_3d(self):
        report = format_report(self._res)
        assert "Rainfall 3D:" in report

    def test_contains_rainfall_7d(self):
        report = format_report(self._res)
        assert "Rainfall 7D:" in report

    def test_contains_rainfall_15d(self):
        report = format_report(self._res)
        assert "Rainfall 15D:" in report

    def test_contains_api_line(self):
        report = format_report(self._res)
        assert "API (15-Day):" in report

    def test_contains_trigger_state_line(self):
        report = format_report(self._res)
        assert "Rainfall Trigger State:" in report

    def test_contains_dynamic_risk_line(self):
        report = format_report(self._res)
        assert "Dynamic Risk Level:" in report

    def test_contains_action_line(self):
        report = format_report(self._res)
        assert "Action:" in report

    def test_contains_storage_line_with_db_path(self):
        report = format_report(self._res)
        assert "Storage:" in report
        assert "SQLite" in report

    def test_contains_hex_color(self):
        report = format_report(self._res)
        assert "#" in report     # hex color code present

    def test_contains_numeric_code(self):
        report = format_report(self._res)
        assert "Code:" in report

    def test_mm_unit_present(self):
        report = format_report(self._res)
        assert " mm" in report


# ---------------------------------------------------------------------------
# 3. parse_args() — argument parser
# ---------------------------------------------------------------------------

class TestParseArgs:

    def test_lat_lon_required(self):
        with pytest.raises(SystemExit):
            parse_args([])

    def test_basic_parse(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5"])
        assert args.lat == 27.5
        assert args.lon == 85.5

    def test_mock_flag_default_false(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5"])
        assert args.mock is False

    def test_mock_flag_set(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5", "--mock"])
        assert args.mock is True

    def test_location_id_optional(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5"])
        assert args.location_id is None

    def test_location_id_set(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5",
                           "--location-id", "KULLU"])
        assert args.location_id == "KULLU"

    def test_db_path_default(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5"])
        assert "risk_store.db" in args.db_path

    def test_db_path_override(self):
        args = parse_args(["--lat", "27.5", "--lon", "85.5",
                           "--db-path", "/tmp/custom.db"])
        assert args.db_path == "/tmp/custom.db"


# ---------------------------------------------------------------------------
# 4. main() — entry-point integration
# ---------------------------------------------------------------------------

class TestMain:

    def test_main_mock_returns_zero(self, tmp_path, capsys):
        db  = str(tmp_path / "main.db")
        st  = str(tmp_path / "state.json")
        ret = main([
            "--lat", "27.5", "--lon", "85.5",
            "--location-id", "MAIN-LOC",
            "--mock",
            "--db-path", db,
        ])
        assert ret == 0

    def test_main_mock_stdout_has_banner(self, tmp_path, capsys):
        db  = str(tmp_path / "main.db")
        main([
            "--lat", "27.5", "--lon", "85.5",
            "--mock",
            "--db-path", db,
        ])
        captured = capsys.readouterr()
        assert "TEST / MOCK DATA MODE" in captured.out

    def test_main_mock_stdout_has_separator(self, tmp_path, capsys):
        db = str(tmp_path / "sep.db")
        main(["--lat", "27.5", "--lon", "85.5", "--mock", "--db-path", db])
        captured = capsys.readouterr()
        assert SEPARATOR in captured.out

    def test_main_persists_record_to_db(self, tmp_path, capsys):
        db  = str(tmp_path / "persist.db")
        main([
            "--lat", "27.5", "--lon", "85.5",
            "--location-id", "PERSIST-LOC",
            "--mock",
            "--db-path", db,
        ])
        store  = SQLiteRiskStore(db_path=db)
        latest = store.get_latest_risk("PERSIST-LOC")
        assert latest is not None
        assert latest['location_id'] == "PERSIST-LOC"


# ---------------------------------------------------------------------------
# 5. subprocess CLI smoke test
# ---------------------------------------------------------------------------

class TestSubprocessCLI:

    def test_subprocess_mock_exit_code_zero(self, tmp_path):
        db = str(tmp_path / "sub.db")
        proc = subprocess.run(
            [
                sys.executable, RUNNER_PATH,
                "--lat", "27.5", "--lon", "85.5",
                "--location-id", "SUB-LOC",
                "--mock",
                "--db-path", db,
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert proc.returncode == 0, f"STDERR: {proc.stderr}"

    def test_subprocess_mock_output_has_required_headers(self, tmp_path):
        db = str(tmp_path / "sub2.db")
        proc = subprocess.run(
            [
                sys.executable, RUNNER_PATH,
                "--lat", "27.5", "--lon", "85.5",
                "--mock",
                "--db-path", db,
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        out = proc.stdout
        for header in [
            "LANDSLIDE EARLY WARNING SYSTEM",
            "TEST / MOCK DATA MODE",
            "--- STATIC SUSCEPTIBILITY ---",
            "--- DYNAMIC RAINFALL ---",
            "--- COMPOSITE OPERATIONAL RISK ---",
        ]:
            assert header in out, f"Missing header in output: {header!r}"

    def test_subprocess_mock_contains_mm_unit(self, tmp_path):
        db = str(tmp_path / "sub3.db")
        proc = subprocess.run(
            [sys.executable, RUNNER_PATH,
             "--lat", "27.5", "--lon", "85.5", "--mock", "--db-path", db],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert " mm" in proc.stdout

    def test_subprocess_mock_persists_to_db(self, tmp_path):
        db = str(tmp_path / "sub4.db")
        subprocess.run(
            [sys.executable, RUNNER_PATH,
             "--lat", "27.5", "--lon", "85.5",
             "--location-id", "SUB4-LOC",
             "--mock", "--db-path", db],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        store  = SQLiteRiskStore(db_path=db)
        latest = store.get_latest_risk("SUB4-LOC")
        assert latest is not None
