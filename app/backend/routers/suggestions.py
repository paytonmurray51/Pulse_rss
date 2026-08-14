import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user, get_current_user
from database import get_db
from models import Suggestion, User
from schemas import SuggestionCreate, SuggestionOut
from services.email_service import email_configured, send_suggestion_email

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_out(s: Suggestion, author: User | None) -> SuggestionOut:
    return SuggestionOut(
        id=s.id, message=s.message, emailed=s.emailed, resolved=s.resolved,
        created_at=s.created_at,
        author_name=author.name if author else None,
        author_email=author.email if author else None,
    )


@router.post("", response_model=SuggestionOut, status_code=201)
async def submit_suggestion(
    payload: SuggestionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    suggestion = Suggestion(user_id=user.id, message=payload.message.strip())
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)

    # Stored first, emailed second: a mail outage must never lose feedback
    # somebody took the trouble to write. Failures are recorded, not raised.
    if email_configured():
        try:
            await send_suggestion_email(user.name or user.email, user.email, suggestion.message)
            suggestion.emailed = True
            suggestion.email_error = None
        except Exception as e:
            suggestion.email_error = str(e)[:512]
            logger.error("Could not email suggestion %s: %s", suggestion.id, e)
        await db.commit()
        await db.refresh(suggestion)
    else:
        suggestion.email_error = "Email is not configured on this server"
        await db.commit()
        await db.refresh(suggestion)

    return _to_out(suggestion, user)


@router.get("", response_model=list[SuggestionOut])
async def list_suggestions(
    include_resolved: bool = False,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Suggestion, User).join(User, User.id == Suggestion.user_id)
    if not include_resolved:
        query = query.where(Suggestion.resolved == False)
    rows = (await db.execute(query.order_by(Suggestion.created_at.desc()))).all()
    return [_to_out(s, u) for s, u in rows]


@router.post("/{suggestion_id}/resolve", response_model=SuggestionOut)
async def toggle_resolved(
    suggestion_id: int,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(Suggestion, User)
        .join(User, User.id == Suggestion.user_id)
        .where(Suggestion.id == suggestion_id)
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion, author = row
    suggestion.resolved = not suggestion.resolved
    await db.commit()
    await db.refresh(suggestion)
    return _to_out(suggestion, author)
