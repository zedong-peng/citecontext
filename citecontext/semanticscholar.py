from __future__ import annotations

import hashlib
import json
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .cache import CacheConfig, JsonDiskCache, now_ts


GRAPH_BASE_URL = "https://api.semanticscholar.org/graph/v1"

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SemanticScholarClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        cache_dir: str,
        cache_ttl_hours: float | None,
        timeout_sec: float,
        min_interval_sec: float,
        max_retries: int,
    ):
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.min_interval_sec = max(0.0, min_interval_sec)
        self.max_retries = max(0, max_retries)
        self._last_request_ts = 0.0
        self._cache = JsonDiskCache(CacheConfig(cache_dir=cache_dir, ttl_hours=cache_ttl_hours))

    def _throttle(self) -> None:
        if self.min_interval_sec <= 0:
            return
        elapsed = now_ts() - self._last_request_ts
        sleep_for = self.min_interval_sec - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

    def _request_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{GRAPH_BASE_URL}{path}"
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        cache_key = _sha256(full_url)

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        attempt = 0
        backoff = 1.0
        while True:
            attempt += 1
            self._throttle()
            req = urllib.request.Request(full_url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)
                    self._cache.set(cache_key, data)
                    self._last_request_ts = now_ts()
                    return data
            except urllib.error.HTTPError as e:
                self._last_request_ts = now_ts()
                status = getattr(e, "code", None)
                if status == 429 or (status is not None and 500 <= status <= 599):
                    if attempt > self.max_retries:
                        raise RuntimeError(f"HTTP {status} after {attempt} attempts: {full_url}") from e
                    retry_after = e.headers.get("Retry-After") if hasattr(e, "headers") else None
                    if retry_after:
                        try:
                            sleep_sec = float(retry_after)
                        except Exception:  # noqa: BLE001
                            sleep_sec = backoff
                    else:
                        sleep_sec = backoff
                    sleep_sec = sleep_sec * (1.0 + random.random() * 0.2)
                    time.sleep(min(60.0, max(1.0, sleep_sec)))
                    backoff = min(60.0, backoff * 2.0)
                    continue
                raise RuntimeError(f"HTTP {status}: {full_url}") from e
            except urllib.error.URLError as e:
                self._last_request_ts = now_ts()
                if attempt > self.max_retries:
                    raise RuntimeError(f"Network error after {attempt} attempts: {full_url}") from e
                time.sleep(min(10.0, backoff))
                backoff = min(60.0, backoff * 2.0)
            except (TimeoutError, socket.timeout) as e:
                self._last_request_ts = now_ts()
                if attempt > self.max_retries:
                    raise RuntimeError(f"Timeout after {attempt} attempts: {full_url}") from e
                time.sleep(min(10.0, backoff))
                backoff = min(60.0, backoff * 2.0)

    def resolve_author(self, name: str, *, affiliation_keyword: str | None, strict: bool) -> dict[str, Any]:
        data = self._request_json(
            "/author/search",
            {
                "query": name,
                "limit": 10,
                "fields": "name,authorId,affiliations,paperCount,citationCount,hIndex",
            },
        )
        candidates = data.get("data") or []
        if not candidates:
            raise RuntimeError(f"No author found for name={name!r}")

        def score(c: dict) -> float:
            s = 0.0
            s += float(c.get("paperCount") or 0) / 1000.0
            s += float(c.get("citationCount") or 0) / 1_000_000.0
            s += float(c.get("hIndex") or 0) / 1000.0
            if affiliation_keyword:
                affs = " ".join(c.get("affiliations") or [])
                if affiliation_keyword.lower() in affs.lower():
                    s += 1.0
            return s

        ranked = sorted(candidates, key=score, reverse=True)
        best = ranked[0]
        if strict and len(ranked) >= 2 and score(ranked[1]) >= score(best) * 0.98:
            names = [f"{c.get('name')} (authorId={c.get('authorId')}, affiliations={c.get('affiliations')})" for c in ranked[:5]]
            raise RuntimeError("Ambiguous author search, pass --author_id. Top candidates:\n- " + "\n- ".join(names))
        return best

    def iter_author_papers(self, author_id: str) -> list[dict[str, Any]]:
        papers: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            data = self._request_json(
                f"/author/{urllib.parse.quote(author_id)}/papers",
                {
                    "limit": limit,
                    "offset": offset,
                    "fields": "paperId,title,year,venue,externalIds,citationCount,influentialCitationCount,authors,url",
                },
            )
            batch = data.get("data") or []
            papers.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            if offset > 10_000:
                break
        return papers

    def iter_paper_citations(self, paper_id: str, *, max_items: int) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        max_items = max(0, max_items)
        while len(citations) < max_items:
            request_limit = min(limit, max_items - len(citations))
            data = self._request_json(
                f"/paper/{urllib.parse.quote(paper_id)}/citations",
                {
                    "limit": request_limit,
                    "offset": offset,
                    "fields": "citingPaper.paperId,citingPaper.title,citingPaper.year,citingPaper.venue,citingPaper.authors,citingPaper.externalIds,citingPaper.url,citingPaper.citationCount,isInfluential,contexts",
                },
            )
            batch = data.get("data") or []
            citations.extend(batch)
            if len(batch) == 0 or len(batch) < request_limit:
                break
            offset += limit
            if offset > 50_000:
                break
        return citations
