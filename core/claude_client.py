from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import anthropic

from core.config import API_KEY, SKILLS_DIR, LLM_PROVIDER, LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL

log = logging.getLogger(__name__)


def load_skill(name: str) -> str:
    candidates = [
        SKILLS_DIR / name / "SKILL.md",
        Path(__file__).parent.parent / "skills" / name / "SKILL.md",
        Path.home() / ".openclaw" / "workspace" / "skills" / name / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            log.info(f"Loaded skill: {name} ({path})")
            return path.read_text(encoding="utf-8")
    log.warning(f"Skill '{name}' not found — using built-in fallback")
    return ""


def call_claude(system: str, user_message: str,
                tools: list | None = None, max_tokens: int = 2000) -> str:
    client = anthropic.Anthropic(api_key=API_KEY)
    kwargs: dict = dict(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    if tools:
        kwargs["tools"] = tools
    for attempt in range(3):
        try:
            response = client.messages.create(**kwargs)
            return "".join(b.text for b in response.content if hasattr(b, "text")).strip()
        except anthropic.RateLimitError:
            wait = 65 * (attempt + 1)
            log.warning(f"Rate limit — waiting {wait}s (attempt {attempt + 1}/3)")
            time.sleep(wait)
        except Exception as e:
            log.exception(f"Claude API error: {e}")
            raise
    log.error("Rate limit — all retries exhausted")
    return ""


def call_llm(system: str, user_message: str,
             tools: list | None = None, max_tokens: int = 2000) -> str:
    if LLM_PROVIDER == "local":
        return _call_ollama(system, user_message, max_tokens)
    return call_claude(system, user_message, tools=tools, max_tokens=max_tokens)


def _call_ollama(system: str, user_message: str, max_tokens: int = 2000) -> str:
    import openai
    client = openai.OpenAI(base_url=LOCAL_LLM_BASE_URL, api_key="ollama")
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=LOCAL_LLM_MODEL,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_message},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"Ollama attempt {attempt + 1}/3 failed: {e}")
            if attempt == 2:
                raise
    return ""


def parse_json_response(raw: str) -> list | dict | None:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"JSON parse failed: {e} | raw[:200]: {raw[:200]}")
        return None
