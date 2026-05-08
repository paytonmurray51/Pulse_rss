import json
import logging
import re

import anthropic

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic()

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

    try:
        response = _client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

        return json.loads(raw)
    except Exception as e:
        logger.error(f"Claude scoring error: {e}")
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

        scores = await score_articles(payload, interests, feedback_ctx)

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
