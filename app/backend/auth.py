import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AllowedEmail, User

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Signing key for our own session cookie. Generated per-process if unset so
# local development works; in production it must be stable or every deploy
# signs everyone out.
SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(32)
SESSION_COOKIE = "pulse_session"
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))
OAUTH_STATE_COOKIE = "pulse_oauth_state"

# Public origin, used to build the OAuth redirect URI. Must exactly match the
# value registered in the Google Cloud console.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8080").rstrip("/")

# Cookies are only marked Secure over HTTPS; plain http breaks local dev.
_SECURE_COOKIES = PUBLIC_URL.startswith("https://")


def oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def redirect_uri() -> str:
    return f"{PUBLIC_URL}/api/auth/callback"


def build_authorization_url(state: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_identity(code: str) -> dict:
    """Trade an authorization code for a verified Google identity."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        logger.error("Google token exchange failed: %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=400, detail="Google sign-in failed.")

    raw_id_token = resp.json().get("id_token")
    if not raw_id_token:
        raise HTTPException(status_code=400, detail="Google did not return an identity token.")

    try:
        # Verifies signature, issuer, audience and expiry against Google's keys.
        claims = google_id_token.verify_oauth2_token(
            raw_id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        logger.error("ID token verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Could not verify Google identity.")

    if not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="Your Google email address is not verified.")

    return claims


def issue_session(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=SESSION_DAYS)).timestamp()),
        },
        SESSION_SECRET,
        algorithm="HS256",
    )


def set_session_cookie(response, token: str):
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=_SECURE_COOKIES,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE, path="/")


async def is_email_allowed(db: AsyncSession, email: str) -> bool:
    result = await db.execute(
        select(AllowedEmail).where(AllowedEmail.email == email.lower())
    )
    return result.scalar_one_or_none() is not None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")

    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")

    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists")

    # Revoking an invite ends access at the next request, not just at sign-in.
    if not await is_email_allowed(db, user.email):
        raise HTTPException(status_code=403, detail="Your access to Pulse has been removed.")

    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user
