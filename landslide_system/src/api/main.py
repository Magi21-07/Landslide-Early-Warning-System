from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from src.api.config import get_settings
from src.api.routers import health, landslide, risk, rainfall, geospatial, alerts, demo
from src.api.middleware import CorrelationIDMiddleware, StructuredLoggingMiddleware
from src.api.exceptions import global_exception_handler, value_error_handler, validation_exception_handler

settings = get_settings()

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION
)

# Add Middlewares
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(CorrelationIDMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(ValueError, value_error_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Include routers
app.include_router(health.router)
app.include_router(landslide.router)
app.include_router(risk.router)
app.include_router(rainfall.router)
app.include_router(geospatial.router)
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(demo.router)

@app.get("/")
def root():
    return {
        "system": "Landslide Early Warning System API",
        "version": "1.0.0",
        "documentation": "/docs",
        "status": "online"
    }
