import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "InvoiceIQ API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    
    # Storage & DB
    DATABASE_URL: str = "sqlite:///./invoiceiq.db"
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "uploads")
    SAMPLES_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "samples")
    
    # Vision LLM Keys
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    
    # Default model preference
    DEFAULT_LLM_PROVIDER: str = "auto" # groq, openai, gemini, or mock
    
    # Webhook integration default (e.g. n8n workflow target)
    DEFAULT_WEBHOOK_URL: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure required directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.SAMPLES_DIR, exist_ok=True)
