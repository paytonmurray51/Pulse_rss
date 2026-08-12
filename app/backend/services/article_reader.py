import logging
import re
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Text inside these never belongs to the article body. Without skipping them,
# script and style contents end up in the prompt as noise.
SKIP_TAGS = {
    "script", "style", "noscript", "svg", "iframe", "form", "button",
    "nav", "header", "footer", "aside", "select", "textarea",
    "title",  # passed to the model separately; no need to duplicate it
}

# Below this, extraction almost certainly hit a paywall stub, a consent wall,
# or a JS-rendered shell — summarizing it would produce confident nonsense.
MIN_USABLE_CHARS = 600

# Caps prompt cost on very long pages. ~20k chars is roughly 5k tokens.
MAX_CHARS = 20_000


class _ArticleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            chunk = data.strip()
            if chunk:
                self._parts.append(chunk)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()


class ArticleUnreadable(Exception):
    """Raised when the page cannot be turned into usable article text."""


async def fetch_article_text(url: str) -> tuple[str, int]:
    """Fetch a URL and extract its readable text.

    Returns (text, word_count). Raises ArticleUnreadable with a
    user-facing message when extraction fails or yields too little to
    summarize honestly.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type and "text/" not in content_type:
                raise ArticleUnreadable(
                    f"This link is {content_type or 'a non-text file'}, not a readable article."
                )
            html = resp.text
    except httpx.HTTPStatusError as e:
        raise ArticleUnreadable(
            f"The site returned HTTP {e.response.status_code}. It may be paywalled or blocking automated reads."
        )
    except httpx.RequestError as e:
        raise ArticleUnreadable(f"Could not reach the site: {type(e).__name__}.")

    parser = _ArticleTextParser()
    try:
        parser.feed(html)
    except Exception as e:
        raise ArticleUnreadable(f"Could not parse the page: {e}")

    text = parser.get_text()
    if len(text) < MIN_USABLE_CHARS:
        raise ArticleUnreadable(
            "Only a fragment of this page could be read — it is most likely paywalled "
            "or rendered with JavaScript. Open the original instead."
        )

    return text[:MAX_CHARS], len(text.split())
