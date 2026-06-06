# scripts Path Override

## Purpose

Scripts are command-line entry points for demo runs, schema profiling, and
evaluation.

## Rules

- Keep scripts importable from repo root without requiring manual `PYTHONPATH`.
- Do not print secrets from `.env`.
- Evaluation scripts should support local/cheap paths and API-backed paths
  separately.
- Long DeepSeek-backed evaluation should be resumable or cache-aware.
- If scripts regenerate tracked outputs, update reports that cite those outputs.

## Preferred Commands

Local checks:

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

DeepSeek extractor check:

```bash
python3 scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
```

Full comparison:

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --methods all
```

