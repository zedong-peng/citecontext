python3 -m citecontext --author_name "Jieru Zhao" \
  --output_json output.json \
  --output_md output.md

# Stage 2 (optional, slow)
# export LLM_API_KEY="sk-..."
# python3 -m citecontext.enrich_titles_json \
#   --input output.json \
#   --output output.enriched.json \
#   --output_md output.enriched.md \
#   --api_base "https://..." \
#   --model "deepseek-v3-1-250821"
