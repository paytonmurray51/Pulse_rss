from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_admin_user, get_current_user
from database import get_db
from models import Feed, Article, User
from schemas import FeedCreate, FeedOut, FeedUpdate
from services.rss_fetcher import detect_feed_type, resolve_youtube_channel_to_feed_url

router = APIRouter()


@router.get("", response_model=list[FeedOut])
async def list_feeds(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_subq = (
        select(Article.feed_id, func.count(Article.id).label("article_count"))
        .group_by(Article.feed_id)
        .subquery()
    )
    result = await db.execute(
        select(Feed, func.coalesce(count_subq.c.article_count, 0).label("article_count"))
        .outerjoin(count_subq, Feed.id == count_subq.c.feed_id)
        .order_by(Feed.created_at.desc())
    )
    rows = result.all()
    feeds = []
    for feed, count in rows:
        out = FeedOut.model_validate(feed)
        out.article_count = count
        feeds.append(out)
    return feeds


@router.post("", response_model=FeedOut, status_code=201)
async def create_feed(
    payload: FeedCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    feed_url = payload.url.strip()
    feed_type = detect_feed_type(feed_url)

    if feed_type == "youtube" and "feeds/videos.xml" not in feed_url:
        try:
            feed_url = await resolve_youtube_channel_to_feed_url(feed_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    existing = await db.execute(select(Feed).where(Feed.url == feed_url))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Feed with this URL already exists")

    feed = Feed(
        name=payload.name,
        url=feed_url,
        feed_type=feed_type,
        category=payload.category,
    )
    db.add(feed)
    await db.commit()
    await db.refresh(feed)

    out = FeedOut.model_validate(feed)
    out.article_count = 0
    return out


@router.put("/{feed_id}", response_model=FeedOut)
async def update_feed(
    feed_id: int,
    payload: FeedUpdate,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    if payload.name is not None:
        feed.name = payload.name
    if payload.url is not None:
        feed.url = payload.url
    if payload.category is not None:
        feed.category = payload.category
    if payload.active is not None:
        feed.active = payload.active

    await db.commit()
    await db.refresh(feed)

    count_result = await db.execute(
        select(func.count(Article.id)).where(Article.feed_id == feed_id)
    )
    count = count_result.scalar_one()
    out = FeedOut.model_validate(feed)
    out.article_count = count
    return out


@router.delete("/{feed_id}", status_code=204)
async def delete_feed(
    feed_id: int,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    await db.delete(feed)
    await db.commit()
