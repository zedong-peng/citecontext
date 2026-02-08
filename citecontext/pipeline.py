from __future__ import annotations

import heapq
import json
from dataclasses import dataclass
from typing import Any

from .semanticscholar import SemanticScholarClient
from .md import md_headers_for_records, records_to_md_rows, render_markdown_table
from .progress import tqdm


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
    earliest_author_cutoff_year: int | None
    api_key: str | None
    cache_dir: str
    timeout_sec: float
    min_interval_sec: float
    max_retries: int
    strict_disambiguation: bool


def _pick_earliest_publishing_author(
    client: SemanticScholarClient,
    paper: dict[str, Any],
    *,
    earliest_year_cache: dict[str, int | None],
    cutoff_year: int | None,
) -> dict[str, Any] | None:
    authors = paper.get("authors") or []
    if not authors:
        return None

    best: dict[str, Any] | None = None
    best_year: int | None = None

    for a in authors:
        if not isinstance(a, dict):
            continue
        author_id = (a.get("authorId") or "").strip()
        name = (a.get("name") or "").strip()
        if not name and not author_id:
            continue

        year: int | None = None
        if author_id:
            if author_id not in earliest_year_cache:
                earliest_year_cache[author_id] = client.get_author_earliest_publication_year(
                    author_id,
                    max_year=cutoff_year,
                )
            year = earliest_year_cache[author_id]

        if year is None:
            continue

        if best_year is None or year < best_year:
            best_year = year
            best = {"authorId": author_id or None, "name": name or None, "earliest_publication_year": year}

    if best is not None:
        return best

    first = authors[0] if isinstance(authors[0], dict) else {}
    return {
        "authorId": (first.get("authorId") or None) if isinstance(first, dict) else None,
        "name": ((first.get("name") or "").strip() or None) if isinstance(first, dict) else None,
        "earliest_publication_year": None,
    }


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
    earliest_year_cache: dict[str, int | None] = {}
    for cited_paper in tqdm(target_papers, total=len(target_papers), desc="Target papers"):
        cited_paper_id = cited_paper.get("paperId") or ""
        if not cited_paper_id:
            continue

        heap: list[tuple[int, int, dict[str, Any]]] = []
        tie = 0

        with tqdm(
            total=max(0, cfg.scan_citations_per_paper),
            desc="  Scanning citations",
            leave=False,
        ) as pbar:
            for citation in client.iter_paper_citations_iter(
                cited_paper_id, max_items=max(0, cfg.scan_citations_per_paper)
            ):
                pbar.update(1)
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
            earliest_author = _pick_earliest_publishing_author(
                client,
                citing,
                earliest_year_cache=earliest_year_cache,
                cutoff_year=cfg.earliest_author_cutoff_year,
            )

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
                    "citing_earliest_author": earliest_author,
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

    md_headers = md_headers_for_records(records)
    md_rows = records_to_md_rows(records, max_context_chars=cfg.max_context_chars)
    md = render_markdown_table(md_headers, md_rows)
    with open(cfg.output_md, "w", encoding="utf-8") as f:
        f.write(md)
