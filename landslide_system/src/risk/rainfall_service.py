"""
src/risk/rainfall_service.py
-----------------------------
Phase 5.3: Rainfall Extraction and Normalisation Service.

Wraps ChirpsClient (Phase 5.2) in a clean service layer that exposes
domain-level interfaces for single-point and multi-location rainfall fetch,
with strict input validation, missing-data preservation, and structured
DailyRainfallRecord output.
"""

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported recent-rainfall windows (days)
# ---------------------------------------------------------------------------

SUPPORTED_WINDOWS = {1, 3, 7, 15}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class RainfallFetchError(Exception):
    """Raised when GEE / CHIRPS extraction fails after logging."""


# ---------------------------------------------------------------------------
# Data schemas (dataclasses)
# ---------------------------------------------------------------------------

@dataclass
class LocationInput:
    """Validated geographic point for rainfall extraction."""
    latitude:    float
    longitude:   float
    location_id: Optional[str] = None

    def __post_init__(self):
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(
                f"latitude must be in [-90, 90]. Got: {self.latitude}"
            )
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(
                f"longitude must be in [-180, 180]. Got: {self.longitude}"
            )


@dataclass
class DailyRainfallRecord:
    """One day of rainfall data for a single geographic point."""
    location_id:  Optional[str]
    latitude:     float
    longitude:    float
    date:         str             # YYYY-MM-DD
    rainfall_mm:  Optional[float] # None = missing; 0.0 = genuine dry day
    source:       str
    retrieved_at: str             # ISO UTC timestamp


# ---------------------------------------------------------------------------
# RainfallService
# ---------------------------------------------------------------------------

class RainfallService:
    """
    Domain-level service for fetching CHIRPS daily rainfall.

    Parameters
    ----------
    gee_config : str
        GEE project ID or path to service-account JSON key (passed to ChirpsClient).
    """

    def __init__(self, gee_config: str):
        from src.risk.chirps_client import ChirpsClient as _ChirpsClient
        self._client = _ChirpsClient(gee_config=gee_config)
        logger.info("RainfallService initialised with ChirpsClient.")

    # ------------------------------------------------------------------ #
    # Primary interface                                                    #
    # ------------------------------------------------------------------ #

    def get_daily_rainfall(
        self,
        latitude:   float,
        longitude:  float,
        start_date: Union[str, datetime.date],
        end_date:   Union[str, datetime.date],
        location_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily rainfall records for a single point and date window.

        Returns a list of DailyRainfallRecord-compatible dicts (one per day).
        Missing days are preserved as None, NOT coerced to 0.0.
        """
        logger.info(
            "get_daily_rainfall -> (%.4f, %.4f) from %s to %s",
            latitude, longitude, start_date, end_date
        )

        try:
            payload = self._client.fetch(
                lat=latitude,
                lon=longitude,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            # Check for EEException by name (avoids importing ee in service layer)
            exc_type = type(exc).__name__
            if 'EEException' in exc_type or isinstance(exc, RuntimeError):
                logger.error(
                    "GEE/CHIRPS extraction failed for (%.4f, %.4f): %s",
                    latitude, longitude, exc
                )
                raise RainfallFetchError(
                    f"Rainfall extraction failed for ({latitude}, {longitude}): {exc}"
                ) from exc
            raise

        df          = payload['data']
        meta        = payload['metadata']
        retrieved_at = meta['retrieved_at']
        source       = meta['collection_id']

        records = []
        missing_count = 0

        for _, row in df.iterrows():
            raw_val = row['precipitation_mm']

            # Preserve NaN / None / NaT as Python None (pd.isna handles all cases)
            if raw_val is None or pd.isna(raw_val):
                rainfall_mm = None
                missing_count += 1
            else:
                # Raw preservation — no rounding, scaling, or transformation
                rainfall_mm = float(raw_val)

            date_str = (
                row['date'].strftime('%Y-%m-%d')
                if hasattr(row['date'], 'strftime')
                else str(row['date'])
            )

            records.append(DailyRainfallRecord(
                location_id  = location_id,
                latitude     = latitude,
                longitude    = longitude,
                date         = date_str,
                rainfall_mm  = rainfall_mm,
                source       = source,
                retrieved_at = retrieved_at,
            ).__dict__)

        if missing_count:
            logger.warning(
                "Missing data: %d/%d days have no precipitation value "
                "for (%.4f, %.4f).",
                missing_count, len(records), latitude, longitude
            )

        logger.info(
            "get_daily_rainfall complete: %d records returned "
            "(%d missing) for (%.4f, %.4f).",
            len(records), missing_count, latitude, longitude
        )
        return records

    def get_recent_rainfall(
        self,
        latitude:    float,
        longitude:   float,
        days:        int = 7,
        location_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convenience wrapper: fetch the last `days` days of rainfall up to today.

        Parameters
        ----------
        days : int
            Must be one of {1, 3, 7, 15}. Raises ValueError otherwise.
        """
        if days not in SUPPORTED_WINDOWS:
            raise ValueError(
                f"Unsupported window: {days} days. "
                f"Supported values are: {sorted(SUPPORTED_WINDOWS)}"
            )

        today      = datetime.date.today()
        start_date = today - datetime.timedelta(days=days - 1)

        logger.info(
            "get_recent_rainfall -> (%.4f, %.4f) last %d days (%s to %s)",
            latitude, longitude, days, start_date, today
        )

        return self.get_daily_rainfall(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=today,
            location_id=location_id,
        )

    def get_rainfall_for_locations(
        self,
        locations: List[Dict[str, Any]],
        days:      int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Batch rainfall fetch across multiple locations.

        Parameters
        ----------
        locations : list of dicts with keys 'latitude', 'longitude',
                    and optionally 'location_id'.
        days : int
            Lookback window. Must be one of {1, 3, 7, 15}.

        Returns
        -------
        Flat list of all DailyRainfallRecord dicts across all locations.
        Input location dicts are never mutated.
        """
        if days not in SUPPORTED_WINDOWS:
            raise ValueError(
                f"Unsupported window: {days} days. "
                f"Supported values are: {sorted(SUPPORTED_WINDOWS)}"
            )

        all_records: List[Dict[str, Any]] = []

        for loc in locations:
            # Build a LocationInput for validation — does not mutate original dict
            loc_input = LocationInput(
                latitude    = float(loc['latitude']),
                longitude   = float(loc['longitude']),
                location_id = loc.get('location_id'),
            )

            logger.info(
                "Fetching rainfall for location '%s' (%.4f, %.4f)...",
                loc_input.location_id or 'unnamed',
                loc_input.latitude,
                loc_input.longitude,
            )

            try:
                records = self.get_recent_rainfall(
                    latitude    = loc_input.latitude,
                    longitude   = loc_input.longitude,
                    days        = days,
                    location_id = loc_input.location_id,
                )
                all_records.extend(records)
            except RainfallFetchError as exc:
                logger.error(
                    "Skipping location '%s': %s",
                    loc_input.location_id or 'unnamed', exc
                )
                # Continue processing remaining locations

        logger.info(
            "get_rainfall_for_locations complete: %d total records "
            "across %d locations.",
            len(all_records), len(locations)
        )
        return all_records
