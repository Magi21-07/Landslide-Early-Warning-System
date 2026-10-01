import logging
import datetime
from typing import Dict, Any, List, Optional
from src.risk.risk_store import RiskStore
from src.risk.risk_scheduler import RiskScheduler
from src.risk.run_risk_engine import _build_mock_predictor, _build_mock_rainfall_service

logger = logging.getLogger(__name__)

class RiskService:
    """Service layer coordinating FastAPI inputs with the Phase 5 Risk Engine."""

    def __init__(self, store: RiskStore, scheduler: RiskScheduler):
        self.store = store
        self.scheduler = scheduler

    def get_current_risk(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the latest risk assessment for a given location."""
        return self.store.get_latest_risk(location_id)

    def get_risk_history(self, location_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieve historical risk assessments for a given location."""
        return self.store.get_risk_history(location_id, limit=limit)

    def evaluate_location_risk(self, lat: float, lon: float, location_id: Optional[str] = None, mock: bool = False) -> Dict[str, Any]:
        """
        Evaluate and store real-time risk for a location.
        Raises ValueError for invalid inputs or domain-specific failures.
        """
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude must be between -90 and 90. Got: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Longitude must be between -180 and 180. Got: {lon}")

        loc_id = location_id or f"{lat:.4f}_{lon:.4f}"

        # Setup mock behavior if requested
        if mock:
            original_predictor = self.scheduler._predictor
            original_rainfall_svc = self.scheduler._rainfall_svc
            self.scheduler._predictor = _build_mock_predictor()
            self.scheduler._rainfall_svc = _build_mock_rainfall_service(lat, lon, loc_id)

        try:
            locations = [{"latitude": lat, "longitude": lon, "location_id": loc_id}]
            # dry_run=True prevents scheduler from writing its own JSON cache,
            # allowing us to exclusively manage persistence via RiskStore.
            results = self.scheduler.refresh_locations(locations, force=True, dry_run=True)
            state = results[0]

            if state.get("stale") and state.get("error_reason"):
                # Mark as stale in the database and bubble the error up
                self.store.mark_stale(loc_id, state["error_reason"])
                raise ValueError(f"Risk evaluation failed: {state['error_reason']}")

            payload = state.get("risk_payload") or {}
            feat = payload.get("rainfall_features", {})
            canon = payload.get("canonical_risk", {})

            store_rec = {
                "location_id": state.get("location_id", loc_id),
                "latitude": state.get("latitude", lat),
                "longitude": state.get("longitude", lon),
                "timestamp": state.get("last_updated") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "observation_date": state.get("observation_date"),
                "susceptibility_probability": payload.get("susceptibility_probability"),
                "susceptibility_class": payload.get("susceptibility_class"),
                "rainfall_1d": feat.get("rainfall_1d"),
                "rainfall_3d": feat.get("rainfall_3d"),
                "rainfall_7d": feat.get("rainfall_7d"),
                "rainfall_15d": feat.get("rainfall_15d"),
                "rainfall_trigger_score": payload.get("rainfall_trigger_score"),
                "rainfall_trigger_state": payload.get("rainfall_trigger_state"),
                "dynamic_risk": payload.get("final_risk_level"),
                "risk_level": canon.get("machine_name"),
                "data_source": "MOCK/SYNTHETIC" if mock else "CHIRPS/GEE",
                "stale": False,
                "error_info": None,
            }
            
            # Persist the freshly calculated risk
            self.store.save_risk_result(store_rec)
            return store_rec

        except ValueError:
            raise
        except Exception as exc:
            logger.error("Unexpected error in evaluate_location_risk: %s", exc)
            self.store.mark_stale(loc_id, f"Engine exception: {str(exc)}")
            raise RuntimeError(f"Engine exception: {exc}") from exc
        finally:
            if mock:
                self.scheduler._predictor = original_predictor
                self.scheduler._rainfall_svc = original_rainfall_svc
