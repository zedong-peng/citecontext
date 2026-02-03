from __future__ import annotations

import argparse
import os
from dataclasses import asdict

from .pipeline import RunConfig, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="citecontext",
        description="Extract verifiable citation-context evidence from Semantic Scholar and output JSON.",
    )

    parser.add_argument("--author_name", type=str, default=None, help="Author name, e.g. 'Jieru Zhao'.")
    parser.add_argument("--author_id", type=str, default=None, help="Semantic Scholar authorId (bypass search).")
    parser.add_argument(
        "--affiliation_keyword",
        type=str,
        default=None,
        help="Optional keyword to disambiguate author search.",
    )

    parser.add_argument("--max_target_papers", type=int, default=20, help="Top-K target papers for the author.")
    parser.add_argument(
        "--scan_citations_per_paper",
        type=int,
        default=1000,
        help="How many citations to scan per target paper before selecting top results.",
    )
    parser.add_argument(
        "--top_citations_per_paper",
        type=int,
        default=3,
        help="Keep top-N citing papers per target paper (by citingPaper.citationCount).",
    )
    parser.add_argument(
        "--max_records",
        type=int,
        default=60,
        help="Max output records total (default 20*3).",
    )
    parser.add_argument(
        "--influential_only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep only Highly Influential Citations (isInfluential == true) when available.",
    )
    parser.add_argument(
        "--require_context",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep only citations with returned citation contexts.",
    )

    parser.add_argument("--output_json", type=str, default="output.json", help="Output JSON file path.")
    parser.add_argument("--output_md", type=str, default="output.md", help="Output Markdown file path.")
    parser.add_argument(
        "--max_context_chars",
        type=int,
        default=280,
        help="Max chars for the context cell in Markdown.",
    )

    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="Semantic Scholar API key (or set SEMANTIC_SCHOLAR_API_KEY).",
    )
    parser.add_argument(
        "--cache_dir",
        type=str,
        default=os.path.join(".cache", "semanticscholar"),
        help="Directory for HTTP response cache.",
    )
    parser.add_argument("--timeout_sec", type=float, default=60.0)
    parser.add_argument("--min_interval_sec", type=float, default=0.25, help="Client-side throttle between requests.")
    parser.add_argument("--max_retries", type=int, default=6, help="Retries on 429/5xx.")
    parser.add_argument(
        "--strict_disambiguation",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, abort when author search is ambiguous.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    api_key = args.api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")

    cfg = RunConfig(
        author_name=args.author_name,
        author_id=args.author_id,
        affiliation_keyword=args.affiliation_keyword,
        max_target_papers=args.max_target_papers,
        scan_citations_per_paper=args.scan_citations_per_paper,
        top_citations_per_paper=args.top_citations_per_paper,
        max_records=args.max_records,
        influential_only=args.influential_only,
        require_context=args.require_context,
        output_json=args.output_json,
        output_md=args.output_md,
        max_context_chars=args.max_context_chars,
        api_key=api_key,
        cache_dir=args.cache_dir,
        timeout_sec=args.timeout_sec,
        min_interval_sec=args.min_interval_sec,
        max_retries=args.max_retries,
        strict_disambiguation=args.strict_disambiguation,
    )

    try:
        run(cfg)
    except Exception as exc:  # noqa: BLE001
        parser.exit(2, f"error: {exc}\nconfig: {asdict(cfg)}\n")
    return 0
