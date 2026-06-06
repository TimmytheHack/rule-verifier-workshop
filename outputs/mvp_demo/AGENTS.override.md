# outputs/mvp_demo Path Override

## Purpose

This path stores generated MVP demo artifacts: rules, filtered rows, verification
reports, and traces.

## Rules

- Regenerate these artifacts with `scripts/run_mvp_demo.py` rather than editing
  them by hand.
- If result count or rule behavior changes, update README and methodology
  references.
- Preserve trace clarity: executed, confirmable, and non-executable preferences
  should remain distinguishable.

## Verification

```bash
python3 scripts/run_mvp_demo.py
```

