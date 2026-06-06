# outputs/eval Path Override

## Purpose

This path stores evaluation result artifacts and token usage logs.

## Rules

- `eval_modes.json`, `fuzzy_eval_results.json`, and
  `pipeline_token_budget.json` are tracked evidence artifacts.
- `deepseek_token_usage.jsonl` may grow after API-backed runs; keep it only when
  the run is part of the evidence being reported.
- `deepseek_fuzzy_cache.json` and quick/partial result files are ignored helper
  artifacts.
- Do not let a skipped run overwrite API-backed evidence unless that is the
  intended result.

## Verification

Check summaries after evaluation:

```bash
python3 -m json.tool outputs/eval/eval_modes.json >/dev/null
python3 -m json.tool outputs/eval/fuzzy_eval_results.json >/dev/null
python3 -m json.tool outputs/eval/pipeline_token_budget.json >/dev/null
```

