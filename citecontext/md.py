from __future__ import annotations

from typing import Any


DEFAULT_MD_HEADERS = [
    "被引论文",
    "被引 venue / 年份",
    "引用论文",
    "引用 venue / 年份",
    "引用作者中最早发文者",
    "原文引用句（英文）",
]

ENRICHED_MD_HEADERS = [
    "被引论文",
    "被引 venue / 年份",
    "引用论文",
    "引用 venue / 年份",
    "引用作者中最早发文者",
    "Title sum",
    "原文引用句（英文）",
]


def md_headers_for_records(records: list[dict[str, Any]]) -> list[str]:
    """Return column headers for Markdown output."""
    has_enrichment = any((r.get("citing_earliest_author_title_sum") or "").strip() for r in records)
    return ENRICHED_MD_HEADERS if has_enrichment else DEFAULT_MD_HEADERS


def md_escape_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "<br>")
    text = text.replace("|", "\\|")
    return text.strip()


def render_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    header_row = "| " + " | ".join(md_escape_cell(h) for h in headers) + " |"
    sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines = [header_row, sep_row]
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(md_escape_cell(v) for v in padded[: len(headers)]) + " |")
    return "\n".join(lines) + "\n"


def venue_year(venue: Any, year: Any) -> str:
    v = (venue or "").strip() if isinstance(venue, str) else str(venue or "").strip()
    y = "" if year is None else str(year).strip()
    if v and y:
        return f"{v} {y}"
    return v or y


def md_link(title: str | None, url: str | None) -> str:
    t = (title or "").strip()
    u = (url or "").strip()
    if not t:
        return ""
    if not u:
        return t
    return f"[{t}]({u})"


def pick_context(contexts: Any, *, max_chars: int) -> str:
    if not contexts:
        return ""
    if isinstance(contexts, list):
        first = next((c for c in contexts if isinstance(c, str) and c.strip()), "")
    elif isinstance(contexts, str):
        first = contexts
    else:
        first = ""
    first = (first or "").strip()
    if max_chars > 0 and len(first) > max_chars:
        first = first[: max_chars - 1].rstrip() + "…"
    return first


def records_to_md_rows(records: list[dict[str, Any]], *, max_context_chars: int) -> list[list[Any]]:
    has_enrichment = any((r.get("citing_earliest_author_title_sum") or "").strip() for r in records)

    def sort_key(r: dict[str, Any]) -> tuple[int, int, str, str]:
        cited_cc = int(((r.get("cited_paper") or {}).get("citationCount")) or 0)
        citing_cc = int(((r.get("citing_paper") or {}).get("citationCount")) or 0)
        cited_title = ((r.get("cited_paper") or {}).get("title") or "").lower()
        citing_title = ((r.get("citing_paper") or {}).get("title") or "").lower()
        return (-cited_cc, -citing_cc, cited_title, citing_title)

    rows: list[list[Any]] = []
    for r in sorted(records, key=sort_key):
        cited = r.get("cited_paper") or {}
        citing = r.get("citing_paper") or {}

        cited_title = md_link(cited.get("title"), cited.get("url"))
        cited_vy = venue_year(cited.get("venue"), cited.get("year"))

        citing_title = md_link(citing.get("title"), citing.get("url"))
        citing_vy = venue_year(citing.get("venue"), citing.get("year"))

        earliest = r.get("citing_earliest_author") or {}
        earliest_name = (earliest.get("name") or "").strip()
        earliest_year = earliest.get("earliest_publication_year")
        earliest_cell = (
            f"{earliest_name} ({earliest_year})" if earliest_name and earliest_year else (earliest_name or "")
        )

        context = pick_context(r.get("citation_contexts"), max_chars=max_context_chars)

        if has_enrichment:
            title_sum = r.get("citing_earliest_author_title_sum") or ""
            rows.append(
                [
                    cited_title,
                    cited_vy,
                    citing_title,
                    citing_vy,
                    earliest_cell,
                    title_sum,
                    context,
                ]
            )
        else:
            rows.append(
                [
                    cited_title,
                    cited_vy,
                    citing_title,
                    citing_vy,
                    earliest_cell,
                    context,
                ]
            )
    return rows
