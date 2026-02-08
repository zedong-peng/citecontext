# citecontext
Extracting citation contexts from Semantic Scholar for verifiable academic evaluation.

## Quickstart

**Title search** (web search + 点进页面读全文 + LLM 总结某人 notable titles):

```bash
# 输出：默认打印到终端；加 --output 写入文件
python -m citecontext.titlesearch "Deming Chen" \
    --api_base "https://..." \
    --api_key "sk-..." \
    --model "deepseek-v3-1-terminus" \
    --output deming_chen_titles.json
```

- **不加 `--output`**：JSON 打印到 **终端 (stdout)**，进度/日志在 stderr。
- **加 `--output 文件名`**：JSON 写入该文件，例如 `jieru_zhao_titles.json`。
- 缓存：每人结果缓存在 `.cache/titlesearch/`，7 天有效，重复查同一人不会重新搜。

**主流程（Stage 1）**：只用 Semantic Scholar API 拉取引用证据（快）

```bash
python3 -m citecontext --author_name "Jieru Zhao"
# 生成 output.json 和 output.md
```

默认会用一个加速启发：`--earliest_author_cutoff_year 2015`，即选“最早发文作者”时只考虑 **2015 年及以前**就已发表过论文的作者；想要严格查全量（会更慢）可用 `--earliest_author_cutoff_year 0` 关闭。

**Title enrichment（Stage 2，可选，慢）**：读入 Stage 1 的 JSON，对“最早发文作者”做 web+LLM titles 总结，写回新 JSON：

```bash
export LLM_API_KEY="sk-..."
python3 -m citecontext.enrich_titles_json \
  --input output.json \
  --output output.enriched.json \
  --output_md output.enriched.md \
  --api_base "https://..." \
  --model "deepseek-v3-1-250821"
```
