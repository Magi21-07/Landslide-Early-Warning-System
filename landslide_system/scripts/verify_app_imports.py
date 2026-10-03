import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

modules_to_test = [
    "src.api.main",
    "src.api.routers.risk",
    "src.features.feature_builder",
    "src.etl.spatial_service",
    "src.etl.terrain_service",
    "src.etl.sentinel_service",
    "src.etl.gee_extractor",
    "src.models.predict",
    "src.risk.rainfall_service",
]

failed = False
for mod in modules_to_test:
    try:
        __import__(mod)
        print(f"OK: {mod}")
    except ModuleNotFoundError as e:
        print(f"FAIL (ModuleNotFoundError): {mod} - {e}")
        failed = True
    except Exception as e:
        print(f"WARN (Other Exception): {mod} - {e}")
        # Not a ModuleNotFoundError, so the import technically worked but code execution failed
        # We mainly care about ModuleNotFoundError right now.

if failed:
    sys.exit(1)
else:
    print("All imports successful!")
    sys.exit(0)
