# src Path Override

## Purpose

This path contains runtime and evaluation support code.

## Rules

- Preserve both execution separations:
  legacy extraction -> grounding -> verification -> promotion -> execution, and
  uploaded semantic intent -> reviewed grounding -> `SemanticQueryVerifier` ->
  `SemanticSQLBuilder` -> DuckDB execution.
- Do not call LLMs from verifier, SQL builder, executor, trace generation, or
  response contract assembly logic.
- LLM-facing code may propose slots, `SemanticIntent`, semantic mapping
  candidates, bounded rerank choices, or evidence-only answer text. It must not
  approve mappings, generate raw SQL, add candidate rows, relax verification, or
  write executable policy.
- Keep runtime behavior deterministic after extraction and grounding. Any
  LLM-backed fallback or failure must be recorded in planner/evidence metadata.
- For uploaded datasets, execute only through reviewed domain packs,
  schema/value indexes, warehouse fingerprint checks, and verified DuckDB
  queries. Do not silently fall back to raw Excel/Pandas execution.
- Use standard-library helpers where practical; avoid new dependencies unless
  they remove real complexity.
- Keep public functions typed and unit-testable.

## Verification

For runtime changes, run:

```bash
python3 -m py_compile src/**/*.py
python3 -m unittest discover -s tests
```

If shell globstar is unavailable, compile touched files explicitly.
