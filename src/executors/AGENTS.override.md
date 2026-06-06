# src/executors Path Override

## Purpose

Executors apply verified executable rules to a backend such as pandas.

## Rules

- Executors must not verify rules, ask LLMs, or promote candidates.
- Executors should assume rules were already verified and fail clearly on bad
  data rather than silently weakening filters.
- Keep numeric parsing conservative and test any broadened parsing behavior.
- Preserve trace-relevant fields needed by downstream result explanations.

## Verification

Run the MVP demo or targeted executor tests after changing execution behavior:

```bash
python3 scripts/run_mvp_demo.py
```

