"""Admin API router for dynamic configuration hot-reload.

Provides ``PUT /admin/config`` with HMAC-SHA256 authentication for
over-the-air configuration updates, and ``GET /admin/config`` for
reading the current sanitized config.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from utils.config import ConfigManager
from utils.constants import ADMIN_HMAC_HEADER

logger = logging.getLogger(__name__)


class ConfigUpdateRequest(BaseModel):
    """Partial config update payload."""
    updates: Dict[str, Any] = Field(
        ...,
        description="Dict of section_name -> partial values to merge",
    )


def create_admin_router(
    config_manager: ConfigManager,
    hmac_secret: str,
    max_payload_bytes: int,
) -> APIRouter:
    """Create an admin API router bound to a ConfigManager.

    Parameters
    ----------
    config_manager:
        The ConfigManager instance to apply updates to.
    hmac_secret:
        The HMAC-SHA256 secret for authenticating requests.
    max_payload_bytes:
        Maximum allowed request body size.
    """
    router = APIRouter(prefix="/admin", tags=["admin"])

    def _verify_hmac(request_body: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature of the request body."""
        expected = hmac.new(
            hmac_secret.encode("utf-8"),
            request_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @router.get("/config")
    async def get_config() -> Dict[str, Any]:
        """Return current sanitized configuration (secrets redacted)."""
        return config_manager.get_sanitized()

    @router.put("/config")
    async def update_config(request: Request) -> Dict[str, Any]:
        """Apply a partial config update with HMAC authentication.

        Expects:
        - Header ``X-Tricorder-HMAC``: SHA-256 HMAC of the raw request body
        - JSON body: ``{"updates": {"section": {"key": "value"}}}``
        """
        # Verify HMAC signature
        signature = request.headers.get(ADMIN_HMAC_HEADER, "")
        if not signature:
            raise HTTPException(
                status_code=401,
                detail=f"Missing {ADMIN_HMAC_HEADER} header",
            )

        body = await request.body()
        if len(body) > max_payload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Payload exceeds {max_payload_bytes} bytes",
            )

        if not _verify_hmac(body, signature):
            raise HTTPException(
                status_code=403,
                detail="Invalid HMAC signature",
            )

        # Parse and apply updates
        try:
            import json
            payload = json.loads(body)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        updates = payload.get("updates")
        if not isinstance(updates, dict):
            raise HTTPException(
                status_code=400,
                detail="Body must contain 'updates' dict",
            )

        try:
            diff = config_manager.reload(updates)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:
            logger.error("Config reload failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Config reload failed. Check server logs.",
            )

        return {
            "ok": True,
            "changes": diff,
        }

    return router
