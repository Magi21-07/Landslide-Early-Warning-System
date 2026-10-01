"""
src/risk/run_risk_engine.py
----------------------------
Phase 5.10: End-to-End Real-Time Risk Engine CLI Runner.

Wires together RiskScheduler, SQLiteRiskStore, and all Phase 5
risk/rainfall components into a single standalone entry-point.

Usage:
    python src/risk/run_risk_engine.py --lat 27.5 --lon 85.5 --mock
    python src/risk/run_risk_engine.py --lat 31.6862 --lon 76.5213 \\
           --location-id KULLU --db-path data/processed/risk_store.db
"""

import argparse
import datetime
import json
import sys
import os
import logging

# Ensure project root is on sys.path when invoked directly
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s %(name)s: %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger('run_risk_engine')

SEPARATOR = "=" * 60
MOCK_RAINFALL_MM = 12.0     # synthetic daily rainfall used in --mock mode
TODAY = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Recommended action strings (derived from risk level)
# ---------------------------------------------------------------------------

_ACTIONS = {
    "LOW":      "No immediate action required. Routine monitoring.",
    "MODERATE": "Increase monitoring frequency. Alert field teams.",
    "HIGH":     "Deploy field inspection teams. Issue public advisory.",
    "CRITICAL": "Evacuate at-risk communities. Activate emergency protocol.",
}


# ---------------------------------------------------------------------------
# Mock engine factories
# ---------------------------------------------------------------------------

def _build_mock_predictor(sus_prob: float = 0.68, sus_class: str = "HIGH"):
    """Return a drop-in mock for LandslidePredictor."""
    class _MockPredictor:
        def predict(self, features):
            return {"probability": sus_prob, "susceptibility": sus_class}
    return _MockPredictor()


def _build_mock_rainfall_service(lat: float, lon: float, loc_id: str):
    """Return a drop-in mock for RainfallService with synthetic rainfall."""
    from src.risk.rainfall_service import DailyRainfallRecord

    def _get_recent_rainfall(latitude, longitude, days=15, location_id=None, **kw):
        records = []
        base = datetime.date.fromisoformat(TODAY)
        for i in range(days):
            d = base - datetime.timedelta(days=i)
            # Synthetic pattern: moderate rainfall with a recent spike
            mm = MOCK_RAINFALL_MM + (30.0 if i == 1 else 0.0)
            records.append({
                "location_id": location_id,
                "latitude":    latitude,
                "longitude":   longitude,
                "date":        d.isoformat(),
                "rainfall_mm": mm,
                "source":      "MOCK/SYNTHETIC",
                "retrieved_at": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            })
        return records

    class _MockRainfallService:
        def get_recent_rainfall(self, latitude, longitude,
                                 days=15, location_id=None, **kw):
            return _get_recent_rainfall(latitude, longitude, days, location_id)

    return _MockRainfallService()


# ---------------------------------------------------------------------------
# Core evaluation function (importable for tests)
# ---------------------------------------------------------------------------

def run_assessment(
    lat:         float,
    lon:         float,
    location_id: str,
    db_path:     str,
    mock:        bool = False,
    rainfall_trigger_config: str = None,
    risk_engine_config:      str = None,
    risk_levels_config:      str = None,
    state_path:              str = None,
) -> dict:
    """
    Run the full risk assessment pipeline and return a result dict.

    Parameters
    ----------
    lat, lon       : Geographic coordinates.
    location_id    : Human-readable identifier.
    db_path        : Path to SQLite state file.
    mock           : If True, inject mock engines (offline mode).
    *_config       : Optional overrides for YAML config paths.
    state_path     : Override for scheduler JSON cache path.

    Returns
    -------
    dict : full result including risk_payload, mode, db_path.
    """
    from src.risk.risk_scheduler import RiskScheduler
    from src.risk.risk_store import SQLiteRiskStore

    # --- Build scheduler (dry_run so it does NOT write JSON cache) ---
    sched = RiskScheduler(
        gee_config              = "mock" if mock else "",
        state_path              = state_path or "data/processed/latest_risk_state.json",
        rainfall_days           = 15,
        rainfall_trigger_config = rainfall_trigger_config,
        risk_engine_config      = risk_engine_config,
        risk_levels_config      = risk_levels_config,
    )

    # --- Inject mocks before pipeline runs ---
    if mock:
        sched._predictor    = _build_mock_predictor()
        sched._rainfall_svc = _build_mock_rainfall_service(lat, lon, location_id)

    # --- Run pipeline (force=True, dry_run=True — we persist via SQLiteRiskStore) ---
    locations = [{"latitude": lat, "longitude": lon, "location_id": location_id}]
    results   = sched.refresh_locations(locations, force=True, dry_run=True)
    state     = results[0]

    # --- Persist to SQLite ---
    store = SQLiteRiskStore(db_path=db_path)
    payload = state.get("risk_payload") or {}

    # Flatten for SQLite schema
    feat   = payload.get("rainfall_features", {})
    canon  = payload.get("canonical_risk", {})

    store_rec = {
        "location_id":               state.get("location_id"),
        "latitude":                  state.get("latitude"),
        "longitude":                 state.get("longitude"),
        "timestamp":                 state.get("last_updated")
                                     or datetime.datetime.now(
                                         datetime.timezone.utc).isoformat(),
        "observation_date":          state.get("observation_date"),
        "susceptibility_probability": payload.get("susceptibility_probability"),
        "susceptibility_class":      payload.get("susceptibility_class"),
        "rainfall_1d":               feat.get("rainfall_1d"),
        "rainfall_3d":               feat.get("rainfall_3d"),
        "rainfall_7d":               feat.get("rainfall_7d"),
        "rainfall_15d":              feat.get("rainfall_15d"),
        "rainfall_trigger_score":    payload.get("rainfall_trigger_score"),
        "rainfall_trigger_state":    payload.get("rainfall_trigger_state"),
        "dynamic_risk":              payload.get("final_risk_level"),
        "risk_level":                canon.get("machine_name"),
        "data_source":               "MOCK/SYNTHETIC" if mock else "CHIRPS/GEE",
        "stale":                     state.get("stale", False),
        "error_info":                state.get("error_reason"),
    }
    store.save_risk_result(store_rec)

    return {
        "state":    state,
        "payload":  payload,
        "feat":     feat,
        "canon":    canon,
        "db_path":  db_path,
        "mock":     mock,
        "location_id": location_id,
        "lat":      lat,
        "lon":      lon,
    }


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def format_report(result: dict) -> str:
    """Return the formatted stdout report string."""
    state   = result["state"]
    payload = result["payload"]
    feat    = result["feat"]
    canon   = result["canon"]
    mock    = result["mock"]
    db_path = result["db_path"]

    mode_banner = "*** TEST / MOCK DATA MODE ***" if mock else "[LIVE MODE]"
    mode_label  = "MOCK" if mock else "LIVE"

    sus_prob  = payload.get("susceptibility_probability")
    sus_class = payload.get("susceptibility_class", "N/A")
    trig_state= payload.get("rainfall_trigger_state", "N/A")
    trig_score= payload.get("rainfall_trigger_score", "N/A")
    reasons   = payload.get("reasons", [])
    risk_level= canon.get("level_enum") or payload.get("final_risk_level", "N/A")
    num_code  = canon.get("numeric_code", "N/A")
    hex_col   = canon.get("color_hex", "N/A")
    action    = _ACTIONS.get(str(risk_level), "Review situation and apply local protocols.")

    api_val   = feat.get("antecedent_precipitation_index")
    api_str   = f"{api_val:.4f}" if api_val is not None else "N/A"

    def _fmt(v): return f"{v:.2f}" if isinstance(v, (int, float)) and v is not None else "N/A"

    lines = [
        SEPARATOR,
        "LANDSLIDE EARLY WARNING SYSTEM — LOCATION RISK ASSESSMENT",
        SEPARATOR,
        mode_banner,
        f"[MODE: {mode_label}]",
        f"Location ID: {result['location_id']} ({result['lat']}, {result['lon']})",
        f"Timestamp: {state.get('last_updated', 'N/A')}",
        "",
        "--- STATIC SUSCEPTIBILITY ---",
        f"Probability: {_fmt(sus_prob)}",
        f"Class: {sus_class}",
        "",
        "--- DYNAMIC RAINFALL ---",
        f"Observation Date: {state.get('observation_date', 'N/A')} "
        f"(Data Age: {state.get('data_age_days', 0)} days, "
        f"Stale: {state.get('stale', False)})",
        f"Rainfall 1D:  {_fmt(feat.get('rainfall_1d'))} mm",
        f"Rainfall 3D:  {_fmt(feat.get('rainfall_3d'))} mm",
        f"Rainfall 7D:  {_fmt(feat.get('rainfall_7d'))} mm",
        f"Rainfall 15D: {_fmt(feat.get('rainfall_15d'))} mm",
        f"API (15-Day): {api_str} mm",
        f"Rainfall Trigger State: {trig_state} (Score: {trig_score})",
        "Trigger Reasons:",
    ]
    for r in reasons:
        lines.append(f"  - {r}")

    lines += [
        "",
        "--- COMPOSITE OPERATIONAL RISK ---",
        f"Dynamic Risk Level: {risk_level} "
        f"(Code: {num_code}, Hex: {hex_col})",
        f"Action: {action}",
        f"Storage: Persisted to SQLite ({db_path})",
        SEPARATOR,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_risk_engine",
        description="Landslide Early Warning System — Real-Time Risk Engine",
    )
    p.add_argument("--lat",         type=float, required=True,
                   help="Latitude (WGS84, e.g. 27.5)")
    p.add_argument("--lon",         type=float, required=True,
                   help="Longitude (WGS84, e.g. 85.5)")
    p.add_argument("--location-id", type=str,   default=None,
                   help="Human-readable location identifier")
    p.add_argument("--mock",        action="store_true",
                   help="Run 100%% offline with synthetic rainfall data")
    p.add_argument("--db-path",     type=str,
                   default="data/processed/risk_store.db",
                   help="Path to SQLite state database")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    lat         = args.lat
    lon         = args.lon
    location_id = args.location_id or f"{lat:.4f}_{lon:.4f}"
    mock        = args.mock
    db_path     = args.db_path

    try:
        result = run_assessment(
            lat         = lat,
            lon         = lon,
            location_id = location_id,
            db_path     = db_path,
            mock        = mock,
        )
        report = format_report(result)
        print(report)
        return 0

    except Exception as exc:
        logger.error("Fatal error: %s", exc, exc_info=True)
        print(f"\n[ERROR] Risk assessment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
