# src/tracing Path Override

## Purpose

Tracing explains why rules and rows were accepted, held, rejected, or marked as
LLM-needed.

## Rules

- Trace output should be auditable and tied to verified rules.
- Do not invent execution reasons for skipped or missing-schema preferences.
- Include non-executed preferences in trace when they matter to user intent.
- Keep English/Chinese trace variants aligned if both are generated.

## Verification

```bash
python3 scripts/run_mvp_demo.py
```

