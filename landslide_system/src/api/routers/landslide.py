from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/landslide", tags=["landslide"])

@router.get("/status")
def landslide_status():
    return {
        "system": "landslide-early-warning",
        "status": "operational",
        "api": "ready"
    }
