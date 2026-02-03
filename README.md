# citecontext
Extracting citation contexts from Semantic Scholar for verifiable academic evaluation.

## Quickstart

Generate `output.json` and `output.md`:

```bash
python3 -m citecontext --author_name "Jieru Zhao"
```

Optional:

```bash
export SEMANTIC_SCHOLAR_API_KEY="..."
python3 -m citecontext --author_name "Jieru Zhao" --max_target_papers 20 --top_citations_per_paper 3 --scan_citations_per_paper 1000 --output_json output.json --output_md output.md
```

## Influential Citations

Filter to "Highly Influential Citations" only:

```bash
python3 -m citecontext --author_name "Jieru Zhao" --influential_only --output_json output.json
```

## Usage

Minimal (defaults produce `output.json` and `output.md`):

```bash
python3 -m citecontext --author_name "Jieru Zhao"
```

Common options:

```bash
# If author-name search is ambiguous
python3 -m citecontext --author_id "<SemanticScholarAuthorId>"

# Relax filters (include non-influential and/or missing context)
python3 -m citecontext --author_name "Jieru Zhao" --no-influential_only --no-require_context

# Change scale
python3 -m citecontext --author_name "Jieru Zhao" --max_target_papers 20 --top_citations_per_paper 3 --scan_citations_per_paper 2000
```

Defaults (when you only pass `--author_name`):

- `--max_target_papers 20` (the author’s top-20 papers by `citationCount`)
- `--top_citations_per_paper 3` (keep top-3 citing papers per cited paper)
- `--scan_citations_per_paper 1000` (scan up to 1000 citations before selecting top-3)
- `--max_records 60` (20×3)
- `--influential_only` and `--require_context` are both enabled by default

Output schema notes:

- Each record contains `citing_first_author` and `citing_last_author` (the latter is used as a *corresponding author approximation*), plus `citation_contexts` as returned by the API (not generated).
- Each record also contains `citing_last_author_is_IEEE_Fellow` (currently always `null`).
- Each record also contains `citing_last_author_position` (currently always `null`; e.g. "AP"/"Professor" if filled in later).
