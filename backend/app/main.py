import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import engine, Base
from app.routers import documents, analytics

# Create Database tables automatically on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-Powered Invoice & Receipt Data Extraction API & Dashboard",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for full flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)

# Mount Uploads directory for document file viewing
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Frontend Static Dashboard path
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
    app.mount("/dashboard", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

@app.get("/")
def root():
    """Serves Dashboard interface or API Root info."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "dashboard": "/dashboard"
    }

@app.get("/health")
def health_check():
    return {"status": "online", "version": settings.VERSION}

@app.get("/api/v1/status")
def system_status():
    """Returns the active configuration status: AI provider, OCR backend, auth mode, and integrations."""
    active_provider = "demo/fallback"
    if settings.GROQ_API_KEY:
        active_provider = "groq_llama3"
    elif settings.OPENAI_API_KEY:
        active_provider = "openai_gpt4o"
    elif settings.GEMINI_API_KEY:
        active_provider = "gemini_flash"

    return {
        "version": settings.VERSION,
        "ai_provider": active_provider,
        "ocr_backend": settings.OCR_BACKEND,
        "auth_mode": "api_key" if settings.API_SECRET_KEY else "open_demo",
        "base_currency": settings.BASE_CURRENCY,
        "integrations": {
            "google_sheets": bool(settings.GOOGLE_SHEET_ID and settings.GOOGLE_SERVICE_ACCOUNT_JSON),
            "airtable": bool(settings.AIRTABLE_API_KEY and settings.AIRTABLE_BASE_ID),
            "webhook": bool(settings.DEFAULT_WEBHOOK_URL),
        }
    }
