python3 -m citecontext --author_name "Jieru Zhao" \
  --output_json output_full.json \
  --output_md output_full.md \
  --max_target_papers 100 \
  --scan_citations_per_paper 1000 \
  --top_citations_per_paper 1000 \
  --max_records 2000 \
  --earliest_author_cutoff_year 2018

# Stage 2 (optional, slow)
# export LLM_API_KEY="sk-..."
# python3 -m citecontext.enrich_titles_json \
#   --input output.json \
#   --output output.enriched.json \
#   --output_md output.enriched.md \
#   --api_base "https://..." \
#   --model "deepseek-v3-1-250821"
