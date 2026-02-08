"""Web Search Agent — find a person's important academic / professional titles.

Flow:  search (ddgs) → visit each result page → extract text → LLM summarize.

Standalone usage
----------------
::

    python -m citecontext.titlesearch "Andrew Yao" "Minyi Guo" \\
        --api_base "https://..." \\
        --api_key  "sk-..." \\
        --model    "deepseek-v3-1-250821"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

from .cache import CacheConfig, JsonDiskCache
from .llm import LLMClient, LLMConfig
from .progress import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TitleSearchConfig:
    """Configuration for the title search agent."""

    api_base: str
    api_key: str
    model: str
    cache_dir: str = os.path.join(".cache", "titlesearch")
    num_search_results: int = 5
    max_page_chars: int = 3000
    llm_timeout_sec: float = 300.0
    fetch_timeout_sec: float = 15.0


# ---------------------------------------------------------------------------
# Search — uses the `ddgs` package (DuckDuckGo / Bing backend)
# ---------------------------------------------------------------------------


def _ddgs_search(query: str, *, max_results: int = 5) -> list[dict[str, str]]:
    """Return search results as [{title, href, body}, …]."""
    try:
        from ddgs import DDGS  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "ddgs is required for web search.\n"
            "Install it with:  pip install ddgs"
        ) from None

    results: list[dict[str, str]] = []
    try:
        for r in DDGS().text(query, max_results=max_results):
            results.append(
                {
                    "title": r.get("title", ""),
                    "href": r.get("href", ""),
                    "body": r.get("body", ""),
                }
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] search failed for {query!r}: {exc}", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Page fetcher — visit a URL and extract readable text
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}


def _fetch_page_text(url: str, *, timeout: float = 15.0, max_chars: int = 3000) -> str:
    """Fetch *url*, strip boilerplate HTML, return clean text (up to *max_chars*)."""
    try:
        import requests  # type: ignore[import-untyped]
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "requests and beautifulsoup4 are required.\n"
            "Install with:  pip install requests beautifulsoup4"
        ) from None

    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"    [warn] fetch failed {url}: {exc}", file=sys.stderr)
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(
        ["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]
    ):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)[:max_chars]


# ---------------------------------------------------------------------------
# Search + visit pages
# ---------------------------------------------------------------------------


def _search_and_read(
    name: str,
    *,
    num_results: int = 5,
    max_page_chars: int = 3000,
    fetch_timeout: float = 15.0,
) -> list[dict[str, str]]:
    """Search for *name*, visit top pages, return [{url, text}, …]."""
    queries = [
        f'"{name}" professor university',
        f'"{name}" fellow OR homepage OR "google scholar"',
    ]
    seen: set[str] = set()
    pages: list[dict[str, str]] = []

    for q in queries:
        print(f"  [search] {q}", file=sys.stderr)
        hits = _ddgs_search(q, max_results=num_results)
        for h in hits:
            url = h.get("href", "")
            if not url or url in seen:
                continue
            seen.add(url)
            print(f"    -> visiting: {url}", file=sys.stderr)
            text = _fetch_page_text(url, timeout=fetch_timeout, max_chars=max_page_chars)
            if text:
                pages.append({"url": url, "text": text})
        time.sleep(1.0)

    return pages


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert at identifying notable academic and professional titles.

The user will provide the full text extracted from several web pages about a person.
Write a SHORT summary (1–2 sentences, ideally under 120 chars) listing ONLY their \
most impressive / noteworthy titles.

Include things like:
- Institutional affiliation & academic rank  (e.g. "Professor at Stanford")
- Lab / centre leadership  (e.g. "Director of XXX Lab")
- Society fellowships  (e.g. "ACM Fellow, IEEE Fellow")
- Academy memberships  (e.g. "Member of Chinese Academy of Sciences")
- Major awards  (e.g. "Turing Award laureate")

Rules:
- Output ONLY the summary text — no JSON, no markdown, no preamble.
- Be concise: drop generic info, keep only the impressive stuff.
- If nothing notable is found, output exactly: unknown
- Use English.
"""


def _build_user_prompt(name: str, pages: list[dict[str, str]]) -> str:
    parts = [f"Summarize the notable titles for: {name}\n"]
    for i, p in enumerate(pages, 1):
        parts.append(f"--- Page {i}: {p['url']} ---")
        parts.append(p["text"])
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class TitleSearchAgent:
    """Search → visit pages → LLM summarize titles."""

    def __init__(self, cfg: TitleSearchConfig):
        self.cfg = cfg
        self._llm = LLMClient(
            LLMConfig(
                api_base=cfg.api_base,
                api_key=cfg.api_key,
                model=cfg.model,
                timeout_sec=cfg.llm_timeout_sec,
            )
        )
        self._cache = JsonDiskCache(
            CacheConfig(cache_dir=cfg.cache_dir, ttl_hours=24 * 7)
        )

    def search_titles(self, name: str) -> str:
        """Search for a person's titles.  Returns a short summary string."""
        cache_key = hashlib.sha256(
            f"titlesearch:v5:{name.strip().lower()}".encode()
        ).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            print(f"  [titlesearch] cache hit: {name}", file=sys.stderr)
            return str(cached)

        print(f"  [titlesearch] ===== {name} =====", file=sys.stderr)
        pages = _search_and_read(
            name,
            num_results=self.cfg.num_search_results,
            max_page_chars=self.cfg.max_page_chars,
            fetch_timeout=self.cfg.fetch_timeout_sec,
        )

        if not pages:
            print(f"  [titlesearch] no pages found for {name}", file=sys.stderr)
            self._cache.set(cache_key, "unknown")
            return "unknown"

        print(
            f"  [titlesearch] read {len(pages)} pages, calling LLM ({self.cfg.model}) …",
            file=sys.stderr,
        )
        user_prompt = _build_user_prompt(name, pages)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        summary = self._llm.chat(messages, temperature=0.1)
        summary = summary.strip().strip('"').strip()
        if not summary:
            summary = "unknown"

        self._cache.set(cache_key, summary)
        return summary

    def batch_search(self, names: list[str]) -> dict[str, str]:
        """Search titles for multiple people.  Returns ``{name: summary}``."""
        results: dict[str, str] = {}
        unique = list(dict.fromkeys(n.strip() for n in names if n.strip()))
        for name in tqdm(unique, total=len(unique), desc="Title search"):
            print(f"\n  {name}", file=sys.stderr)
            results[name] = self.search_titles(name)
        return results


# ---------------------------------------------------------------------------
# Pipeline enrichment helper
# ---------------------------------------------------------------------------


def enrich_records(
    records: list[dict[str, Any]],
    cfg: TitleSearchConfig,
) -> list[dict[str, Any]]:
    """Enrich citation records: fill ``citing_earliest_author_title_sum`` with a summary."""
    agent = TitleSearchAgent(cfg)

    names = list(
        dict.fromkeys(
            ((r.get("citing_earliest_author") or {}).get("name") or "").strip()
            for r in records
            if ((r.get("citing_earliest_author") or {}).get("name") or "").strip()
        )
    )
    if not names:
        return records

    print(
        f"\n=== Title Search: enriching {len(names)} unique authors ===",
        file=sys.stderr,
    )
    title_map = agent.batch_search(names)

    for r in records:
        author = ((r.get("citing_earliest_author") or {}).get("name") or "").strip()
        if author and author in title_map:
            r["citing_earliest_author_title_sum"] = title_map[author]

    return records


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------


def _cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="titlesearch",
        description=(
            "Search for a person's important academic / professional titles "
            "using web search + page reading + LLM."
        ),
    )
    parser.add_argument("names", nargs="+", help="Person name(s) to search.")
    parser.add_argument(
        "--api_base", type=str, required=True, help="OpenAI-compatible API base URL."
    )
    parser.add_argument("--api_key", type=str, required=True, help="API key.")
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-v3-1-250821",
        help="Model name (default: deepseek-v3-1-250821).",
    )
    parser.add_argument(
        "--cache_dir",
        type=str,
        default=os.path.join(".cache", "titlesearch"),
    )
    parser.add_argument("--num_search_results", type=int, default=5)
    parser.add_argument("--max_page_chars", type=int, default=3000)
    parser.add_argument(
        "--output", type=str, default=None, help="Output JSON file (default: stdout)."
    )
    args = parser.parse_args(argv)

    cfg = TitleSearchConfig(
        api_base=args.api_base,
        api_key=args.api_key,
        model=args.model,
        cache_dir=args.cache_dir,
        num_search_results=args.num_search_results,
        max_page_chars=args.max_page_chars,
    )

    agent = TitleSearchAgent(cfg)
    results: dict[str, str] = {}
    for name in args.names:
        summary = agent.search_titles(name)
        results[name] = summary
        print(f"\n  => {name}: {summary}", file=sys.stderr)

    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n  Results written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
