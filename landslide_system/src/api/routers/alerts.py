from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List
from src.alerts.alert_history import AlertHistoryRecord, AlertHistoryService

router = APIRouter()

# A global instance for simplicity; in a real app, this might be injected via DI
alert_history_service = AlertHistoryService()

@router.get(
    "/history/{target_id}",
    response_model=List[AlertHistoryRecord],
    summary="Get Alert History for Target",
    description="Returns an append-only historical record of alerts and their delivery statuses."
)
def get_target_history(
    target_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0)
):
    """
    Retrieve alert history for a given target ID.
    """
    return alert_history_service.get_target_history(target_id=target_id, limit=limit, offset=offset)
