import json
import logging
import re

import anthropic

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic()


class ClaudeUnavailable(Exception):
    """The Anthropic API refused the request or could not be reached.

    Distinct from a malformed response: this means no usable answer exists
    yet, so the caller should retry later rather than persist a fallback.
    """


def explain_anthropic_error(exc: Exception) -> str:
    """Turn an SDK exception into something actionable for a human.

    A generic 'try again' is actively misleading for billing and auth
    failures, where retrying can never succeed.
    """
    message = str(exc)
    lowered = message.lower()

    if "credit balance is too low" in lowered or "plans & billing" in lowered:
        return (
            "Anthropic credit balance is too low. Add credits at "
            "console.anthropic.com under Plans & Billing."
        )

    status = (
        getattr(getattr(exc, "response", None), "status_code", None)
        or getattr(exc, "status_code", None)
    )
    if status == 401:
        return "ANTHROPIC_API_KEY was rejected — it may be invalid or revoked."
    if status == 403:
        return "The Anthropic API key lacks permission for this model."
    if status == 429:
        return "Rate limited by the Anthropic API. Try again in a minute."
    if status in (500, 502, 503, 529):
        return "The Anthropic API is temporarily unavailable. Try again shortly."

    return f"Anthropic API error: {message}"

SYSTEM_PROMPT = """You are a personal content curator. For each article provided, score and evaluate it.

You MUST respond ONLY with a valid JSON array — no markdown, no code fences, no explanation.

For each article in the input array, output an object with these fields:
- index (int): same index from input
- relevance_score (float 0-10): how relevant to the user's interests
- quality_score (float 0-10): content quality, depth, originality
- combined_score (float 0-10): relevance * 0.6 + quality * 0.4
- filter (bool): true if content should be hidden (spam, clickbait, irrelevant)
- filter_reason (string or null): brief reason if filtered
- summary (string): 1-2 sentence TL;DR of the article
- tags (array of 2-4 strings): topic tags

Example output format:
[{"index":0,"relevance_score":8.5,"quality_score":7.0,"combined_score":7.9,"filter":false,"filter_reason":null,"summary":"Article about X.","tags":["tag1","tag2"]}]"""


SUMMARY_SYSTEM_PROMPT = """You summarize articles for a reader who wants the substance without opening the page.

Respond ONLY with a valid JSON object — no markdown, no code fences, no preamble.

Fields:
- key_points (array of 3-5 strings): the article's substantive claims. Each a full
  sentence carrying actual information — specific findings, numbers, arguments.
  Never write meta-descriptions like "the article discusses X".
- why_it_matters (string): one sentence connecting the article to the reader's
  stated interests. If it does not relate to them, say plainly what it is useful for.

Base every statement on the supplied text. If the text looks truncated or is
mostly navigation boilerplate, say so in key_points rather than inventing content.

Example:
{"key_points":["Go's explicit error handling makes generated code easier to review.","Roughly a third of new Go at Google is now model-generated."],"why_it_matters":"Relevant if you run Go services and are weighing AI-assisted work."}"""


async def summarize_article(title: str, text: str, interests: list[str]) -> dict:
    """Produce a structured deep summary of one article's body text."""
    interests_str = ", ".join(interests) if interests else "general technology"

    user_message = (
        f"Reader's interests: {interests_str}\n\n"
        f"Article title: {title}\n\n"
        f"Article text:\n{text}\n\n"
        "Respond with ONLY the JSON object."
    )

    response = _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1200,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()

    parsed = json.loads(raw)
    points = [p for p in parsed.get("key_points", []) if isinstance(p, str) and p.strip()]
    if not points:
        raise ValueError("Model returned no usable key points")

    return {
        "key_points": points,
        "why_it_matters": parsed.get("why_it_matters") or None,
    }


def _build_feedback_section(feedback_ctx: dict) -> str:
    lines = []

    liked = feedback_ctx.get("liked_titles", [])[:15]
    if liked:
        lines.append("User previously LIKED these (score higher):")
        for t in liked:
            lines.append(f"  - {t}")

    implicit_liked = feedback_ctx.get("implicit_liked_titles", [])[:10]
    if implicit_liked:
        lines.append("User implicitly liked (opened multiple times + saved):")
        for t in implicit_liked:
            lines.append(f"  - {t}")

    disliked = feedback_ctx.get("disliked_titles", [])[:10]
    if disliked:
        lines.append("User previously DISLIKED these (score lower):")
        for t in disliked:
            lines.append(f"  - {t}")

    blocked_topics = feedback_ctx.get("blocked_topics", [])
    if blocked_topics:
        lines.append("Blocked topics (filter anything similar):")
        for t in blocked_topics:
            lines.append(f"  - {t}")

    return "\n".join(lines)


async def score_articles(
    articles: list[dict],
    interests: list[str],
    feedback_ctx: dict,
) -> list[dict]:
    if not articles:
        return []

    interests_str = ", ".join(interests) if interests else "general tech and news"
    feedback_section = _build_feedback_section(feedback_ctx)

    user_message = f"""User interests: {interests_str}

{feedback_section}

Articles to evaluate:
{json.dumps(articles, ensure_ascii=False)}

Respond with ONLY the JSON array."""

    # A failed call means no answer exists yet — raise so the caller can defer
    # these articles instead of freezing a fabricated 5.0 into the database.
    try:
        response = _client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        raise ClaudeUnavailable(explain_anthropic_error(e)) from e

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    # A malformed reply is different: the model did answer, so neutral scores
    # are a fair fallback and the articles are genuinely done being tried.
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as e:
        logger.error("Could not parse scoring response, using neutral scores: %s", e)
        return [
            {
                "index": a["index"],
                "relevance_score": 5.0,
                "quality_score": 5.0,
                "combined_score": 5.0,
                "filter": False,
                "filter_reason": None,
                "summary": None,
                "tags": [],
            }
            for a in articles
        ]


async def process_new_articles(
    articles: list,
    interests: list[str],
    feedback_ctx: dict,
    batch_size: int = 10,
) -> dict:
    results: dict = {}

    for batch_start in range(0, len(articles), batch_size):
        batch = articles[batch_start: batch_start + batch_size]
        payload = [
            {
                "index": i,
                "title": a.title,
                "description": (a.description or "")[:500],
                "source": a.feed.name if a.feed else "",
                "type": a.feed.feed_type if a.feed else "rss",
            }
            for i, a in enumerate(batch)
        ]

        try:
            scores = await score_articles(payload, interests, feedback_ctx)
        except ClaudeUnavailable as e:
            # Whatever broke this batch will break the rest, so stop and
            # return what succeeded. Omitted articles stay unprocessed and
            # get retried on the next refresh.
            logger.error(
                "Scoring unavailable after %d/%d articles — deferring the rest: %s",
                len(results), len(articles), e,
            )
            break

        score_map = {s["index"]: s for s in scores}
        for i, article in enumerate(batch):
            score = score_map.get(i, {})
            results[article.url] = {
                "ai_score": score.get("combined_score", 5.0),
                "ai_summary": score.get("summary"),
                "ai_tags": score.get("tags", []),
                "ai_filtered": score.get("filter", False),
                "ai_filter_reason": score.get("filter_reason"),
                "ai_processed": True,
            }

    return results
