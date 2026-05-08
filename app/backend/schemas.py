from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# Feed schemas
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


# Article schemas
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
    ai_score: Optional[float] = None
    ai_summary: Optional[str] = None
    ai_tags: Optional[List[str]] = None
    ai_filtered: bool = False
    read_later: bool = False
    is_read: bool = False
    user_rating: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArticleListResponse(BaseModel):
    items: List[ArticleOut]
    total: int
    page: int
    per_page: int


# UserProfile schemas
class UserProfileOut(BaseModel):
    interests: Optional[List[str]] = None
    min_score_threshold: float
    refresh_interval_minutes: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    interests: Optional[List[str]] = None
    min_score_threshold: Optional[float] = None
    refresh_interval_minutes: Optional[int] = None


# Stats schema
class StatsOut(BaseModel):
    total_articles: int
    unread_articles: int
    read_later_count: int
    total_feeds: int
    active_feeds: int
    avg_score: Optional[float] = None
    articles_today: int


# Block schemas
class BlockCreate(BaseModel):
    block_type: str
    value: str


class BlockOut(BaseModel):
    id: int
    block_type: str
    value: str

    model_config = {"from_attributes": True}
