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


# A channel ID is always "UC" followed by 22 more characters.
_CHANNEL_ID = r"(UC[A-Za-z0-9_-]{22})"

# Ordered by trustworthiness. The channel page advertises its own RSS feed,
# which is precisely what we want. The JSON blobs near the bottom also name
# every *other* channel appearing on the page — a recommended video's author
# would resolve to the wrong feed — so they are last resorts.
_CHANNEL_ID_PATTERNS = (
    rf'rel="alternate"[^>]*?channel_id={_CHANNEL_ID}',
    rf'feeds/videos\.xml\?channel_id={_CHANNEL_ID}',
    rf'<meta[^>]*?itemprop="(?:identifier|channelId)"[^>]*?content="{_CHANNEL_ID}"',
    rf'<link[^>]*?rel="canonical"[^>]*?/channel/{_CHANNEL_ID}',
    rf'"externalId"\s*:\s*"{_CHANNEL_ID}"',
    rf'"channelId"\s*:\s*"{_CHANNEL_ID}"',
)


def _feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def extract_channel_id(html: str) -> Optional[str]:
    for pattern in _CHANNEL_ID_PATTERNS:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


async def resolve_youtube_channel_to_feed_url(url: str) -> str:
    """Turn any YouTube channel URL into its RSS feed URL.

    Handles are resolved by fetching the page and reading the channel ID out
    of it, since YouTube exposes no public lookup. Each failure mode reports
    what actually went wrong: a page we could not fetch, a page we could not
    read, and a URL that was never a channel are three different problems.
    """
    path = urlparse(url).path

    if "feeds/videos.xml" in url:
        return url

    direct = re.match(rf"/channel/{_CHANNEL_ID}", path)
    if direct:
        return _feed_url(direct.group(1))

    # @handle, legacy /c/ and /user/ vanity paths, and the bare /Name form.
    if not re.match(r"/(@[^/]+|c/[^/]+|user/[^/]+|[A-Za-z0-9_.-]+)/?$", path):
        raise ValueError(
            f"That does not look like a YouTube channel URL: {url}. "
            "Use the channel's main page, e.g. https://www.youtube.com/@SomeChannel"
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        logger.error("YouTube returned %s for %s", e.response.status_code, url)
        raise ValueError(
            f"YouTube returned HTTP {e.response.status_code} for that channel. "
            "Check the URL, or paste the channel's RSS feed directly: "
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC..."
        )
    except Exception as e:
        logger.error("Could not fetch %s: %s", url, e)
        raise ValueError(
            f"Could not reach YouTube to look up that channel ({type(e).__name__}). "
            "Try again, or paste the channel's RSS feed directly: "
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC..."
        )

    channel_id = extract_channel_id(html)
    if channel_id:
        logger.info("Resolved %s to channel %s", url, channel_id)
        return _feed_url(channel_id)

    logger.error("Fetched %s (%d bytes) but found no channel ID", url, len(html))
    raise ValueError(
        "Found that YouTube page but couldn't read its channel ID — YouTube may have "
        "served a consent or bot-check page. Open the channel in a browser, view the "
        "page source, search for 'channel_id=', and paste the full feed URL: "
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC..."
    )
