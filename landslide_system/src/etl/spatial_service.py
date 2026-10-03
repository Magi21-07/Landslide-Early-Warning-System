"""
src/etl/spatial_service.py
---------------------------
FC-3: Static Spatial Factor Service

Provides dynamic, point-query extraction of static environmental factors:
  1. Soil properties     — SoilGrids v2 REST API (clay %, hydraulic capacity)
  2. Soil depth          — SoilGrids v2 REST API (BDRICM, cm)
  3. Lithology & weathering — No validated local dataset; returns FALLBACK/UNAVAILABLE
  4. Proximity metrics   — Overpass API (distance to nearest river & road, metres)

DESIGN PRINCIPLES:
  - NEVER infer physical properties from lat/lon ranges or city names.
  - ALL external calls have a strict 3.0 s timeout.
  - Concurrent execution via ThreadPoolExecutor (total ≤ 3 s wall time).
  - Source failures → explicit FALLBACK (not silently real).
  - MOCK/TEST modes never activate automatically in production.

ACTIVE ML MODEL: NOT AFFECTED.
  The Phase-4 model receives exactly [slope, elevation, rain3d, rain15d].
  Static factors from this module are NOT passed to predict_proba().
"""

from __future__ import annotations

import logging
import math
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.etl.spatial_models import (
    FactorProvenance,
    SourceStatus,
    StaticSpatialMetrics,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration Constants
# ---------------------------------------------------------------------------

_HTTP_TIMEOUT        = 3.0          # seconds — hard limit per external request
_PARALLEL_TIMEOUT    = 3.0          # seconds — hard wall-clock for all concurrent calls
_SOILGRIDS_BASE      = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_OVERPASS_URL        = "https://overpass-api.de/api/interpreter"
_OVERPASS_BBOX_DEG   = 0.03         # ± degrees bounding box for proximity search
_EARTH_RADIUS_M      = 6_371_000.0  # metres

# SoilGrids fallback defaults — clearly marked FALLBACK when used
_SOIL_FALLBACK = {
    "clay_percent":       25.0,
    "hydraulic_capacity": 15.0,
    "soil_depth":         None,      # depth has no safe arbitrary default
}

# Lithology fallback — used ONLY when real lookup cannot complete
_LITHOLOGY_FALLBACK = {
    "lithology_class": "Sedimentary",
    "weathering_index": 0.45,
}

# Proximity fallback — used ONLY on network failure
_PROXIMITY_FALLBACK = {
    "distance_to_river_m": None,
    "distance_to_road_m":  None,
}


# ---------------------------------------------------------------------------
# Internal Utility: Coordinate Validation
# ---------------------------------------------------------------------------

def _validate_coordinates(lat: float, lon: float) -> None:
    """Raise ValueError for coordinates outside valid WGS-84 bounds."""
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"latitude {lat} out of range [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"longitude {lon} out of range [-180, 180]")


# ---------------------------------------------------------------------------
# Internal Utility: Haversine & Line-Segment Distance
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geodesic distance in metres between two WGS-84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _point_to_segment_distance_m(
    p_lat: float, p_lon: float,
    a_lat: float, a_lon: float,
    b_lat: float, b_lon: float,
) -> float:
    """
    Minimum geodesic distance in metres from point P to line segment A→B.

    Uses a planar projection approximation centred on A:
      - 1° latitude  ≈ 111 120 m
      - 1° longitude ≈ 111 120 * cos(lat_A) m
    This gives sub-metre accuracy for segments < ~50 km.
    """
    cos_lat = math.cos(math.radians(a_lat))
    m_per_deg_lat = 111_120.0
    m_per_deg_lon = 111_120.0 * cos_lat

    # Project to local metres
    px = (p_lon - a_lon) * m_per_deg_lon
    py = (p_lat - a_lat) * m_per_deg_lat
    ax, ay = 0.0, 0.0
    bx = (b_lon - a_lon) * m_per_deg_lon
    by = (b_lat - a_lat) * m_per_deg_lat

    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:                   # degenerate segment → treat as point
        return math.hypot(px - ax, py - ay)

    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _min_distance_to_way_m(
    target_lat: float, target_lon: float,
    nodes: List[Dict[str, float]],
) -> float:
    """
    Compute minimum distance from target point to a Way's geometry (list of nodes).
    Iterates over all adjacent node pairs (line segments).
    Returns float('inf') for ways with fewer than 2 nodes.
    """
    min_d = float("inf")
    for i in range(len(nodes) - 1):
        a, b = nodes[i], nodes[i + 1]
        d = _point_to_segment_distance_m(
            target_lat, target_lon,
            a["lat"], a["lon"],
            b["lat"], b["lon"],
        )
        if d < min_d:
            min_d = d
    return min_d


# ---------------------------------------------------------------------------
# Internal Utility: HTTP Client Factory
# ---------------------------------------------------------------------------

def _make_client() -> httpx.Client:
    """Return a configured httpx.Client with sensible defaults."""
    return httpx.Client(
        timeout=httpx.Timeout(_HTTP_TIMEOUT),
        follow_redirects=True,
        headers={"User-Agent": "LandslideEWS-FC3/1.0"},
    )


# ---------------------------------------------------------------------------
# Internal Utility: SoilGrids Value Extraction
# ---------------------------------------------------------------------------

def _extract_soilgrids_value(
    data: Dict[str, Any],
    prop_name: str,
    depth_label: str = "0-5cm",
) -> Optional[float]:
    """
    Navigate SoilGrids v2 JSON response to extract `mean` for a property+depth.
    Returns None if the value is absent or non-numeric.
    """
    try:
        layers = data.get("properties", {}).get("layers", [])
        for layer in layers:
            if layer.get("name") == prop_name:
                for depth in layer.get("depths", []):
                    if depth.get("label") == depth_label:
                        val = depth.get("values", {}).get("mean")
                        if val is not None:
                            return float(val)
        return None
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# STEP 2: Soil Properties (SoilGrids v2)
# ---------------------------------------------------------------------------

def get_soil_properties(lat: float, lon: float) -> Tuple[Dict[str, Any], FactorProvenance]:
    """
    Query SoilGrids v2 REST API for:
      - clay    : clay content, 0–5 cm, mean — native unit: decig/kg → divide by 10 → %
      - wv0033  : volumetric water content at 33 kPa (field capacity proxy)
                  native unit: cm³/dm³ → divide by 10 → % vol
      - bdricm  : absolute depth to bedrock, cm (mean)

    Returns (result_dict, provenance).
    On any failure returns FALLBACK values clearly marked.
    """
    _validate_coordinates(lat, lon)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    params = [
        ("lon", lon),
        ("lat", lat),
        ("property", "clay"),
        ("property", "wv0033"),
        ("property", "bdricm"),
        ("depth", "0-5cm"),
        ("value", "mean"),
    ]

    try:
        with _make_client() as client:
            resp = client.get(_SOILGRIDS_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()

        clay_raw   = _extract_soilgrids_value(data, "clay",    "0-5cm")
        wv0033_raw = _extract_soilgrids_value(data, "wv0033",  "0-5cm")
        bdricm_raw = _extract_soilgrids_value(data, "bdricm",  "0-5cm")

        # Unit conversion
        clay_pct  = round(clay_raw   / 10.0, 2) if clay_raw   is not None else None
        hyd_cap   = round(wv0033_raw / 10.0, 2) if wv0033_raw is not None else None
        soil_depth= round(bdricm_raw,        1) if bdricm_raw is not None else None

        # Range validation
        if clay_pct is not None and not (0.0 <= clay_pct <= 100.0):
            logger.warning("clay_percent %s out of range [0,100]; discarding.", clay_pct)
            clay_pct = None
        if hyd_cap is not None and not (0.0 <= hyd_cap <= 100.0):
            logger.warning("hydraulic_capacity %s out of range [0,100]; discarding.", hyd_cap)
            hyd_cap = None

        any_real = any(v is not None for v in [clay_pct, hyd_cap, soil_depth])
        status   = SourceStatus.REAL if any_real else SourceStatus.FALLBACK

        result = {
            "clay_percent":       clay_pct   if clay_pct   is not None else _SOIL_FALLBACK["clay_percent"],
            "hydraulic_capacity": hyd_cap    if hyd_cap    is not None else _SOIL_FALLBACK["hydraulic_capacity"],
            "soil_depth":         soil_depth,                 # None if not retrieved — no arbitrary default
            "_real_clay":         clay_pct   is not None,
            "_real_hyd":          hyd_cap    is not None,
            "_real_depth":        soil_depth is not None,
        }
        fallback_used = not (clay_pct is not None and hyd_cap is not None)

        prov = FactorProvenance(
            source="SoilGrids_v2",
            status=status,
            fallback_used=fallback_used,
            lookup_method="REST_API",
            retrieved_at=ts,
            notes="clay=decig/kg÷10→%; wv0033=cm³/dm³÷10→%vol; bdricm=cm",
        )
        logger.info(
            "SoilGrids result for (%.4f, %.4f): clay=%.2f%% hyd=%.2f depth=%s status=%s",
            lat, lon,
            result["clay_percent"], result["hydraulic_capacity"],
            result["soil_depth"], status,
        )
        return result, prov

    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        logger.warning("SoilGrids timeout/connect error for (%.4f,%.4f): %s", lat, lon, exc)
    except httpx.HTTPStatusError as exc:
        logger.warning("SoilGrids HTTP %s for (%.4f,%.4f): %s", exc.response.status_code, lat, lon, exc)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("SoilGrids parse error for (%.4f,%.4f): %s", lat, lon, exc)
    except Exception as exc:
        logger.warning("SoilGrids unexpected error for (%.4f,%.4f): %s", lat, lon, exc)

    # ---------- FALLBACK ----------
    prov = FactorProvenance(
        source="SoilGrids_v2",
        status=SourceStatus.FALLBACK,
        fallback_used=True,
        lookup_method="REST_API",
        retrieved_at=ts,
        notes="Source unavailable; using configured fallback defaults.",
    )
    result = {**_SOIL_FALLBACK}
    return result, prov


# ---------------------------------------------------------------------------
# STEP 4: Lithology & Weathering
# ---------------------------------------------------------------------------

def get_lithology_and_weathering(lat: float, lon: float) -> Tuple[Dict[str, Any], FactorProvenance]:
    """
    Lithology: No validated GLiM raster or local vector dataset exists in
               this repository. Returns FALLBACK with explicit provenance.

    Weathering: No direct or proxy weathering dataset exists in this
                repository. Returns None / UNAVAILABLE.

    NOTE: These factors MUST NOT be sourced from lat/lon heuristics.
    Future retraining should integrate GLiM v1 or regional lithology raster.
    """
    _validate_coordinates(lat, lon)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Lithology — FALLBACK (no raster available)
    result = {
        "lithology_class":  _LITHOLOGY_FALLBACK["lithology_class"],
        "lithology_source": "NONE",
        "weathering_index": None,           # UNAVAILABLE — no proxy dataset
        "weathering_source": "NONE",
    }

    prov = FactorProvenance(
        source="GLiM_v1",
        status=SourceStatus.FALLBACK,
        fallback_used=True,
        lookup_method="NONE",
        retrieved_at=ts,
        notes=(
            "No GLiM raster or regional lithology dataset found in repository. "
            "Lithology='Sedimentary' is a configured fallback, NOT a spatial lookup. "
            "Weathering=None (UNAVAILABLE). "
            "Action required: ingest GLiM v1 GeoPackage for REAL mode."
        ),
    )
    logger.info(
        "Lithology/weathering for (%.4f,%.4f): FALLBACK (no local dataset). "
        "weathering=UNAVAILABLE.",
        lat, lon,
    )
    return result, prov


# ---------------------------------------------------------------------------
# STEP 5: Proximity Metrics (Overpass API)
# ---------------------------------------------------------------------------

def get_proximity_metrics(lat: float, lon: float) -> Tuple[Dict[str, Any], FactorProvenance]:
    """
    Query Overpass API for nearest river and road within ±0.03° bounding box.

    Distance calculation:
      - Uses per-segment Haversine/planar approximation (NOT degree Euclidean).
      - Iterates all geometry nodes of each returned Way.
      - Returns minimum perpendicular segment distance in METRES.

    Fallback: on any failure, returns _PROXIMITY_FALLBACK with status=FALLBACK.
    On NO_FEATURE_FOUND: returns bbox-threshold estimate with status=REAL + note.
    """
    _validate_coordinates(lat, lon)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    d = _OVERPASS_BBOX_DEG
    bbox = f"{lat - d},{lon - d},{lat + d},{lon + d}"

    query = (
        f"[out:json][timeout:3];"
        f"("
        f'way["waterway"~"river|stream"]({bbox});'
        f'way["highway"]({bbox});'
        f");out geom;"
    )

    try:
        with _make_client() as client:
            resp = client.post(_OVERPASS_URL, content=query,
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
            resp.raise_for_status()
            osm_data = resp.json()

        elements = osm_data.get("elements", [])

        river_distances: List[float] = []
        road_distances:  List[float] = []

        for elem in elements:
            if elem.get("type") != "way":
                continue
            nodes = elem.get("geometry", [])
            if len(nodes) < 2:
                # Fewer than 2 nodes → cannot form a segment; use single-node distance
                if nodes:
                    d_pt = _haversine_m(lat, lon, nodes[0]["lat"], nodes[0]["lon"])
                    nodes_dist = d_pt
                else:
                    continue
            else:
                nodes_dist = _min_distance_to_way_m(lat, lon, nodes)

            tags = elem.get("tags", {})
            is_waterway = "waterway" in tags
            is_highway  = "highway"  in tags

            if is_waterway:
                river_distances.append(nodes_dist)
            if is_highway:
                road_distances.append(nodes_dist)

        # Determine result per feature class
        if river_distances:
            dist_river = round(min(river_distances), 1)
            river_status = SourceStatus.REAL
            river_note   = f"Found {len(river_distances)} waterway ways in ±{d}° bbox."
        else:
            # No feature in bbox — return threshold distance as indicator, mark clearly
            dist_river = round(_OVERPASS_BBOX_DEG * 111_000, 1)  # ~3 330 m
            river_status = SourceStatus.REAL
            river_note   = f"NO_FEATURE_FOUND in ±{d}° bbox; reporting bbox-threshold distance."

        if road_distances:
            dist_road  = round(min(road_distances), 1)
            road_status = SourceStatus.REAL
            road_note   = f"Found {len(road_distances)} highway ways in ±{d}° bbox."
        else:
            dist_road  = round(_OVERPASS_BBOX_DEG * 111_000, 1)
            road_status = SourceStatus.REAL
            road_note   = f"NO_FEATURE_FOUND in ±{d}° bbox; reporting bbox-threshold distance."

        # Range guard
        dist_river = max(0.0, dist_river)
        dist_road  = max(0.0, dist_road)

        overall_status = SourceStatus.REAL
        result = {
            "distance_to_river_m": dist_river,
            "distance_to_road_m":  dist_road,
            "_river_note": river_note,
            "_road_note":  road_note,
        }
        prov = FactorProvenance(
            source="Overpass_OSM",
            status=overall_status,
            fallback_used=False,
            lookup_method="REST_API",
            retrieved_at=ts,
            notes=f"bbox={bbox}; river={river_note}; road={road_note}",
        )
        logger.info(
            "Proximity for (%.4f,%.4f): river=%.1fm road=%.1fm",
            lat, lon, dist_river, dist_road,
        )
        return result, prov

    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        logger.warning("Overpass timeout/connect for (%.4f,%.4f): %s", lat, lon, exc)
    except httpx.HTTPStatusError as exc:
        logger.warning("Overpass HTTP %s for (%.4f,%.4f): %s", exc.response.status_code, lat, lon, exc)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Overpass parse error for (%.4f,%.4f): %s", lat, lon, exc)
    except Exception as exc:
        logger.warning("Overpass unexpected error for (%.4f,%.4f): %s", lat, lon, exc)

    # ---------- FALLBACK ----------
    prov = FactorProvenance(
        source="Overpass_OSM",
        status=SourceStatus.FALLBACK,
        fallback_used=True,
        lookup_method="REST_API",
        retrieved_at=ts,
        notes="Source unavailable; using configured fallback defaults.",
    )
    result = {**_PROXIMITY_FALLBACK}
    return result, prov


# ---------------------------------------------------------------------------
# STEP 6: Orchestrator — get_static_spatial_metrics
# ---------------------------------------------------------------------------

def get_static_spatial_metrics(lat: float, lon: float) -> Dict[str, Any]:
    """
    Orchestrate all static factor queries concurrently.

    Concurrent execution via ThreadPoolExecutor with a hard 3-second wall-clock limit.
    Any factor that fails within that budget uses its explicit FALLBACK.

    Returns the API-ready dict for 'spatial_metrics' key in /risk/evaluate response.

    CRITICAL: This function does NOT modify the ML model input vector.
              It is purely additive to the API response.
    """
    _validate_coordinates(lat, lon)

    soil_result    = _SOIL_FALLBACK.copy()
    soil_prov      = FactorProvenance(
        source="SoilGrids_v2", status=SourceStatus.FALLBACK, fallback_used=True,
        lookup_method="REST_API", notes="Concurrent execution did not complete in time."
    )
    litho_result   = {"lithology_class": _LITHOLOGY_FALLBACK["lithology_class"],
                      "weathering_index": None}
    litho_prov     = FactorProvenance(
        source="GLiM_v1", status=SourceStatus.FALLBACK, fallback_used=True,
        lookup_method="NONE", notes="No local dataset."
    )
    prox_result    = _PROXIMITY_FALLBACK.copy()
    prox_prov      = FactorProvenance(
        source="Overpass_OSM", status=SourceStatus.FALLBACK, fallback_used=True,
        lookup_method="REST_API", notes="Concurrent execution did not complete in time."
    )

    t_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_soil  = executor.submit(get_soil_properties,           lat, lon)
        fut_litho = executor.submit(get_lithology_and_weathering,  lat, lon)
        fut_prox  = executor.submit(get_proximity_metrics,         lat, lon)

        remaining = _PARALLEL_TIMEOUT - (time.monotonic() - t_start)

        try:
            soil_result, soil_prov = fut_soil.result(timeout=max(0.1, remaining))
        except (FuturesTimeout, Exception) as exc:
            logger.warning("Soil future error: %s — using FALLBACK.", exc)

        remaining = _PARALLEL_TIMEOUT - (time.monotonic() - t_start)
        try:
            litho_result, litho_prov = fut_litho.result(timeout=max(0.1, remaining))
        except (FuturesTimeout, Exception) as exc:
            logger.warning("Lithology future error: %s — using FALLBACK.", exc)

        remaining = _PARALLEL_TIMEOUT - (time.monotonic() - t_start)
        try:
            prox_result, prox_prov = fut_prox.result(timeout=max(0.1, remaining))
        except (FuturesTimeout, Exception) as exc:
            logger.warning("Proximity future error: %s — using FALLBACK.", exc)

    # Assemble canonical StaticSpatialMetrics
    metrics = StaticSpatialMetrics(
        clay_percent        = soil_result.get("clay_percent"),
        hydraulic_capacity  = soil_result.get("hydraulic_capacity"),
        soil_depth          = soil_result.get("soil_depth"),
        lithology_class     = litho_result.get("lithology_class"),
        weathering_index    = litho_result.get("weathering_index"),   # None = UNAVAILABLE
        distance_to_river_m = prox_result.get("distance_to_river_m"),
        distance_to_road_m  = prox_result.get("distance_to_road_m"),
        latitude            = lat,
        longitude           = lon,
    )
    metrics.set_provenance("soil",      soil_prov)
    metrics.set_provenance("lithology", litho_prov)
    metrics.set_provenance("proximity", prox_prov)
    metrics.data_quality = metrics.overall_quality()

    elapsed = time.monotonic() - t_start
    logger.info(
        "get_static_spatial_metrics (%.4f, %.4f) completed in %.2fs — quality=%s",
        lat, lon, elapsed, metrics.data_quality,
    )
    return metrics.to_api_dict()
