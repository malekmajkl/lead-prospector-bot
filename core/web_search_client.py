from __future__ import annotations

import logging

from core.config import SEARCH_PROVIDER, SERPAPI_KEY

log = logging.getLogger(__name__)


def web_search(query: str, num_results: int = 8) -> str:
    if SEARCH_PROVIDER == "serpapi":
        return _serpapi(query, num_results)
    return _duckduckgo(query, num_results)


def _duckduckgo(query: str, n: int) -> str:
    from duckduckgo_search import DDGS
    results = list(DDGS().text(query, max_results=n))
    log.info(f"DDG search '{query}': {len(results)} results")
    lines = [f"[{r['title']}] {r['href']}\n{r['body']}" for r in results]
    return "\n\n".join(lines)


def _serpapi(query: str, n: int) -> str:
    import requests
    params = {"q": query, "api_key": SERPAPI_KEY, "num": n, "hl": "cs", "gl": "cz"}
    data = requests.get("https://serpapi.com/search", params=params, timeout=15).json()
    results = data.get("organic_results", [])
    log.info(f"SerpAPI search '{query}': {len(results)} results")
    lines = [
        f"[{r.get('title', '')}] {r.get('link', '')}\n{r.get('snippet', '')}"
        for r in results
    ]
    return "\n\n".join(lines)
