# docs Path Override

## Purpose

This path contains narrative methodology, evaluation, schema-profile, and demo
case documentation. Docs should explain the safety boundary rather than make the
system appear more capable than it is.

## Rules

- Keep ordinary Markdown docs in Chinese only.
- Do not reintroduce parallel English/Chinese documentation files.
- If benchmark numbers change, update every report and summary table that cites
  them.
- State limitations plainly: one-year rank data is not stable enough for a full
  advisor, and this project evaluates rule safety rather than final application
  quality.
- Do not document unsupported preferences as executable unless the matching
  field has been promoted into `schemas/schema_registry.json` and tested.
- When implementation behavior changes, update all related tracked text in the
  same quest: README sections, methodology/evaluation reports, project-plan
  notes, generated summaries, and frontend mock/demo copy when those texts
  describe the changed behavior.
- Before finishing a quest, search docs and README for stale executor, schema,
  API payload, artifact path, benchmark, or guardrail descriptions introduced
  by the change.

## Verification

After changing docs, run:

```bash
git diff --check
```

If numbers were changed, also inspect the corresponding files in `outputs/eval/`.
