# domains Path Override

## Purpose

This path contains domain packs that configure schema mappings, aliases, rule
taxonomy, execution projection, answer templates, and golden cases.

## Rules

- Keep domain packs declarative. Runtime code must read canonical fields from
  `DomainConfig` instead of hardcoding source column names.
- Domain pack text may use the target domain language, but this override file
  must stay in English.
- Do not add vector databases or full-table embeddings for tabular fixtures.

## Verification

Validate edited JSON files and run focused domain tests.
