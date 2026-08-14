from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Integer, String, Text, Boolean, Float, DateTime, ForeignKey, func, text,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    picture: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile", back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class AllowedEmail(Base):
    """Invite list. Sign-in is refused for addresses that are not here."""

    __tablename__ = "allowed_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppSettings(Base):
    """Instance-wide settings (single row, id=1). Admin-controlled."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auto_refresh_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    refresh_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=1440, server_default=text("1440"), nullable=False
    )
    last_auto_refresh_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Feed(Base):
    """Shared across the household — fetched once, scored per person."""

    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    feed_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="rss", server_default=text("'rss'")
    )
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    last_fetched: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    articles: Mapped[List["Article"]] = relationship(
        "Article", back_populates="feed", cascade="all, delete-orphan"
    )


class Article(Base):
    """The article itself. Nothing reader-specific lives here."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    feed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    # Deep summary of the article body. Cached once for everyone: it is
    # overwhelmingly the article's own content, not reader-specific.
    ai_full_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_full_summary_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    feed: Mapped["Feed"] = relationship("Feed", back_populates="articles")


class ArticleScore(Base):
    """One row per (article, reader). Relevance depends on whose interests."""

    __tablename__ = "article_scores"
    __table_args__ = (
        UniqueConstraint("article_id", "user_id", name="uq_article_scores_article_user"),
        Index("ix_article_scores_user_score", "user_id", "ai_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    ai_filtered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    ai_filter_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ArticleState(Base):
    """One row per (article, reader): saves, reads and ratings."""

    __tablename__ = "article_states"
    __table_args__ = (
        UniqueConstraint("article_id", "user_id", name="uq_article_states_article_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    read_later: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    open_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    user_rating: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FeedbackBlock(Base):
    __tablename__ = "feedback_blocks"
    __table_args__ = (
        UniqueConstraint("user_id", "block_type", "value", name="uq_blocks_user_type_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    interests: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True, default=list)
    min_score_threshold: Mapped[float] = mapped_column(
        Float, default=5.0, server_default=text("5.0"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="profile")


class Suggestion(Base):
    """Improvement suggestions from members; emailed to the owner."""

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    emailed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    email_error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")
