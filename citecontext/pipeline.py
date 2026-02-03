from __future__ import annotations

import heapq
import json
from dataclasses import dataclass
from typing import Any

from .semanticscholar import SemanticScholarClient
from .md import DEFAULT_MD_HEADERS, records_to_md_rows, render_markdown_table


@dataclass(frozen=True)
class RunConfig:
    author_name: str | None
    author_id: str | None
    affiliation_keyword: str | None
    max_target_papers: int
    scan_citations_per_paper: int
    top_citations_per_paper: int
    max_records: int
    influential_only: bool
    require_context: bool
    output_json: str
    output_md: str
    max_context_chars: int
    api_key: str | None
    cache_dir: str
    timeout_sec: float
    min_interval_sec: float
    max_retries: int
    strict_disambiguation: bool


def _extract_first_last_author(paper: dict[str, Any]) -> tuple[str, str]:
    authors = paper.get("authors") or []
    first = ((authors[0] or {}).get("name") or "").strip() if authors else ""
    last = ((authors[-1] or {}).get("name") or "").strip() if authors else ""
    return first, last


def _top_k_papers_by_citation_count(papers: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    papers = list(papers)
    papers.sort(key=lambda p: (p.get("citationCount") or 0, p.get("year") or 0), reverse=True)
    return papers[: max(0, k)]


def run(cfg: RunConfig) -> None:
    if not cfg.author_id and not cfg.author_name:
        raise ValueError("Provide --author_id or --author_name")

    client = SemanticScholarClient(
        api_key=cfg.api_key,
        cache_dir=cfg.cache_dir,
        cache_ttl_hours=None,
        timeout_sec=cfg.timeout_sec,
        min_interval_sec=cfg.min_interval_sec,
        max_retries=cfg.max_retries,
    )

    if cfg.author_id:
        author_id = cfg.author_id
        cited_author_name = cfg.author_name or "Unknown"
    else:
        assert cfg.author_name is not None
        chosen = client.resolve_author(
            cfg.author_name,
            affiliation_keyword=cfg.affiliation_keyword,
            strict=cfg.strict_disambiguation,
        )
        author_id = chosen["authorId"]
        cited_author_name = chosen.get("name") or cfg.author_name

    author_papers = client.iter_author_papers(author_id)
    target_papers = _top_k_papers_by_citation_count(author_papers, cfg.max_target_papers)
    if not target_papers:
        raise RuntimeError(f"No papers found for authorId={author_id}")

    records: list[dict[str, Any]] = []
    for cited_paper in target_papers:
        cited_paper_id = cited_paper.get("paperId") or ""
        if not cited_paper_id:
            continue

        heap: list[tuple[int, int, dict[str, Any]]] = []
        tie = 0
        citations = client.iter_paper_citations(cited_paper_id, max_items=max(0, cfg.scan_citations_per_paper))
        for citation in citations:
            if cfg.influential_only and citation.get("isInfluential") is False:
                continue
            citing = citation.get("citingPaper") or {}
            contexts = citation.get("contexts") or []
            if cfg.require_context and not contexts:
                continue

            citing_cc = int(citing.get("citationCount") or 0)
            tie += 1
            heapq.heappush(heap, (citing_cc, tie, citation))
            if len(heap) > max(1, cfg.top_citations_per_paper):
                heapq.heappop(heap)

        top = sorted(heap, key=lambda t: t[0], reverse=True)
        for _, __, citation in top:
            citing = citation.get("citingPaper") or {}
            first_author, last_author = _extract_first_last_author(citing)

            records.append(
                {
                    "cited_author": {"authorId": author_id, "name": cited_author_name},
                    "cited_paper": {
                        "paperId": cited_paper.get("paperId"),
                        "title": cited_paper.get("title"),
                        "venue": cited_paper.get("venue"),
                        "year": cited_paper.get("year"),
                        "citationCount": cited_paper.get("citationCount"),
                        "externalIds": cited_paper.get("externalIds"),
                        "url": cited_paper.get("url"),
                    },
                    "citing_paper": {
                        "paperId": citing.get("paperId"),
                        "title": citing.get("title"),
                        "venue": citing.get("venue"),
                        "year": citing.get("year"),
                        "citationCount": citing.get("citationCount"),
                        "externalIds": citing.get("externalIds"),
                        "url": citing.get("url"),
                    },
                    "citing_first_author": first_author,
                    "citing_last_author": last_author,
                    "corresponding_author_assumption": "last_author",
                    "citing_last_author_is_IEEE_Fellow": None,
                    "citing_last_author_position": None,
                    "isInfluential": citation.get("isInfluential"),
                    "citation_contexts": citation.get("contexts") or [],
                }
            )

            if len(records) >= cfg.max_records:
                break
        if len(records) >= cfg.max_records:
            break

    payload = {
        "query": {
            "author_name": cfg.author_name,
            "author_id": cfg.author_id,
            "max_target_papers": cfg.max_target_papers,
            "scan_citations_per_paper": cfg.scan_citations_per_paper,
            "top_citations_per_paper": cfg.top_citations_per_paper,
            "influential_only": cfg.influential_only,
            "require_context": cfg.require_context,
            "max_records": cfg.max_records,
        },
        "records": records,
    }
    with open(cfg.output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    md_rows = records_to_md_rows(records, max_context_chars=cfg.max_context_chars)
    md = render_markdown_table(DEFAULT_MD_HEADERS, md_rows)
    with open(cfg.output_md, "w", encoding="utf-8") as f:
        f.write(md)
