"""Google OAuth 2.0 flow for connecting a user's Google Calendar.

Env vars required:
  GOOGLE_CLIENT_ID      — OAuth client ID from Google Cloud Console
  GOOGLE_CLIENT_SECRET  — OAuth client secret
  GOOGLE_REDIRECT_URI   — e.g. http://localhost:8000/api/v1/google/callback

Flow:
  1. Frontend calls GET /google/auth-url?calendar_resource_id=xxx
     → returns { url: "https://accounts.google.com/o/oauth2/..." }
  2. User is redirected to Google, grants calendar access
  3. Google redirects to GET /google/callback?code=xxx&state=xxx
     → exchanges code for tokens, saves to CalendarResource, redirects to frontend
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.infra.database.repositories.calendar_resource import CalendarResourceRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["google-oauth"])

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _get_oauth_config():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/google/callback"
    )
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars are required for OAuth.",
        )
    return client_id, client_secret, redirect_uri


@router.get("/auth-url")
async def get_auth_url(calendar_resource_id: str = Query(...)):
    """Generate Google OAuth consent URL. State carries the calendar_resource_id."""
    client_id, _, redirect_uri = _get_oauth_config()

    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": calendar_resource_id,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": url}


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Handle Google OAuth callback: exchange code for tokens, save to CalendarResource."""
    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(f"{_FRONTEND_URL}/calendars?error={error}")

    calendar_resource_id = state
    client_id, client_secret, redirect_uri = _get_oauth_config()

    import httpx

    token_resp = await httpx.AsyncClient().post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    if token_resp.status_code != 200:
        logger.error("Google token exchange failed: %s", token_resp.text)
        return RedirectResponse(f"{_FRONTEND_URL}/calendars?error=token_exchange_failed")

    token_data = token_resp.json()

    creds_payload = {
        "type": "oauth",
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "expiry": token_data.get("expires_in"),
    }

    # Fetch user's primary calendar email for calendar_id
    calendar_id = "primary"
    try:
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        cal_resp = await httpx.AsyncClient().get(
            "https://www.googleapis.com/calendar/v3/calendars/primary",
            headers=headers,
        )
        if cal_resp.status_code == 200:
            cal_data = cal_resp.json()
            calendar_id = cal_data.get("id", "primary")
    except Exception as exc:
        logger.warning("Could not fetch calendar info: %s", exc)

    repo = CalendarResourceRepository(session)
    try:
        resource_uuid = UUID(calendar_resource_id)
    except ValueError:
        return RedirectResponse(f"{_FRONTEND_URL}/calendars?error=invalid_resource_id")

    resource = await repo.get_by_id(resource_uuid)
    if resource is None:
        return RedirectResponse(f"{_FRONTEND_URL}/calendars?error=resource_not_found")

    await repo.update(resource_uuid, {
        "calendar_type": "google",
        "calendar_id": calendar_id,
        "credentials": json.dumps(creds_payload),
    })
    await session.commit()

    logger.info(
        "Google OAuth: connected calendar %s to resource %s (%s)",
        calendar_id, resource.name, resource_uuid,
    )

    return RedirectResponse(f"{_FRONTEND_URL}/calendars?connected={calendar_resource_id}")
