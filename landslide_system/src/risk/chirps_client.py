"""
src/risk/chirps_client.py
--------------------------
Phase 5.2: CHIRPS Rainfall Data Connector.

Queries CHIRPS daily precipitation data from Google Earth Engine for a given
point and date range. Reuses GEE initialisation from src/etl/gee_extractor.py.
"""

import datetime
import logging
from typing import Union

import numpy as np
import pandas as pd

from src.risk.config import (
    PRIMARY_CHIRPS_COLLECTION,
    FALLBACK_CHIRPS_COLLECTION,
    CHIRPS_BAND,
    CHIRPS_UNITS,
    DEFAULT_LOOKBACK_DAYS,
    LATITUDE_RANGE,
    LONGITUDE_RANGE,
)

# Module-level import so unittest.mock.patch can intercept it
from src.etl.gee_extractor import initialize_gee

logger = logging.getLogger(__name__)

# Type alias for flexible date input
DateInput = Union[str, datetime.date]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_date(value: DateInput, name: str) -> datetime.date:
    """Coerce str (YYYY-MM-DD) or datetime.date to datetime.date."""
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(
            f"'{name}' must be a date object or ISO string (YYYY-MM-DD). Got: {value!r}"
        ) from exc


def _validate_coordinates(lat: float, lon: float) -> None:
    if not (LATITUDE_RANGE[0] <= lat <= LATITUDE_RANGE[1]):
        raise ValueError(
            f"Latitude {lat} is out of valid range {LATITUDE_RANGE}."
        )
    if not (LONGITUDE_RANGE[0] <= lon <= LONGITUDE_RANGE[1]):
        raise ValueError(
            f"Longitude {lon} is out of valid range {LONGITUDE_RANGE}."
        )


def _validate_date_order(start: datetime.date, end: datetime.date) -> None:
    if start > end:
        raise ValueError(
            f"start_date ({start}) must be <= end_date ({end})."
        )


# ---------------------------------------------------------------------------
# ChirpsClient
# ---------------------------------------------------------------------------

class ChirpsClient:
    """
    Fetches CHIRPS daily precipitation data for a point via Google Earth Engine.

    Parameters
    ----------
    gee_config : str
        Passed to initialize_gee() — either a GEE project ID or path to a
        service-account JSON key file.
    collection_id : str, optional
        CHIRPS collection to query. Defaults to PRIMARY_CHIRPS_COLLECTION.
        Falls back to FALLBACK_CHIRPS_COLLECTION on EEException.
    """

    def __init__(
        self,
        gee_config: str,
        collection_id: str = None,
    ):
        # Reuse existing GEE initialisation — no duplicate ee.Initialize()
        success = initialize_gee(gee_config)
        if not success:
            raise RuntimeError(
                "GEE initialisation failed. Check your credentials / project ID."
            )

        self._primary_collection   = collection_id or PRIMARY_CHIRPS_COLLECTION
        self._fallback_collection  = FALLBACK_CHIRPS_COLLECTION
        self._active_collection    = self._primary_collection

        logger.info(
            "ChirpsClient ready. Primary collection: %s", self._primary_collection
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def fetch(
        self,
        lat: float,
        lon: float,
        start_date: DateInput = None,
        end_date:   DateInput = None,
    ) -> dict:
        """
        Fetch daily CHIRPS precipitation for a point and date range.

        Parameters
        ----------
        lat, lon        : WGS84 coordinates.
        start_date      : First day of window (inclusive). ISO string or date.
                          Defaults to (today - DEFAULT_LOOKBACK_DAYS).
        end_date        : Last day of window (inclusive). ISO string or date.
                          Defaults to today.

        Returns
        -------
        dict with keys:
          "data"     -> pd.DataFrame  columns=['date', 'precipitation_mm']
          "metadata" -> dict          provenance info
        """
        # --- Resolve defaults ---
        today = datetime.date.today()
        if end_date is None:
            end_date = today
        if start_date is None:
            start_date = today - datetime.timedelta(days=DEFAULT_LOOKBACK_DAYS)

        # --- Validate ---
        start_date = _to_date(start_date, 'start_date')
        end_date   = _to_date(end_date,   'end_date')
        _validate_coordinates(lat, lon)
        _validate_date_order(start_date, end_date)

        logger.info(
            "Fetching CHIRPS for (%.4f, %.4f) from %s to %s",
            lat, lon, start_date, end_date
        )

        # --- Query GEE with fallback ---
        df = self._query_gee(lat, lon, start_date, end_date)

        # --- Build output ---
        retrieved_at = (
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        )

        payload = {
            "data": df,
            "metadata": {
                "data_source":    "CHIRPS",
                "collection_id":  self._active_collection,
                "retrieved_at":   retrieved_at,
                "date_range":     {
                    "start": start_date.isoformat(),
                    "end":   end_date.isoformat()
                },
                "coordinate":     {"latitude": lat, "longitude": lon},
                "units":          CHIRPS_UNITS,
            }
        }
        return payload

    # ------------------------------------------------------------------ #
    # Internal GEE query                                                   #
    # ------------------------------------------------------------------ #

    def _query_gee(
        self,
        lat: float,
        lon: float,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> pd.DataFrame:
        """Query GEE CHIRPS collection; tries primary then fallback."""
        try:
            return self._extract_from_collection(
                self._primary_collection, lat, lon, start_date, end_date
            )
        except Exception as primary_exc:
            logger.warning(
                "Primary CHIRPS collection failed (%s): %s. "
                "Attempting fallback: %s",
                self._primary_collection, primary_exc,
                self._fallback_collection
            )
            try:
                df = self._extract_from_collection(
                    self._fallback_collection, lat, lon, start_date, end_date
                )
                self._active_collection = self._fallback_collection
                return df
            except Exception as fallback_exc:
                logger.error(
                    "Fallback CHIRPS collection also failed: %s", fallback_exc
                )
                raise RuntimeError(
                    f"Both CHIRPS collections failed. "
                    f"Primary: {primary_exc}. Fallback: {fallback_exc}."
                ) from fallback_exc

    def _extract_from_collection(
        self,
        collection_id: str,
        lat: float,
        lon: float,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> pd.DataFrame:
        """
        Perform the actual GEE extraction and return a tidy DataFrame.
        Missing days are represented as np.nan (NOT silently zeroed).
        """
        import ee

        point = ee.Geometry.Point([lon, lat])

        # GEE end date is exclusive — add 1 day to include end_date
        gee_end = (end_date + datetime.timedelta(days=1)).isoformat()

        collection = (
            ee.ImageCollection(collection_id)
            .filterBounds(point)
            .filterDate(start_date.isoformat(), gee_end)
            .select(CHIRPS_BAND)
        )

        size = collection.size().getInfo()
        if size == 0:
            logger.warning(
                "CHIRPS collection '%s' returned 0 images for "
                "(%.4f, %.4f) between %s and %s.",
                collection_id, lat, lon, start_date, end_date
            )
            # Return empty DataFrame — do NOT fill with zeros
            return pd.DataFrame(columns=['date', 'precipitation_mm'])

        logger.info(
            "Extracting %d CHIRPS images from '%s'...", size, collection_id
        )

        # Extract each image's date and precipitation value
        def _extract_feature(image):
            value = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=5500,       # CHIRPS native ~5.5 km
                maxPixels=1
            ).get(CHIRPS_BAND)
            return ee.Feature(
                None,
                {
                    'date':             image.date().format('YYYY-MM-dd'),
                    'precipitation_mm': value
                }
            )

        features_list = collection.map(_extract_feature).getInfo()['features']

        records = []
        missing_count = 0
        for feat in features_list:
            props = feat.get('properties', {})
            date_str   = props.get('date')
            precip_val = props.get('precipitation_mm')

            if precip_val is None:
                missing_count += 1
                logger.warning(
                    "Missing precipitation value for date %s at (%.4f, %.4f). "
                    "Storing as NaN.",
                    date_str, lat, lon
                )
                precip_val = np.nan

            records.append({
                'date':             date_str,
                'precipitation_mm': float(precip_val) if not np.isnan(precip_val) else np.nan
            })

        if missing_count > 0:
            logger.warning(
                "Data quality warning: %d/%d days have missing precipitation "
                "values for (%.4f, %.4f).",
                missing_count, len(records), lat, lon
            )

        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        logger.info(
            "CHIRPS extraction complete. %d rows returned (%d NaN).",
            len(df), df['precipitation_mm'].isna().sum()
        )
        return df
