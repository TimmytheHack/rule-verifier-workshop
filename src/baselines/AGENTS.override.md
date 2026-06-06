# src/baselines Path Override

## Purpose

Baselines compare verifier-controlled architecture against LLM-only approaches.
They are evaluation tools, not safe execution paths.

## Rules

- Do not route baseline output into executors.
- Keep prompts honest: baselines may propose rules, but the evaluator checks
  unsafe promotion.
- Schema-aware baselines may receive schema context, but must still remain
  separate from symbolic verifier logic.
- Preserve token usage in returned payloads for evaluation.

## Verification

```bash
python3 -m unittest tests.test_deepseek_eval_modes
```

