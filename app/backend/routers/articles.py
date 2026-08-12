import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal, get_db
from models import Article, Feed, FeedbackBlock, UserProfile
from schemas import ArticleListResponse, ArticleOut, StatsOut, SummaryOut
from services.article_reader import ArticleUnreadable, fetch_article_text
from services.claude_service import process_new_articles, summarize_article
from services.rss_fetcher import fetch_feed

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── helpers ────────────────────────────────────────────────────────────────

async def _build_feedback_context(db: AsyncSession) -> dict:
    liked_q = await db.execute(
        select(Article.title)
        .where(Article.user_rating == "liked")
        .order_by(Article.created_at.desc())
        .limit(50)
    )
    implicit_q = await db.execute(
        select(Article.title)
        .where(
            Article.open_count >= 2,
            Article.read_later == True,
            Article.user_rating == None,
        )
        .order_by(Article.created_at.desc())
        .limit(20)
    )
    disliked_q = await db.execute(
        select(Article.title)
        .where(Article.user_rating == "disliked")
        .order_by(Article.created_at.desc())
        .limit(30)
    )
    blocks_q = await db.execute(select(FeedbackBlock))
    blocks = blocks_q.scalars().all()

    blocked_sources = [b.value for b in blocks if b.block_type == "source"]
    blocked_topics = [b.value for b in blocks if b.block_type == "topic"]

    return {
        "liked_titles": [r[0] for r in liked_q.all()],
        "implicit_liked_titles": [r[0] for r in implicit_q.all()],
        "disliked_titles": [r[0] for r in disliked_q.all()],
        "blocked_sources": blocked_sources,
        "blocked_topics": blocked_topics,
    }


async def _run_full_refresh(session_factory=None):
    """Fetch every active feed, score new articles, and persist the results.

    Callers on the FastAPI event loop can rely on the default factory. The
    scheduler runs on its own short-lived loop and passes a factory bound to
    an engine it owns and disposes.
    """
    factory = session_factory or AsyncSessionLocal
    async with factory() as db:
        try:
            feeds_result = await db.execute(select(Feed).where(Feed.active == True))
            feeds = feeds_result.scalars().all()

            profile_result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
            profile = profile_result.scalar_one_or_none()
            interests = profile.interests if profile and profile.interests else []

            feedback_ctx = await _build_feedback_context(db)
            blocked_sources_lower = [s.lower() for s in feedback_ctx.get("blocked_sources", [])]

            new_articles: list[Article] = []

            for feed in feeds:
                if feed.name.lower() in blocked_sources_lower:
                    logger.info(f"Skipping blocked source: {feed.name}")
                    continue

                entries = await fetch_feed(feed)
                feed.last_fetched = datetime.now(timezone.utc)

                for entry in entries:
                    existing = await db.execute(
                        select(Article.id).where(Article.url == entry["url"])
                    )
                    if existing.scalar_one_or_none():
                        continue

                    article = Article(
                        feed_id=feed.id,
                        title=entry["title"],
                        url=entry["url"],
                        description=entry.get("description"),
                        author=entry.get("author"),
                        published_at=entry.get("published_at"),
                        thumbnail=entry.get("thumbnail"),
                    )
                    db.add(article)
                    new_articles.append(article)

            await db.commit()

            if not new_articles:
                logger.info("No new articles found in refresh")
                return

            # Reload with feed relationship for process_new_articles
            article_ids = []
            for a in new_articles:
                await db.refresh(a)
                article_ids.append(a.id)

            loaded_result = await db.execute(
                select(Article)
                .where(Article.id.in_(article_ids))
                .options(selectinload(Article.feed))
            )
            loaded_articles = loaded_result.scalars().all()

            scores = await process_new_articles(loaded_articles, interests, feedback_ctx)

            blocked_topics_lower = [t.lower() for t in feedback_ctx.get("blocked_topics", [])]

            for article in loaded_articles:
                score_data = scores.get(article.url, {})
                article.ai_score = score_data.get("ai_score", 5.0)
                article.ai_summary = score_data.get("ai_summary")
                article.ai_tags = score_data.get("ai_tags", [])
                article.ai_filtered = score_data.get("ai_filtered", False)
                article.ai_filter_reason = score_data.get("ai_filter_reason")
                article.ai_processed = True

                # Post-process: block by topic
                tags_lower = [t.lower() for t in (article.ai_tags or [])]
                for blocked in blocked_topics_lower:
                    if any(blocked in tag for tag in tags_lower):
                        article.ai_filtered = True
                        article.ai_filter_reason = "Matches a blocked topic"
                        break

            await db.commit()
            logger.info(f"Refresh complete: {len(loaded_articles)} new articles processed")

        except Exception as e:
            logger.error(f"Error during full refresh: {e}", exc_info=True)
            await db.rollback()


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
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Article)
        .options(selectinload(Article.feed))
        .where(Article.ai_processed == True)
    )

    if not show_filtered:
        query = query.where(Article.ai_filtered == False)
    if feed_id is not None:
        query = query.where(Article.feed_id == feed_id)
    if category is not None:
        feeds_result = await db.execute(select(Feed.id).where(Feed.category == category))
        feed_ids = [r[0] for r in feeds_result.all()]
        query = query.where(Article.feed_id.in_(feed_ids))
    if read_later is True:
        query = query.where(Article.read_later == True)
    if unread_only:
        query = query.where(Article.is_read == False)

    # Fall back to the saved profile threshold when the caller does not send
    # one, so the Settings slider actually governs the default feed.
    if min_score is None:
        profile_result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = profile_result.scalar_one_or_none()
        min_score = profile.min_score_threshold if profile else None
    if min_score:
        query = query.where(Article.ai_score >= min_score)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    if sort == "newest":
        order = (Article.published_at.desc().nulls_last(), Article.ai_score.desc())
    else:
        order = (Article.ai_score.desc().nulls_last(), Article.published_at.desc())

    query = query.order_by(*order).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    articles = result.scalars().all()

    items = []
    for a in articles:
        out = ArticleOut.model_validate(a)
        if a.feed:
            out.feed_name = a.feed.name
            out.feed_type = a.feed.feed_type
        items.append(out)

    return ArticleListResponse(items=items, total=total, page=page, per_page=per_page)


@router.post("/refresh")
async def refresh_articles(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    background_tasks.add_task(_run_full_refresh)
    return {"status": "refresh started"}


@router.get("/stats", response_model=StatsOut)
async def get_stats(db: AsyncSession = Depends(get_db)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_result = await db.execute(
        select(func.count(Article.id)).where(Article.ai_processed == True, Article.ai_filtered == False)
    )
    unread_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.ai_processed == True,
            Article.ai_filtered == False,
            Article.is_read == False,
        )
    )
    read_later_result = await db.execute(
        select(func.count(Article.id)).where(Article.read_later == True)
    )
    total_feeds_result = await db.execute(select(func.count(Feed.id)))
    active_feeds_result = await db.execute(
        select(func.count(Feed.id)).where(Feed.active == True)
    )
    avg_score_result = await db.execute(
        select(func.avg(Article.ai_score)).where(
            Article.ai_processed == True, Article.ai_filtered == False
        )
    )
    today_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.ai_processed == True,
            Article.ai_filtered == False,
            Article.created_at >= today_start,
        )
    )

    avg_score = avg_score_result.scalar_one_or_none()
    if avg_score is not None:
        avg_score = round(float(avg_score), 1)

    return StatsOut(
        total_articles=total_result.scalar_one(),
        unread_articles=unread_result.scalar_one(),
        read_later_count=read_later_result.scalar_one(),
        total_feeds=total_feeds_result.scalar_one(),
        active_feeds=active_feeds_result.scalar_one(),
        avg_score=avg_score,
        articles_today=today_result.scalar_one(),
    )


@router.post("/{article_id}/summarize", response_model=SummaryOut)
async def summarize(
    article_id: int,
    refresh: bool = Query(False, description="Regenerate even if a summary is cached"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Article).where(Article.id == article_id).options(selectinload(Article.feed))
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Serve the cache first — a given article should only ever be paid for once.
    if article.ai_full_summary and not refresh:
        try:
            cached = json.loads(article.ai_full_summary)
            return SummaryOut(
                article_id=article.id,
                key_points=cached.get("key_points", []),
                why_it_matters=cached.get("why_it_matters"),
                reading_time_min=cached.get("reading_time_min"),
                cached=True,
                generated_at=article.ai_full_summary_at,
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

    profile_result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
    profile = profile_result.scalar_one_or_none()
    interests = profile.interests if profile and profile.interests else []

    try:
        summary = await summarize_article(article.title, text, interests)
    except Exception as e:
        logger.error("Summarization failed for article %s: %s", article.id, e)
        raise HTTPException(
            status_code=502,
            detail="The summarizer failed on this article. Try again in a moment.",
        )

    # Computed here rather than asked of the model, which guesses badly at it.
    summary["reading_time_min"] = max(1, round(word_count / 200))

    article.ai_full_summary = json.dumps(summary)
    article.ai_full_summary_at = datetime.now(timezone.utc)
    await db.commit()

    return SummaryOut(
        article_id=article.id,
        key_points=summary["key_points"],
        why_it_matters=summary.get("why_it_matters"),
        reading_time_min=summary["reading_time_min"],
        cached=False,
        generated_at=article.ai_full_summary_at,
    )


@router.post("/{article_id}/read-later", response_model=ArticleOut)
async def toggle_read_later(article_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Article).where(Article.id == article_id).options(selectinload(Article.feed))
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.read_later = not article.read_later
    await db.commit()
    await db.refresh(article)
    out = ArticleOut.model_validate(article)
    if article.feed:
        out.feed_name = article.feed.name
        out.feed_type = article.feed.feed_type
    return out


@router.post("/{article_id}/read", response_model=ArticleOut)
async def mark_read(article_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Article).where(Article.id == article_id).options(selectinload(Article.feed))
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.is_read = True
    article.open_count = (article.open_count or 0) + 1
    await db.commit()
    await db.refresh(article)
    out = ArticleOut.model_validate(article)
    if article.feed:
        out.feed_name = article.feed.name
        out.feed_type = article.feed.feed_type
    return out


@router.post("/{article_id}/feedback", response_model=ArticleOut)
async def set_feedback(
    article_id: int,
    rating: str = Query("", description="'liked', 'disliked', or '' to clear"),
    db: AsyncSession = Depends(get_db),
):
    if rating not in ("liked", "disliked", ""):
        raise HTTPException(status_code=422, detail="rating must be 'liked', 'disliked', or ''")

    result = await db.execute(
        select(Article).where(Article.id == article_id).options(selectinload(Article.feed))
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.user_rating = rating if rating else None
    if rating == "liked":
        article.is_read = True

    await db.commit()
    await db.refresh(article)
    out = ArticleOut.model_validate(article)
    if article.feed:
        out.feed_name = article.feed.name
        out.feed_type = article.feed.feed_type
    return out
