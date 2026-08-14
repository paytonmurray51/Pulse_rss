import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    OAUTH_STATE_COOKIE,
    PUBLIC_URL,
    build_authorization_url,
    clear_session_cookie,
    exchange_code_for_identity,
    get_current_user,
    is_email_allowed,
    issue_session,
    oauth_configured,
    set_session_cookie,
    _SECURE_COOKIES,
)
from database import get_db
from models import User, UserProfile
from schemas import UserOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/login")
async def login():
    """Begin the Google sign-in flow."""
    if not oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on this server.",
        )

    # CSRF defence: the state we send must come back with the callback.
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(build_authorization_url(state), status_code=307)
    response.set_cookie(
        OAUTH_STATE_COOKIE, state,
        max_age=600, httponly=True, secure=_SECURE_COOKIES, samesite="lax", path="/",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if error:
        return RedirectResponse(f"{PUBLIC_URL}/login?error={quote(error)}", status_code=307)
    if not code:
        return RedirectResponse(f"{PUBLIC_URL}/login?error=missing_code", status_code=307)

    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected or state != expected:
        return RedirectResponse(f"{PUBLIC_URL}/login?error=bad_state", status_code=307)

    claims = await exchange_code_for_identity(code)
    email = (claims.get("email") or "").lower()
    if not email:
        return RedirectResponse(f"{PUBLIC_URL}/login?error=no_email", status_code=307)

    if not await is_email_allowed(db, email):
        logger.warning("Rejected sign-in for %s (not on the invite list)", email)
        return RedirectResponse(f"{PUBLIC_URL}/login?error=not_invited", status_code=307)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email)
        db.add(user)

    # Refreshed on every sign-in so a changed Google avatar or name follows.
    user.google_sub = claims.get("sub") or user.google_sub
    user.name = claims.get("name") or user.name or email.split("@")[0]
    user.picture = claims.get("picture") or user.picture
    user.last_seen_at = datetime.now(timezone.utc)

    await db.flush()

    profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        db.add(UserProfile(user_id=user.id, interests=[], min_score_threshold=5.0))

    await db.commit()
    await db.refresh(user)

    response = RedirectResponse(f"{PUBLIC_URL}/", status_code=307)
    set_session_cookie(response, issue_session(user))
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout():
    response = RedirectResponse(f"{PUBLIC_URL}/login", status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/config")
async def config():
    """Lets the login page explain itself when OAuth is not set up."""
    return {"google_enabled": oauth_configured()}
