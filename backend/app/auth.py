"""
API Key Authentication Dependency
-----------------------------------
If API_SECRET_KEY is set in .env, all protected endpoints require the
`X-API-Key` header to match. Leave empty to run in open/demo mode.

Usage:
    @router.get("/protected", dependencies=[Depends(require_api_key)])
"""
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from app.config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(API_KEY_HEADER)):
    """Dependency that enforces API key auth when API_SECRET_KEY is configured."""
    if not settings.API_SECRET_KEY:
        # Demo mode: no auth required
        return None
    if api_key != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Supply `X-API-Key` header.",
        )
    return api_key
