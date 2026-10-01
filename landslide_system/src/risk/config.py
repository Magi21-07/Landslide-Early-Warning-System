# src/risk/config.py
"""
Configurable defaults for the Phase 5 Risk Engine.
All values are module-level constants; override by passing explicit arguments
to the relevant classes rather than mutating these globals.
"""

# ---------------------------------------------------------------------------
# CHIRPS Rainfall Collections
# ---------------------------------------------------------------------------

# Primary: CHIRPS v3 satellite-only daily product (~5.5 km resolution)
PRIMARY_CHIRPS_COLLECTION: str = "UCSB-CHC/CHIRPS/V3/DAILY_SAT"

# Fallback: CHIRPS v2 blended (gauge + satellite) daily product (~5.5 km)
FALLBACK_CHIRPS_COLLECTION: str = "UCSB-CHC/CHIRPS/DAILY"

# Band name and units are identical across both collections
CHIRPS_BAND: str = "precipitation"
CHIRPS_UNITS: str = "mm/day"

# ---------------------------------------------------------------------------
# Temporal defaults
# ---------------------------------------------------------------------------

# Number of days to look back from the target date when no date range is given
DEFAULT_LOOKBACK_DAYS: int = 14

# ---------------------------------------------------------------------------
# Geographic validation bounds
# ---------------------------------------------------------------------------

LATITUDE_RANGE:  tuple = (-90.0,  90.0)
LONGITUDE_RANGE: tuple = (-180.0, 180.0)
