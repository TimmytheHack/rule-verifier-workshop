# Preference-to-Rule Verification Workbench

中文版本 / Chinese version: [README.md](README.md)

This is a research-engineering project for Guangdong college application planning. It verifies whether natural-language preferences can be safely converted into executable rules. It is not a generic recommendation bot, and it does not silently execute vague preferences as filters.

The project focuses on:

- preferences that can be schema-grounded and converted into deterministic rules;
- preferences that require confirmation before execution;
- preferences that must remain not executed because the schema is missing, the wording is vague, or external information is required;
- a frontend workbench that shows extraction, attribute grounding, verification, execution results, and trace evidence.

## Current Shape

The repository contains a FastAPI backend and a Vue 3 frontend workbench:

- The backend runs the verified pipeline, reads the Guangdong application-planning Excel workbook, and returns rules, results, traces, and evidence-backed answers.
- The frontend only visualizes mock data or backend API output. It does not add recommendation logic or infer new rules.
- LLMs can assist extraction or evidence-based answering, but executability is still controlled by the schema-grounded verifier.

Main paths:

| Path | Purpose |
|---|---|
| `src/` | Verification pipeline, rules, executor, API, and reporting code |
| `frontend/` | Vue 3 + Vite + Element Plus frontend workbench |
| `schemas/` | Reviewed schema registry and schema profile |
| `rules/` | Rule lifecycle, taxonomy, and vague-term configuration |
| `scripts/` | Demo, evaluation, and offline schema profiling scripts |
| `docs/` | Methodology, evaluation, and end-to-end demo documentation |
| `outputs/` | Generated demo and evaluation artifacts |

## Local Requirements

Recommended environment:

- Python 3.10+
- Node.js 18+
- npm

The backend demo expects this Excel file at the repository root:

```text
广东省2025年志愿填报大数据（24-25）0523.xlsx
```

If the file is missing, API mode and the MVP demo cannot run correctly.

## Start The Backend

From the repository root, create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

`.env` uses:

```text
DEEPSEEK_API_KEY=replace_with_your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat
```

You do not need a DeepSeek key for frontend demo mode, regex extraction, or template evidence answers. You need a valid key when using LLM-assisted extraction or LLM evidence answers.

Start FastAPI:

```bash
source .venv/bin/activate
python -m uvicorn src.api.server:app --reload --port 8001
```

Check the backend:

```bash
curl http://127.0.0.1:8001/health
```

Expected response:

```json
{"status":"ok"}
```

## Start The Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Vite proxies `/api` to `http://127.0.0.1:8001`. Demo mode can run without the backend. API mode requires the backend to be running.

## Test The Workbench

1. Open `http://127.0.0.1:5173`.
2. Keep demo mode selected, click the run button, and check that the page shows extracted preferences, attribute grounding, rule audit, candidate rules, not-executed preferences, filtered results, and traces.
3. Start the backend, switch to API mode, and run the default input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

4. Confirm that the page explicitly marks the Sino-foreign cooperation preference as not executed because the current schema has no cooperation-type field.
5. If you choose LLM-assisted extraction or LLM evidence answers, confirm that `.env` has a DeepSeek key and check the token usage panel.

## Local Checks

Run unit tests:

```bash
python3 -m unittest discover -s tests
```

Run the MVP demo:

```bash
python3 scripts/run_mvp_demo.py
```

Run fast regex-only evaluation:

```bash
python3 scripts/eval_fuzzy_inputs.py --methods regex
```

Build the frontend:

```bash
cd frontend
npm run build
```

Optional DeepSeek-backed evaluation:

```bash
python3 scripts/eval_modes.py
python3 scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
python3 scripts/eval_fuzzy_inputs.py --methods all
```

DeepSeek-backed evaluation reads `.env` and may incur API latency and token usage.

## Related Docs

- [Methodology report](docs/methodology_report.md)
- [Evaluation report](docs/evaluation_report.md)
- [End-to-end demo cases](docs/end_to_end_demo_cases.md)
- [Excel schema profile](docs/excel_schema_profile.md)
- [Full project plan](docs/full_project_plan.md)
