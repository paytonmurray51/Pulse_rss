from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Integer, String, Text, Boolean, Float, DateTime, ForeignKey, func
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    feed_type: Mapped[str] = mapped_column(String(50), nullable=False, default="rss")
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    articles: Mapped[List["Article"]] = relationship(
        "Article", back_populates="feed", cascade="all, delete-orphan"
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    feed_id: Mapped[int] = mapped_column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    ai_filtered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_filter_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ai_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    read_later: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_rating: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    feed: Mapped["Feed"] = relationship("Feed", back_populates="articles")


class FeedbackBlock(Base):
    __tablename__ = "feedback_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    block_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interests: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True, default=list)
    min_score_threshold: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    refresh_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
