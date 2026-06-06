# src/adapters Path Override

## Purpose

Adapters load external data sources and expose their real fields.

## Rules

- Adapters must not interpret user preferences.
- Adapters may detect headers, normalize cell text, and expose dataframes.
- Keep workbook-specific assumptions explicit and tested.
- If required columns change, update scripts, tests, and schema docs together.

## Verification

```bash
python3 -m unittest tests.test_schema_profiler
```

