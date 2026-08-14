import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user
from database import get_db
from models import AllowedEmail, User
from schemas import MemberCreate, MemberOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[MemberOut])
async def list_members(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Invited addresses, joined to accounts for the ones that signed in."""
    rows = (await db.execute(
        select(AllowedEmail, User)
        .outerjoin(User, User.email == AllowedEmail.email)
        .order_by(AllowedEmail.created_at)
    )).all()

    return [
        MemberOut(
            email=allowed.email, note=allowed.note, created_at=allowed.created_at,
            user_id=user.id if user else None,
            name=user.name if user else None,
            picture=user.picture if user else None,
            is_admin=user.is_admin if user else False,
            last_seen_at=user.last_seen_at if user else None,
        )
        for allowed, user in rows
    ]


@router.post("", response_model=MemberOut, status_code=201)
async def invite_member(
    payload: MemberCreate,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    email = payload.email.lower()
    existing = (await db.execute(
        select(AllowedEmail).where(AllowedEmail.email == email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="That address is already invited")

    allowed = AllowedEmail(email=email, note=payload.note)
    db.add(allowed)
    await db.commit()
    await db.refresh(allowed)

    logger.info("Invited %s", email)
    return MemberOut(email=allowed.email, note=allowed.note, created_at=allowed.created_at)


@router.delete("/{email}", status_code=204)
async def revoke_member(
    email: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    email = email.lower()
    if email == admin.email:
        raise HTTPException(status_code=400, detail="You can't remove your own access")

    allowed = (await db.execute(
        select(AllowedEmail).where(AllowedEmail.email == email)
    )).scalar_one_or_none()
    if not allowed:
        raise HTTPException(status_code=404, detail="Not on the invite list")

    await db.delete(allowed)

    # The account and its data stay, so re-inviting restores everything. The
    # session check rejects them at the next request either way.
    await db.commit()
    logger.info("Revoked access for %s", email)
