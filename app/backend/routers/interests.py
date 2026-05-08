from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import UserProfile
from schemas import UserProfileOut, UserProfileUpdate

router = APIRouter()


@router.get("", response_model=UserProfileOut)
async def get_interests(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(id=1, interests=[], min_score_threshold=5.0, refresh_interval_minutes=30)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.put("", response_model=UserProfileOut)
async def update_interests(
    payload: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(id=1, interests=[], min_score_threshold=5.0, refresh_interval_minutes=30)
        db.add(profile)

    if payload.interests is not None:
        profile.interests = payload.interests
    if payload.min_score_threshold is not None:
        profile.min_score_threshold = payload.min_score_threshold
    if payload.refresh_interval_minutes is not None:
        profile.refresh_interval_minutes = payload.refresh_interval_minutes

    await db.commit()
    await db.refresh(profile)
    return profile
