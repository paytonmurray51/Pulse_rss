from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user, get_current_user
from database import get_db
from models import AppSettings, User, UserProfile
from schemas import (
    AppSettingsOut, AppSettingsUpdate, UserProfileOut, UserProfileUpdate,
)

router = APIRouter()


async def _profile_for(db: AsyncSession, user: User) -> UserProfile:
    profile = (await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )).scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user.id, interests=[], min_score_threshold=5.0)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def _settings(db: AsyncSession) -> AppSettings:
    settings = (await db.execute(
        select(AppSettings).where(AppSettings.id == 1)
    )).scalar_one_or_none()
    if settings is None:
        settings = AppSettings(id=1, auto_refresh_enabled=False, refresh_interval_minutes=1440)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.get("", response_model=UserProfileOut)
async def get_interests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _profile_for(db, user)


@router.put("", response_model=UserProfileOut)
async def update_interests(
    payload: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _profile_for(db, user)
    if payload.interests is not None:
        profile.interests = payload.interests
    if payload.min_score_threshold is not None:
        profile.min_score_threshold = payload.min_score_threshold
    await db.commit()
    await db.refresh(profile)
    return profile


# ─── instance-wide settings (admin) ──────────────────────────────────────────

@router.get("/app-settings", response_model=AppSettingsOut)
async def get_app_settings(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Readable by everyone so the UI can show when the last sync ran."""
    return await _settings(db)


@router.put("/app-settings", response_model=AppSettingsOut)
async def update_app_settings(
    payload: AppSettingsUpdate,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    settings = await _settings(db)
    if payload.auto_refresh_enabled is not None:
        settings.auto_refresh_enabled = payload.auto_refresh_enabled
    if payload.refresh_interval_minutes is not None:
        settings.refresh_interval_minutes = payload.refresh_interval_minutes
    await db.commit()
    await db.refresh(settings)
    return settings
