import os
from functools import lru_cache

from src.risk.risk_store import SQLiteRiskStore, RiskStore
from src.risk.risk_scheduler import RiskScheduler
from src.risk.rainfall_service import RainfallService
from src.api.services.risk_service import RiskService
from src.api.services.geospatial_service import GeospatialService

@lru_cache()
def get_risk_store() -> RiskStore:
    """Provide a singleton instance of the RiskStore."""
    db_path = os.getenv("DB_PATH", "data/processed/risk_store.db")
    return SQLiteRiskStore(db_path=db_path)

@lru_cache()
def get_scheduler() -> RiskScheduler:
    """Provide a singleton instance of the RiskScheduler (and nested ML/GEE clients)."""
    gee_config = os.getenv("EE_PROJECT_ID", "")
    return RiskScheduler(gee_config=gee_config)

@lru_cache()
def get_risk_service() -> RiskService:
    """Provide a singleton instance of the RiskService."""
    store = get_risk_store()
    scheduler = get_scheduler()
    return RiskService(store=store, scheduler=scheduler)

@lru_cache()
def get_rainfall_service() -> RainfallService:
    """Provide a singleton instance of the RainfallService."""
    scheduler = get_scheduler()
    return scheduler._get_rainfall_service()

@lru_cache()
def get_geospatial_service() -> GeospatialService:
    """Provide a singleton instance of the GeospatialService."""
    store = get_risk_store()
    return GeospatialService(store=store)

