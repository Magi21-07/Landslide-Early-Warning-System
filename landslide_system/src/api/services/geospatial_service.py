import logging
from typing import Optional, List, Dict, Any
from src.risk.risk_store import RiskStore, SQLiteRiskStore
from src.api.schemas.geospatial import GeoJSONFeatureCollection, GeoJSONFeature, PointGeometry

logger = logging.getLogger(__name__)

class GeospatialService:
    def __init__(self, store: RiskStore):
        self.store = store
        
    def get_risk_map(
        self,
        min_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lat: Optional[float] = None,
        max_lon: Optional[float] = None,
        risk_level: Optional[str] = None,
        limit: int = 100
    ) -> GeoJSONFeatureCollection:
        records = []
        if isinstance(self.store, SQLiteRiskStore):
            records = self._query_sqlite(min_lat, min_lon, max_lat, max_lon, risk_level, limit)
        else:
            logger.warning("PostGIS not yet implemented. Falling back to empty results.")
            records = []
            
        features = []
        for r in records:
            lon = r.get("longitude")
            lat = r.get("latitude")
            if lon is None or lat is None:
                continue
                
            name_map = {
                "26.9124_75.7873": "Jaipur Ridge",
                "27.5000_85.5000": "Kathmandu North",
                "31.1046_77.1734": "Shimla Slope",
                "31.6908_76.5177": "Hamirpur West"
            }
            loc_id = r.get("location_id")

            geom = PointGeometry(coordinates=(lon, lat))
            props = {
                "id":                          loc_id,  # standard GeoJSON id alias
                "location_id":                 loc_id,
                "name":                        name_map.get(loc_id) or r.get("name") or f"Lat {lat:.2f}°, Lon {lon:.2f}°",
                "latitude":                    lat,
                "longitude":                   lon,
                "susceptibility_probability":  r.get("susceptibility_probability"),
                "probability":                 r.get("susceptibility_probability"),  # alias for frontend
                "susceptibility_class":        r.get("susceptibility_class"),
                "rainfall_7d":                 r.get("rainfall_7d"),
                "rainfall_trigger_state":      r.get("rainfall_trigger_state"),
                "dynamic_risk":                r.get("dynamic_risk"),
                "risk_level":                  r.get("risk_level"),
                "timestamp":                   r.get("timestamp"),
                "stale":                       bool(r.get("stale", 0))
            }
            features.append(GeoJSONFeature(geometry=geom, properties=props))
            
        return GeoJSONFeatureCollection(features=features)

    def _query_sqlite(
        self,
        min_lat: Optional[float],
        min_lon: Optional[float],
        max_lat: Optional[float],
        max_lon: Optional[float],
        risk_level: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        conn = self.store._conn
        query = """
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY location_id ORDER BY timestamp DESC) as rn
            FROM risk_history
        ) WHERE rn = 1
        """
        params = []
        if min_lat is not None:
            query += " AND latitude >= ?"
            params.append(min_lat)
        if max_lat is not None:
            query += " AND latitude <= ?"
            params.append(max_lat)
        if min_lon is not None:
            query += " AND longitude >= ?"
            params.append(min_lon)
        if max_lon is not None:
            query += " AND longitude <= ?"
            params.append(max_lon)
        if risk_level is not None:
            query += " AND risk_level = ?"
            params.append(risk_level)
            
        query += " LIMIT ?"
        params.append(limit)
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [self.store._row_to_dict(row) for row in rows]
