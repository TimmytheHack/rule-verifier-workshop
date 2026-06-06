# outputs Path Override

## Purpose

This path contains generated demo and evaluation artifacts.

## Rules

- Treat outputs as generated evidence, not source policy.
- Do not hand-edit large generated JSON unless deliberately synchronizing a
  known result artifact.
- If tracked outputs are regenerated, update docs that cite their metrics.
- Cache files and quick/partial outputs should stay ignored unless intentionally
  promoted as evidence.

## Verification

After regenerating outputs, inspect summary fields before committing:

```bash
python3 -m json.tool outputs/eval/eval_modes.json >/dev/null
python3 -m json.tool outputs/eval/fuzzy_eval_results.json >/dev/null
```

