from fastapi import APIRouter, Depends, status, HTTPException
from src.api.dependencies import get_risk_store
from src.risk.risk_store import RiskStore

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "landslide-api",
        "version": "1.0.0"
    }

@router.get("/health/ready")
def readiness_probe(store: RiskStore = Depends(get_risk_store)):
    try:
        # Fast check: just verify database connection by running a minimal query or check if table exists
        # In SQLiteRiskStore, we can just access store._conn
        if hasattr(store, '_conn'):
            cursor = store._conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Risk store is unavailable."
        )
