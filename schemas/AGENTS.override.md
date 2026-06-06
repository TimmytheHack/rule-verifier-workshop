# schemas Path Override

## Purpose

This path defines executable schema boundaries and schema-review artifacts.

## Rules

- `schema_registry.json` is the executable schema boundary.
- `excel_schema_profile.json` is a review artifact, not automatic execution
  authority.
- Missing-but-desired fields may be documented, but must not be active unless
  the Excel source column exists and has reviewed operators.
- Attribute grounding may be broader than executable schema, but it must never
  bypass rule verification.

## Promotion Checklist

Before promoting a field into active schema:

1. Confirm the source column exists in the workbook profile.
2. Define type, aliases, allowed operators, nullable behavior, and notes.
3. Add grounding policy if extractor slots can refer to it.
4. Add tests for executable and non-executable cases.

## Verification

```bash
python3 -m json.tool schemas/schema_registry.json >/dev/null
python3 -m json.tool schemas/attribute_grounding.json >/dev/null
python3 -m unittest tests.test_schema_profiler tests.test_rule_verifier
```

