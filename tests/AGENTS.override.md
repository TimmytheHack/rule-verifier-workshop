# tests Path Override

## Purpose

Tests protect verifier boundaries, schema grounding, extraction normalization,
and evaluation assumptions.

## Rules

- Add tests for every new executable field, candidate promotion path, or
  missing-schema guardrail.
- Mock API-backed clients. Unit tests must not call real DeepSeek endpoints.
- Prefer focused assertions on execution level, schema grounding, and unsafe
  promotion over broad snapshot tests.
- Keep tests deterministic and independent of `.env`.

## Verification

```bash
python3 -m unittest discover -s tests
```

