"""
Google Gemini via the Generative Language REST API.

Matches the curl pattern from Google AI Studio:
  POST .../v1beta/models/{model}:generateContent
  Header: X-goog-api-key
"""

from __future__ import annotations

import json
import logging

import requests

from llm import config

log = logging.getLogger(__name__)


def _url() -> str:
    return f"{config.GEMINI_API_BASE}/models/{config.GEMINI_MODEL}:generateContent"


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-goog-api-key": config.GEMINI_API_KEY,
    }


def generate(
    *,
    user_text: str,
    system_text: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    """Single-turn generateContent call. Returns assistant text."""
    from llm.env_validate import is_gemini_placeholder

    if is_gemini_placeholder(config.GEMINI_API_KEY):
        raise RuntimeError(
            "GEMINI_API_KEY is not set in .env (or is still a placeholder)"
        )

    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"temperature": temperature},
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    resp = requests.post(_url(), headers=_headers(), json=payload, timeout=120)
    if not resp.ok:
        log.error("Gemini API %s: %s", resp.status_code, resp.text[:500])
        hint = ""
        if resp.status_code == 429 and "gemini-2.0" in config.GEMINI_MODEL:
            hint = (
                " Free-tier quota for gemini-2.0-flash is often exhausted; "
                "set GEMINI_MODEL=gemini-2.5-flash in .env and retry."
            )
        raise RuntimeError(
            f"Gemini API error {resp.status_code}: {resp.text[:200]}{hint}"
        )

    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if "text" in p)
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response: {data!r}") from e

    if json_mode:
        json.loads(text)  # validate before returning

    return text
