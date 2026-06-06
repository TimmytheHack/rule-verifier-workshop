# src/schema Path Override

## Purpose

Schema code loads executable field definitions, profiles workbooks, and audits
attribute grounding.

## Rules

- Runtime registry should expose only active fields whose source columns exist.
- Schema profiling is offline and must not be imported by runtime execution.
- Attribute grounding can mark slots as schema-grounded, confirmable,
  context-only, missing-schema, or ignored; it must not execute filters.
- Unknown extractor output should be ignored rather than guessed into rules.

## Verification

```bash
python3 -m unittest tests.test_schema_profiler tests.test_rule_verifier
```

