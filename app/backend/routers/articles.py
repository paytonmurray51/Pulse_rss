import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db
from models import (
    Article, ArticleScore, ArticleState, Feed, FeedbackBlock, User, UserProfile,
)
from schemas import (
    ArticleListResponse, ArticleOut, RefreshResult, StatsOut, SummaryOut,
)
from services.article_reader import ArticleUnreadable, fetch_article_text
from services.claude_service import (
    explain_anthropic_error, process_new_articles, summarize_article,
)
from services.rss_fetcher import fetch_feed

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── helpers ────────────────────────────────────────────────────────────────

async def _build_feedback_context(db: AsyncSession, user_id: int) -> dict:
    """Recent likes, dislikes and blocks — for this reader only."""
    liked_q = await db.execute(
        select(Article.title)
        .join(ArticleState, ArticleState.article_id == Article.id)
        .where(ArticleState.user_id == user_id, ArticleState.user_rating == "liked")
        .order_by(ArticleState.updated_at.desc()).limit(50)
    )
    implicit_q = await db.execute(
        select(Article.title)
        .join(ArticleState, ArticleState.article_id == Article.id)
        .where(
            ArticleState.user_id == user_id,
            ArticleState.open_count >= 2,
            ArticleState.read_later == True,
            ArticleState.user_rating == None,
        )
        .order_by(ArticleState.updated_at.desc()).limit(20)
    )
    disliked_q = await db.execute(
        select(Article.title)
        .join(ArticleState, ArticleState.article_id == Article.id)
        .where(ArticleState.user_id == user_id, ArticleState.user_rating == "disliked")
        .order_by(ArticleState.updated_at.desc()).limit(30)
    )
    blocks_q = await db.execute(
        select(FeedbackBlock).where(FeedbackBlock.user_id == user_id)
    )
    blocks = blocks_q.scalars().all()

    return {
        "liked_titles": [r[0] for r in liked_q.all()],
        "implicit_liked_titles": [r[0] for r in implicit_q.all()],
        "disliked_titles": [r[0] for r in disliked_q.all()],
        "blocked_sources": [b.value for b in blocks if b.block_type == "source"],
        "blocked_topics": [b.value for b in blocks if b.block_type == "topic"],
    }


async def ingest_feeds(db: AsyncSession) -> int:
    """Fetch every active feed and store new articles. No AI, no reader."""
    feeds = (await db.execute(select(Feed).where(Feed.active == True))).scalars().all()
    created = 0

    for feed in feeds:
        entries = await fetch_feed(feed)
        feed.last_fetched = datetime.now(timezone.utc)

        for entry in entries:
            exists = await db.execute(select(Article.id).where(Article.url == entry["url"]))
            if exists.scalar_one_or_none():
                continue
            db.add(Article(
                feed_id=feed.id,
                title=entry["title"],
                url=entry["url"],
                description=entry.get("description"),
                author=entry.get("author"),
                published_at=entry.get("published_at"),
                thumbnail=entry.get("thumbnail"),
            ))
            created += 1

    await db.commit()
    logger.info("Ingest complete: %d new articles", created)
    return created


async def score_for_user(db: AsyncSession, user: User, limit: int = 200) -> tuple[int, int]:
    """Score everything this reader has no score for yet.

    Returns (scored, deferred). Deferred articles keep no score row at all, so
    the next run retries them rather than freezing a fabricated value.
    """
    profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    ).scalar_one_or_none()
    interests = profile.interests if profile and profile.interests else []

    feedback_ctx = await _build_feedback_context(db, user.id)
    blocked_sources = {s.lower() for s in feedback_ctx["blocked_sources"]}

    already_scored = select(ArticleScore.article_id).where(ArticleScore.user_id == user.id)
    pending = (await db.execute(
        select(Article)
        .options(selectinload(Article.feed))
        .where(Article.id.notin_(already_scored))
        .order_by(Article.published_at.desc().nulls_last())
        .limit(limit)
    )).scalars().all()

    # Blocked sources never reach the model at all.
    pending = [a for a in pending if not (a.feed and a.feed.name.lower() in blocked_sources)]
    if not pending:
        return 0, 0

    scores = await process_new_articles(pending, interests, feedback_ctx)
    blocked_topics = [t.lower() for t in feedback_ctx["blocked_topics"]]

    scored = deferred = 0
    for article in pending:
        data = scores.get(article.url)
        if data is None:
            deferred += 1
            continue

        tags = data.get("ai_tags") or []
        filtered = data.get("ai_filtered", False)
        reason = data.get("ai_filter_reason")
        if any(b in t.lower() for t in tags for b in blocked_topics):
            filtered, reason = True, "Matches a blocked topic"

        await db.execute(
            pg_insert(ArticleScore)
            .values(
                article_id=article.id, user_id=user.id,
                ai_score=data.get("ai_score", 5.0), ai_summary=data.get("ai_summary"),
                ai_tags=tags, ai_filtered=filtered, ai_filter_reason=reason,
            )
            .on_conflict_do_nothing(index_elements=["article_id", "user_id"])
        )
        scored += 1

    await db.commit()
    logger.info("Scored %d for %s (%d deferred)", scored, user.email, deferred)
    return scored, deferred


async def _state_for(db: AsyncSession, article_id: int, user_id: int) -> ArticleState:
    state = (await db.execute(
        select(ArticleState).where(
            ArticleState.article_id == article_id, ArticleState.user_id == user_id
        )
    )).scalar_one_or_none()
    if state is None:
        state = ArticleState(article_id=article_id, user_id=user_id)
        db.add(state)
        await db.flush()
    return state


def _to_out(article: Article, score: ArticleScore | None, state: ArticleState | None) -> ArticleOut:
    return ArticleOut(
        id=article.id, feed_id=article.feed_id,
        feed_name=article.feed.name if article.feed else None,
        feed_type=article.feed.feed_type if article.feed else None,
        title=article.title, url=article.url, description=article.description,
        author=article.author, published_at=article.published_at,
        thumbnail=article.thumbnail, created_at=article.created_at,
        ai_score=score.ai_score if score else None,
        ai_summary=score.ai_summary if score else None,
        ai_tags=score.ai_tags if score else None,
        ai_filtered=score.ai_filtered if score else False,
        read_later=state.read_later if state else False,
        is_read=state.is_read if state else False,
        user_rating=state.user_rating if state else None,
    )


# ─── routes ─────────────────────────────────────────────────────────────────

@router.get("", response_model=ArticleListResponse)
async def list_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    feed_id: int | None = None,
    category: str | None = None,
    read_later: bool | None = None,
    unread_only: bool = False,
    show_filtered: bool = False,
    min_score: float | None = Query(None, ge=0, le=10),
    sort: str = Query("score", pattern="^(score|newest)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Inner-joining scores means an article only appears once *this* reader
    # has been scored for it — nobody sees another person's ranking.
    query = (
        select(Article, ArticleScore, ArticleState)
        .join(ArticleScore, (ArticleScore.article_id == Article.id)
              & (ArticleScore.user_id == user.id))
        .outerjoin(ArticleState, (ArticleState.article_id == Article.id)
                   & (ArticleState.user_id == user.id))
        .options(selectinload(Article.feed))
    )

    if not show_filtered:
        query = query.where(ArticleScore.ai_filtered == False)
    if feed_id is not None:
        query = query.where(Article.feed_id == feed_id)
    if category:
        query = query.where(Article.feed_id.in_(
            select(Feed.id).where(Feed.category == category)
        ))
    if read_later is True:
        query = query.where(ArticleState.read_later == True)
    if unread_only:
        query = query.where((ArticleState.is_read == False) | (ArticleState.id == None))

    if min_score is None:
        profile = (await db.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )).scalar_one_or_none()
        min_score = profile.min_score_threshold if profile else None
    if min_score:
        query = query.where(ArticleScore.ai_score >= min_score)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    if sort == "newest":
        order = (Article.published_at.desc().nulls_last(), ArticleScore.ai_score.desc())
    else:
        order = (ArticleScore.ai_score.desc().nulls_last(), Article.published_at.desc())

    rows = (await db.execute(
        query.order_by(*order).offset((page - 1) * per_page).limit(per_page)
    )).all()

    return ArticleListResponse(
        items=[_to_out(a, s, st) for a, s, st in rows],
        total=total, page=page, per_page=per_page,
    )


@router.post("/refresh", response_model=RefreshResult)
async def refresh_articles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch new articles and score them for the caller.

    Runs inline rather than in the background so the response can report what
    actually happened — including why scoring failed.
    """
    new_articles = await ingest_feeds(db)
    scored, deferred = await score_for_user(db, user)

    if deferred:
        message = (
            f"{new_articles} new, {scored} scored, {deferred} could not be scored — "
            "they will be retried on the next refresh."
        )
    elif scored:
        message = f"{new_articles} new articles, {scored} scored for you."
    else:
        message = "You are up to date — nothing new to score."

    return RefreshResult(
        new_articles=new_articles, scored=scored, deferred=deferred, message=message
    )


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    mine = (
        select(Article.id)
        .join(ArticleScore, (ArticleScore.article_id == Article.id)
              & (ArticleScore.user_id == user.id))
        .where(ArticleScore.ai_filtered == False)
    )

    total = (await db.execute(
        select(func.count()).select_from(mine.subquery())
    )).scalar_one()

    unread = (await db.execute(select(func.count()).select_from(
        mine.outerjoin(ArticleState, (ArticleState.article_id == Article.id)
                       & (ArticleState.user_id == user.id))
        .where((ArticleState.is_read == False) | (ArticleState.id == None)).subquery()
    ))).scalar_one()

    saved = (await db.execute(
        select(func.count(ArticleState.id)).where(
            ArticleState.user_id == user.id, ArticleState.read_later == True
        )
    )).scalar_one()

    avg = (await db.execute(
        select(func.avg(ArticleScore.ai_score)).where(
            ArticleScore.user_id == user.id, ArticleScore.ai_filtered == False
        )
    )).scalar_one_or_none()

    today_count = (await db.execute(select(func.count()).select_from(
        mine.where(Article.created_at >= today).subquery()
    ))).scalar_one()

    unscored = (await db.execute(
        select(func.count(Article.id)).where(Article.id.notin_(
            select(ArticleScore.article_id).where(ArticleScore.user_id == user.id)
        ))
    )).scalar_one()

    return StatsOut(
        total_articles=total,
        unread_articles=unread,
        read_later_count=saved,
        total_feeds=(await db.execute(select(func.count(Feed.id)))).scalar_one(),
        active_feeds=(await db.execute(
            select(func.count(Feed.id)).where(Feed.active == True)
        )).scalar_one(),
        avg_score=round(float(avg), 1) if avg is not None else None,
        articles_today=today_count,
        unscored_articles=unscored,
    )


async def _load_for_user(db: AsyncSession, article_id: int, user_id: int):
    article = (await db.execute(
        select(Article).where(Article.id == article_id).options(selectinload(Article.feed))
    )).scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    score = (await db.execute(
        select(ArticleScore).where(
            ArticleScore.article_id == article_id, ArticleScore.user_id == user_id
        )
    )).scalar_one_or_none()
    return article, score


@router.post("/{article_id}/read-later", response_model=ArticleOut)
async def toggle_read_later(
    article_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article, score = await _load_for_user(db, article_id, user.id)
    state = await _state_for(db, article_id, user.id)
    state.read_later = not state.read_later
    await db.commit()
    return _to_out(article, score, state)


@router.post("/{article_id}/read", response_model=ArticleOut)
async def mark_read(
    article_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article, score = await _load_for_user(db, article_id, user.id)
    state = await _state_for(db, article_id, user.id)
    state.is_read = True
    state.open_count = (state.open_count or 0) + 1
    await db.commit()
    return _to_out(article, score, state)


@router.post("/{article_id}/feedback", response_model=ArticleOut)
async def set_feedback(
    article_id: int,
    rating: str = Query("", description="'liked', 'disliked', or '' to clear"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if rating not in ("liked", "disliked", ""):
        raise HTTPException(status_code=422, detail="rating must be 'liked', 'disliked', or ''")

    article, score = await _load_for_user(db, article_id, user.id)
    state = await _state_for(db, article_id, user.id)
    state.user_rating = rating or None
    if rating == "liked":
        state.is_read = True
    await db.commit()
    return _to_out(article, score, state)


@router.post("/{article_id}/summarize", response_model=SummaryOut)
async def summarize(
    article_id: int,
    refresh: bool = Query(False, description="Regenerate even if a summary is cached"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    article, _ = await _load_for_user(db, article_id, user.id)

    if article.ai_full_summary and not refresh:
        try:
            cached = json.loads(article.ai_full_summary)
            return SummaryOut(
                article_id=article.id,
                key_points=cached.get("key_points", []),
                why_it_matters=cached.get("why_it_matters"),
                reading_time_min=cached.get("reading_time_min"),
                cached=True, generated_at=article.ai_full_summary_at,
            )
        except (ValueError, TypeError):
            logger.warning("Discarding malformed cached summary for article %s", article.id)

    if article.feed and article.feed.feed_type == "youtube":
        raise HTTPException(
            status_code=422,
            detail="Videos can't be summarized — there's no transcript to read.",
        )

    try:
        text, word_count = await fetch_article_text(article.url)
    except ArticleUnreadable as e:
        raise HTTPException(status_code=422, detail=str(e))

    profile = (await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )).scalar_one_or_none()
    interests = profile.interests if profile and profile.interests else []

    try:
        summary = await summarize_article(article.title, text, interests)
    except Exception as e:
        reason = explain_anthropic_error(e)
        logger.error("Summarization failed for article %s: %s", article.id, e)
        lowered = reason.lower()
        if "credit balance" in lowered or "rejected" in lowered or "lacks permission" in lowered:
            status = 503
        elif "rate limited" in lowered:
            status = 429
        else:
            status = 502
        raise HTTPException(status_code=status, detail=reason)

    summary["reading_time_min"] = max(1, round(word_count / 200))
    article.ai_full_summary = json.dumps(summary)
    article.ai_full_summary_at = datetime.now(timezone.utc)
    await db.commit()

    return SummaryOut(
        article_id=article.id,
        key_points=summary["key_points"],
        why_it_matters=summary.get("why_it_matters"),
        reading_time_min=summary["reading_time_min"],
        cached=False, generated_at=article.ai_full_summary_at,
    )
