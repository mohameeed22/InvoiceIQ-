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
