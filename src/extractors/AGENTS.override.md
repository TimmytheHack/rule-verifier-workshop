# src/extractors Path Override

## Purpose

Extractors convert natural-language input into slots and source spans.

## Rules

- Extractors propose structure only; they do not decide final executability.
- `RegexExtractor` is a conservative benchmark baseline.
- `DeepSeekExtractor` may call DeepSeek for extraction only and must pass output
  through normalization plus symbolic verification.
- Never print API keys or `.env` contents.
- Keep transient network handling bounded with retry limits and timeouts.
- Explicit numeric caps, such as `学费两万以内`, may be normalized into numeric
  slots, but still require schema verification before execution.

## Verification

```bash
python3 -m unittest tests.test_deepseek_eval_modes tests.test_rule_verifier
```

