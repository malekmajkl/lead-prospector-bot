---
name: python-dev
description: >
  Python development rules and standards for this project. Apply these rules whenever writing,
  editing, or reviewing Python code. Triggers include: creating a new Python script, refactoring
  existing code, fixing bugs, adding features to run_local.py or any other .py file, or any
  request involving Python code quality, structure, or best practices.
---

# Python Development Rules

Standards and patterns to follow for all Python code in this project.

---

## 1. Project Structure

Every Python project or standalone script must have:

```
project/
├── .env                  # secrets — never commit
├── .env.example          # template with placeholder values — commit this
├── requirements.txt      # pinned dependencies
├── run_local.py          # main entry point
├── logs/                 # runtime logs (gitignored)
└── output/               # generated files (gitignored)
```

For new scripts > 200 lines, split into modules:
```
project/
├── main.py               # entry point only — arg parsing + call core
├── core/
│   ├── __init__.py
│   ├── pipeline.py       # business logic
│   └── utils.py          # shared helpers
└── tests/
    └── test_pipeline.py
```

---

## 2. Dependencies

Always maintain `requirements.txt` with **pinned versions**:

```
anthropic==0.49.0
gspread==6.1.2
google-auth==2.29.0
google-api-python-client==2.128.0
google-auth-httplib2==0.2.0
google-auth-oauthlib==1.2.1
openpyxl==3.1.2
requests==2.32.3
```

To generate: `pip3 freeze > requirements.txt`
To install: `pip3 install -r requirements.txt`

**Never** install dependencies inline inside the script. All installs belong in `requirements.txt` + `start.sh`.

---

## 3. Environment Variables

- All secrets and config go in `.env` — never hardcode tokens, keys, or IDs in source code
- Load with a dedicated `load_env()` function at module top
- Document every variable in `.env.example` with a placeholder value and a comment
- Validate required vars at startup and exit early with a clear error:

```python
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

missing = [k for k, v in [("TELEGRAM_TOKEN", TOKEN), ("ANTHROPIC_API_KEY", API_KEY)] if not v]
if missing:
    for k in missing:
        print(f"❌ {k} is missing from .env")
    sys.exit(1)
```

---

## 4. Code Style

### Formatting
- Follow **PEP 8**: 4-space indent, max 100 chars per line
- Use `ruff` for linting: `pip3 install ruff && ruff check .`
- Use `black` for formatting: `pip3 install black && black .`

### Naming
- `snake_case` for functions, variables, modules
- `UPPER_SNAKE_CASE` for module-level constants
- `PascalCase` for classes
- Prefix internal helpers with `_`: `_score_fallback()`, `_draft_fallback()`

### Type hints
Add type hints to all function signatures:

```python
def research_leads(role: str, region: str, count: int,
                   exclude_municipalities: list[str] | None = None) -> list[dict]:
```

Use `from __future__ import annotations` at top of file if on Python 3.9.

### Imports
Order: stdlib → third-party → local. One blank line between groups. No wildcard imports.

```python
import os
import sys
import json

import anthropic
import gspread

from core.utils import load_env
```

---

## 5. Functions

- One function = one responsibility
- Max ~40 lines per function — if longer, extract helpers
- Return early instead of deep nesting:

```python
# bad
def save(lead):
    if email:
        if not duplicate:
            append_row(lead)

# good
def save(lead):
    if not lead.get("email"):
        return
    if is_duplicate(lead):
        return
    append_row(lead)
```

- Never define the same function twice — if you need a variant, rename it or use a parameter

---

## 6. Error Handling

- Catch specific exceptions, not bare `except:`
- Always log the error with context before returning a fallback
- Use `log.exception()` (not `log.error()`) when you want the full traceback

```python
# bad
try:
    result = ws.get_all_records()
except:
    return []

# good
try:
    result = ws.get_all_records()
except gspread.exceptions.APIError as e:
    log.error(f"Sheets API error in get_all_records: {e}")
    return []
except Exception as e:
    log.exception(f"Unexpected error reading sheet: {e}")
    return []
```

For retries (e.g. API rate limits), use a helper:

```python
def with_retry(fn, retries: int = 3, base_wait: int = 65):
    for attempt in range(retries):
        try:
            return fn()
        except anthropic.RateLimitError:
            wait = base_wait * (attempt + 1)
            log.warning(f"Rate limit — waiting {wait}s (attempt {attempt+1}/{retries})")
            time.sleep(wait)
    raise RuntimeError("All retries exhausted")
```

---

## 7. Logging

Use the stdlib `logging` module — never use bare `print()` in application code (only in CLI helpers/startup checks).

Standard setup:

```python
import logging

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)
```

Log levels:
- `log.debug()` — verbose detail (disabled in prod)
- `log.info()` — normal flow milestones ("Saved 5 leads to Sheets")
- `log.warning()` — recoverable issues ("Dedup skipped — Sheets not connected")
- `log.error()` — failures that affect output ("Draft failed for email@x.cz: ...")
- `log.exception()` — unexpected errors (includes traceback automatically)

---

## 8. JSON Handling

Always strip markdown fences before parsing Claude responses:

```python
import re

def parse_json_safe(raw: str) -> list | dict | None:
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
```

---

## 9. Claude API Usage

- Always specify the model explicitly — never rely on a default
- Use `claude-sonnet-4-6` (latest) unless a specific reason requires otherwise
- Use prompt caching for large, repeated system prompts (SKILL.md content):

```python
import anthropic

client = anthropic.Anthropic(api_key=API_KEY)

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2000,
    system=[
        {
            "type": "text",
            "text": skill_content,
            "cache_control": {"type": "ephemeral"},  # cache large system prompts
        }
    ],
    messages=[{"role": "user", "content": user_message}],
)
```

- Keep `max_tokens` tight — 2000 for JSON outputs, 4000 for email drafts, 1000 for short tasks
- Never pass user-controlled strings directly into `system` without sanitisation

---

## 10. Security

- Never commit `.env`, `service_account.json`, or `gmail_token.json` — add to `.gitignore`
- Never log full API keys or tokens (log only first 8 chars for debugging if needed)
- Validate and sanitise any user input before passing to shell commands or file paths
- Use `Path` objects (not string concatenation) for all file paths:

```python
from pathlib import Path

OUTPUT_DIR = Path("output")
log_file = Path("logs") / "bot.log"
```

---

## 11. Testing

For any function with logic (scoring, dedup, parsing), write a test in `tests/`:

```python
# tests/test_scoring.py
from run_local import score_lead

def test_mayor_large_city_scores_high():
    lead = {
        "role": "starosta", "municipality": "zlín",
        "email": "novak@zlin.eu", "phone": "+420123456789",
        "contact_name": "Jan Novák", "source_url": "https://zlin.eu"
    }
    score, tier = score_lead(lead)
    assert score >= 75
    assert "High" in tier

def test_missing_email_reduces_score():
    lead = {"role": "starosta", "municipality": "zlín",
            "email": None, "phone": None,
            "contact_name": "Jan Novák", "source_url": "https://zlin.eu"}
    score, _ = score_lead(lead)
    assert score < 60
```

Run with: `python3 -m pytest tests/ -v`

---

## 12. Git Hygiene

`.gitignore` must include:
```
.env
gmail_token.json
service_account.json
output/
logs/
__pycache__/
*.pyc
.DS_Store
```

Commit messages: imperative mood, short (`Add lead dedup before Sheets sync`, not `added deduplication functionality to the pipeline`).
