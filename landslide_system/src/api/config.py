from typing import List, Optional
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class APISettings(BaseSettings):
    API_ENV: str = "development"
    API_TITLE: str = "Landslide Early Warning System API"
    API_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    DATABASE_URL: Optional[str] = None
    API_KEY: str = Field(default="dev-api-key-secret", alias="API_KEY")
    GEE_PROJECT_ID: Optional[str] = None
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache()
def get_settings() -> APISettings:
    return APISettings()
