# src/evaluation Path Override

## Purpose

Evaluation code scores task success, over-promotion, schema hallucination, and
token efficiency.

## Rules

- Keep safety metrics separate from recommendation-quality metrics.
- Do not change scoring to hide unsafe promotion.
- If scoring criteria change, update reports and explain the changed denominator.
- Prefer explicit boolean score parts over opaque aggregate scores.

## Verification

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
python3 -m unittest discover -s tests
```

