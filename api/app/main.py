"""FastAPI application entry point — Claims Photo Fraud Detection API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, claims, dashboard, health, photos, prompts

app = FastAPI(
    title="Claims Photo Fraud Detection API",
    description="GCP-native fraud detection pipeline for insurance claim photos",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# -- CORS --
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Routers --
# Health is mounted at /api/health (no prefix on health router itself)
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(claims.router, prefix="/api")
app.include_router(photos.router, prefix="/api")
app.include_router(prompts.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
