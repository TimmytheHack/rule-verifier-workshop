# outputs/mvp_demo Path Override

## Purpose

This path stores generated MVP demo artifacts: rules, filtered rows, verification
reports, and traces. Generated files are local artifacts and are ignored by
default; keep only this path-specific instruction tracked.

## Rules

- Regenerate these artifacts with `scripts/run_mvp_demo.py` rather than editing
  them by hand.
- Do not commit regenerated MVP demo files unless a maintainer explicitly
  promotes them back to tracked evidence.
- If result count or rule behavior changes, update README and methodology
  references.
- Preserve trace clarity: executed, confirmable, and non-executable preferences
  should remain distinguishable.

## Verification

```bash
python3 scripts/run_mvp_demo.py
```
