from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field


# ─── users & access ──────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    is_admin: bool = False

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    email: str
    note: Optional[str] = None
    created_at: datetime
    # Populated when the invited address has actually signed in.
    user_id: Optional[int] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    is_admin: bool = False
    last_seen_at: Optional[datetime] = None


class MemberCreate(BaseModel):
    email: EmailStr
    note: Optional[str] = None


# ─── feeds ───────────────────────────────────────────────────────────────────

class FeedCreate(BaseModel):
    name: str
    url: str
    feed_type: str = "rss"
    category: Optional[str] = None


class FeedUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    active: Optional[bool] = None


class FeedOut(BaseModel):
    id: int
    name: str
    url: str
    feed_type: str
    category: Optional[str] = None
    active: bool
    last_fetched: Optional[datetime] = None
    created_at: datetime
    article_count: int = 0

    model_config = {"from_attributes": True}


# ─── articles ────────────────────────────────────────────────────────────────

class ArticleOut(BaseModel):
    id: int
    feed_id: int
    feed_name: Optional[str] = None
    feed_type: Optional[str] = None
    title: str
    url: str
    description: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    thumbnail: Optional[str] = None
    # From the signed-in reader's own score row.
    ai_score: Optional[float] = None
    ai_summary: Optional[str] = None
    ai_tags: Optional[List[str]] = None
    ai_filtered: bool = False
    # From the signed-in reader's own state row.
    read_later: bool = False
    is_read: bool = False
    user_rating: Optional[str] = None
    created_at: datetime


class ArticleListResponse(BaseModel):
    items: List[ArticleOut]
    total: int
    page: int
    per_page: int


class SummaryOut(BaseModel):
    article_id: int
    key_points: List[str]
    why_it_matters: Optional[str] = None
    reading_time_min: Optional[int] = None
    cached: bool = False
    generated_at: Optional[datetime] = None


class RefreshResult(BaseModel):
    new_articles: int
    scored: int
    deferred: int
    message: str


# ─── profile & settings ──────────────────────────────────────────────────────

class UserProfileOut(BaseModel):
    interests: Optional[List[str]] = None
    min_score_threshold: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    interests: Optional[List[str]] = None
    min_score_threshold: Optional[float] = None


class AppSettingsOut(BaseModel):
    auto_refresh_enabled: bool
    refresh_interval_minutes: int
    last_auto_refresh_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AppSettingsUpdate(BaseModel):
    auto_refresh_enabled: Optional[bool] = None
    refresh_interval_minutes: Optional[int] = None


# ─── stats & blocks ──────────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total_articles: int
    unread_articles: int
    read_later_count: int
    total_feeds: int
    active_feeds: int
    avg_score: Optional[float] = None
    articles_today: int
    unscored_articles: int = 0


class BlockCreate(BaseModel):
    block_type: str
    value: str


class BlockOut(BaseModel):
    id: int
    block_type: str
    value: str

    model_config = {"from_attributes": True}


# ─── suggestions ─────────────────────────────────────────────────────────────

class SuggestionCreate(BaseModel):
    message: str = Field(min_length=3, max_length=4000)


class SuggestionOut(BaseModel):
    id: int
    message: str
    emailed: bool
    resolved: bool
    created_at: datetime
    author_name: Optional[str] = None
    author_email: Optional[str] = None
