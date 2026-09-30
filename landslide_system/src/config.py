import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# GEE Project Configuration
EE_PROJECT_ID = os.getenv("EE_PROJECT_ID")

# India Bounding Box: [min_lon, min_lat, max_lon, max_lat]
ROI_BOUNDS = [68.0, 6.0, 98.0, 36.0]
