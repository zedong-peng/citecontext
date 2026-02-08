from __future__ import annotations

import argparse
import json
import os
import sys

from .titlesearch import TitleSearchConfig, enrich_records
from .md import md_headers_for_records, records_to_md_rows, render_markdown_table


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="citecontext.enrich_titles_json",
        description="Enrich citecontext JSON by searching earliest-author titles (web + LLM).",
    )
    p.add_argument("--input", required=True, help="Input JSON produced by `python -m citecontext`.")
    p.add_argument("--output", required=True, help="Output enriched JSON path.")
    p.add_argument("--output_md", default=None, help="Optional output Markdown path.")
    p.add_argument("--max_context_chars", type=int, default=280)
    p.add_argument("--api_base", required=True, help="OpenAI-compatible API base URL for the LLM.")
    p.add_argument("--api_key", default=None, help="API key (or set LLM_API_KEY).")
    p.add_argument(
        "--model",
        default="deepseek-v3-1-250821",
        help="Model name (default: deepseek-v3-1-250821).",
    )
    p.add_argument(
        "--cache_dir",
        default=os.path.join(".cache", "titlesearch"),
        help="Cache directory for title search.",
    )
    p.add_argument("--num_search_results", type=int, default=5)
    p.add_argument("--max_page_chars", type=int, default=3000)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = args.api_key or os.environ.get("LLM_API_KEY")
    if not api_key:
        print("error: provide --api_key or set LLM_API_KEY", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    records = payload.get("records") or []
    if not isinstance(records, list):
        print("error: input JSON missing `records` list", file=sys.stderr)
        return 2

    cfg = TitleSearchConfig(
        api_base=args.api_base,
        api_key=api_key,
        model=args.model,
        cache_dir=args.cache_dir,
        num_search_results=args.num_search_results,
        max_page_chars=args.max_page_chars,
    )
    try:
        payload["records"] = enrich_records(records, cfg)
    except ImportError as exc:
        print(
            "error: missing optional dependencies for web title search.\n"
            "Fix:\n"
            "  python3 -m pip install -r requirements.txt\n"
            "Or at least:\n"
            "  python3 -m pip install ddgs requests beautifulsoup4 tqdm\n"
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 2

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if args.output_md:
        md_headers = md_headers_for_records(payload["records"])
        md_rows = records_to_md_rows(payload["records"], max_context_chars=args.max_context_chars)
        md = render_markdown_table(md_headers, md_rows)
        with open(args.output_md, "w", encoding="utf-8") as f:
            f.write(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
