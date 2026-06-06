# src/rules Path Override

## Purpose

Runtime rule logic classifies extracted slots, verifies executability, and
promotes confirmed candidates.

## Rules

- Candidate rules must remain non-executable until explicit confirmation or
  simulated confirmation in evaluation.
- Rule verification must remain symbolic and schema-driven.
- Missing schema must result in rejected or non-executable status.
- Do not add LLM calls here.
- If optional rules are added, use explicit missing-value handling rather than
  creating noisy blocked rules.

## Verification

```bash
python3 -m unittest tests.test_rule_verifier
```

