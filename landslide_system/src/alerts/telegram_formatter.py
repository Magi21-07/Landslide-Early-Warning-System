# src/alerts/telegram_formatter.py
"""
Phase 8.3 Part 2 — Telegram Message Formatter (Updated for Phase 8.6)
=====================================================================

Produces executive, high-visibility Markdown alert messages from an
``AlertEvent`` payload. The formatter delegates to ``TelegramMessageBuilder``
(Phase 8.6) to construct structured, compliant message templates.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.alerts.telegram_message import TelegramMessageBuilder

logger = logging.getLogger(__name__)

def format_alert_message(
    *,
    target_id:          str,
    current_risk_level: str,
    event_type:         str,
    probability:        float,
    triggered_at:       str,
    previous_risk_level: Optional[str]     = None,
    shap_drivers:       Optional[List[Dict[str, Any]]] = None,
    ndvi:               Optional[float]    = None,
    sar_soil_moisture:  Optional[float]    = None,
    rainfall_3day_mm:   Optional[float]    = None,
    model_version:      str                = "",
    data_quality:       str                = "VALID",
    stale:              bool               = False,
) -> str:
    """
    Build the full Telegram Markdown alert message string.
    Delegates to TelegramMessageBuilder.
    """
    return TelegramMessageBuilder.build_message(
        target_id=target_id,
        current_risk_level=current_risk_level,
        event_type=event_type,
        probability=probability,
        triggered_at=triggered_at,
        previous_risk_level=previous_risk_level,
        data_quality=data_quality,
        stale=stale,
        model_version=model_version,
        shap_drivers=shap_drivers,
        ndvi=ndvi,
        sar_soil_moisture=sar_soil_moisture,
        rainfall_3day_mm=rainfall_3day_mm,
    )

def format_event(
    event: Any,
    *,
    shap_drivers:      Optional[List[Dict[str, Any]]] = None,
    ndvi:              Optional[float] = None,
    sar_soil_moisture: Optional[float] = None,
    rainfall_3day_mm:  Optional[float] = None,
) -> str:
    """
    Build a Telegram message directly from an ``AlertEvent`` Pydantic model.
    """
    return format_alert_message(
        target_id           = event.target_id,
        current_risk_level  = event.current_risk_level,
        event_type          = event.event_type,
        probability         = event.probability,
        triggered_at        = event.triggered_at,
        previous_risk_level = event.previous_risk_level,
        model_version       = getattr(event, "model_version", ""),
        data_quality        = getattr(event, "data_quality", "VALID"),
        stale               = getattr(event, "stale", False),
        shap_drivers        = shap_drivers,
        ndvi                = ndvi,
        sar_soil_moisture   = sar_soil_moisture,
        rainfall_3day_mm    = rainfall_3day_mm,
    )
