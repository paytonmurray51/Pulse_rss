import asyncio
import functools
import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

import feedparser
import httpx

logger = logging.getLogger(__name__)

# Some publishers reject the default python-feedparser agent outright.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    parser = _HTMLStripper()
    try:
        parser.feed(html)
        return parser.get_text().strip()
    except Exception:
        return html


def _extract_thumbnail(entry, feed_type: str) -> Optional[str]:
    # Try media_thumbnail
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")

    # Try enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image/"):
                return enc.get("href") or enc.get("url")

    # Try media_content
    if hasattr(entry, "media_content") and entry.media_content:
        for mc in entry.media_content:
            if mc.get("medium") == "image" or mc.get("type", "").startswith("image/"):
                return mc.get("url")

    # YouTube fallback
    if feed_type == "youtube":
        url = getattr(entry, "link", "") or getattr(entry, "id", "")
        video_id = _extract_youtube_video_id(url)
        if video_id:
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    return None


def _extract_youtube_video_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
        r"watch\?.*v=([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _parse_published(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _parse_entries(parsed_feed, feed_type: str) -> list[dict]:
    results = []
    for entry in parsed_feed.entries[:50]:
        url = getattr(entry, "link", None) or getattr(entry, "id", None)
        if not url:
            continue

        # Description
        description = ""
        if hasattr(entry, "content") and entry.content:
            description = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            description = entry.summary or ""
        description = _strip_html(description)[:2000]

        results.append({
            "title": getattr(entry, "title", "Untitled"),
            "url": url,
            "description": description,
            "author": getattr(entry, "author", None),
            "published_at": _parse_published(entry),
            "thumbnail": _extract_thumbnail(entry, feed_type),
        })
    return results


async def fetch_feed(feed) -> list[dict]:
    """Fetch and parse one feed, returning [] on any failure.

    feedparser does not raise on network or parse errors — it reports them via
    the `bozo` flag and an HTTP `status`. Without checking both, a dead URL is
    indistinguishable from a feed that simply has no new items, so every
    failure path here logs why.
    """
    loop = asyncio.get_event_loop()
    try:
        parsed = await loop.run_in_executor(
            None, functools.partial(feedparser.parse, feed.url, agent=USER_AGENT)
        )
    except Exception as e:
        logger.error("Feed %s (%s) raised while fetching: %s", feed.name, feed.url, e)
        return []

    status = getattr(parsed, "status", None)
    if status is not None and status >= 400:
        logger.warning("Feed %s (%s) returned HTTP %s", feed.name, feed.url, status)
        return []

    # bozo is also set for feeds with harmless XML quirks that still parse, so
    # only treat it as fatal when nothing came back.
    if getattr(parsed, "bozo", False) and not parsed.entries:
        logger.warning(
            "Feed %s (%s) could not be parsed: %r",
            feed.name, feed.url, getattr(parsed, "bozo_exception", None),
        )
        return []

    entries = _parse_entries(parsed, feed.feed_type)
    logger.info("Feed %s: %d entries fetched", feed.name, len(entries))
    return entries


def detect_feed_type(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if "youtube.com" in hostname or "youtu.be" in hostname:
        return "youtube"
    return "rss"


async def resolve_youtube_channel_to_feed_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path

    # Already an RSS feed URL
    if "feeds/videos.xml" in url:
        return url

    # /channel/{id}
    channel_match = re.match(r"/channel/([a-zA-Z0-9_-]+)", path)
    if channel_match:
        channel_id = channel_match.group(1)
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # /@handle or /user/name
    handle_match = re.match(r"/(@[^/]+|user/[^/]+|c/[^/]+)", path)
    if handle_match:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
                match = re.search(r'"channelId"\s*:\s*"([a-zA-Z0-9_-]+)"', html)
                if match:
                    channel_id = match.group(1)
                    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            except Exception as e:
                logger.error(f"Failed to resolve YouTube handle {url}: {e}")
                raise ValueError(
                    f"Could not resolve YouTube channel from URL: {url}. "
                    "Please use the direct /channel/{{id}} URL instead."
                )

    raise ValueError(
        f"Unrecognized YouTube URL format: {url}. "
        "Use /channel/{{id}} or /@handle format."
    )
