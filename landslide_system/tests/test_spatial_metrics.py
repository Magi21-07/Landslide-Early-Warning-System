import pytest
from src.etl.spatial_service import get_proximity_metrics

def test_distinct_target_distances():
    # Target A
    result_a, prov_a = get_proximity_metrics(30.43, 78.27)
    # Target B
    result_b, prov_b = get_proximity_metrics(31.10, 77.17)
    
    dist_a = result_a["distance_to_river_m"]
    dist_b = result_b["distance_to_river_m"]
    
    assert dist_a is not None or prov_a.fallback_used
    assert dist_b is not None or prov_b.fallback_used
    
    # If both are real, they must be distinct
    if dist_a is not None and dist_b is not None and not prov_a.fallback_used and not prov_b.fallback_used:
        assert dist_a != dist_b, "Different coordinates should not share the exact same dynamic distance to river."
        
def test_no_hardcoded_1200_fallback():
    # Use invalid or extreme coordinates where fallback happens (e.g., network failure, but we mock it)
    import httpx
    from unittest.mock import patch
    with patch("src.etl.spatial_service._make_client") as mock_client_cls:
        ctx = mock_client_cls.return_value.__enter__.return_value
        ctx.post.side_effect = httpx.TimeoutException("timeout")
        
        result, prov = get_proximity_metrics(30.43, 78.27)
        
        assert prov.fallback_used is True
        assert result["distance_to_river_m"] is None, "Fallback should be None, not 1200.0"
        assert result.get("distance_to_river_m") != 1200.0
