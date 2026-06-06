# src Path Override

## Purpose

This path contains runtime and evaluation support code.

## Rules

- Preserve the extraction -> grounding -> verification -> promotion -> execution
  separation.
- Do not call LLMs from verifier, executor, or trace generation logic.
- Keep runtime behavior deterministic after extraction.
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

