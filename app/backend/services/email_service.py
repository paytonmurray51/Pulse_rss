import html
import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_ENDPOINT = "https://api.resend.com/emails"

# Resend permits onboarding@resend.dev without domain verification, which is
# enough to reach your own address. Set RESEND_FROM once a domain is verified.
RESEND_FROM = os.environ.get("RESEND_FROM", "Pulse <onboarding@resend.dev>")
OWNER_EMAIL = (os.environ.get("OWNER_EMAIL") or "").strip()


class EmailNotConfigured(Exception):
    pass


def email_configured() -> bool:
    return bool(RESEND_API_KEY and OWNER_EMAIL)


async def send_suggestion_email(author_name: str, author_email: str, message: str) -> None:
    """Email one suggestion to the instance owner.

    Raises on failure so the caller can record why, rather than silently
    dropping feedback someone took the trouble to write.
    """
    if not email_configured():
        missing = "RESEND_API_KEY" if not RESEND_API_KEY else "OWNER_EMAIL"
        raise EmailNotConfigured(f"{missing} is not set")

    safe_message = html.escape(message).replace("\n", "<br>")
    safe_name = html.escape(author_name or author_email)
    safe_email = html.escape(author_email)

    body = f"""
    <div style="font-family:system-ui,sans-serif;max-width:520px">
      <p style="color:#666;font-size:13px;margin:0 0 4px">Pulse suggestion</p>
      <p style="margin:0 0 16px"><strong>{safe_name}</strong>
         &lt;{safe_email}&gt;</p>
      <div style="border-left:3px solid #e5e5e5;padding-left:14px;
                  font-size:15px;line-height:1.6">{safe_message}</div>
    </div>
    """

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_FROM,
                "to": [OWNER_EMAIL],
                "reply_to": author_email,
                "subject": f"Pulse suggestion from {author_name or author_email}",
                "html": body,
            },
        )

    if resp.status_code >= 300:
        detail = resp.text[:300]
        logger.error("Resend rejected the message: %s %s", resp.status_code, detail)
        raise RuntimeError(f"Resend returned {resp.status_code}: {detail}")

    logger.info("Suggestion emailed to owner on behalf of %s", author_email)
