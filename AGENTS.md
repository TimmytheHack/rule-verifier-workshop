# AGENTS.md

## Mission

This repository is a research-engineering project for preference-to-rule
verification in Guangdong college application planning. It is not a generic
recommendation bot.

Core invariant:

```text
Natural language may propose structure, but only verified schema-grounded rules may execute.
```

## Agent File Convention

- Root agent instructions live in `AGENTS.md`.
- Path-specific overrides use the singular filename `AGENTS.override.md`.
- Keep `AGENTS.md` and every `AGENTS.override.md` file in English.
- Do not rename `AGENTS.override.md` to `AGENTS.overrides.md`.
- Keep overrides concise and path-specific; do not duplicate the full root
  policy in every directory.

## Documentation And Comments

- Human-facing README files are Chinese only.
- Ordinary Markdown docs are Chinese only, except for technology names,
  commands, file paths, API names, identifiers, and established protocol terms.
- Project-owned source comments should be Chinese.
- Do not translate identifiers, function names, class names, JSON keys, API
  response field names, package names, commands, or protocol terms for language
  consistency.
- Generated Markdown should follow the same naming convention when practical:
  Chinese canonical docs use unsuffixed `*.md` filenames.

## Architecture Boundary

Runtime flow:

```text
Extractor
-> AttributeGrounder
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> Executor
-> TraceGenerator
-> EvidencePack
-> ReportBuilder / AnswerGenerator
```

Keep these boundaries intact:

- Extractors may extract preferences and source spans, but must not decide final
  executability.
- `RegexExtractor` is a benchmark baseline, not the final extraction strategy.
- `DeepSeekExtractor` may extract preferences and source spans only.
- Attribute grounding audits extracted slots before rule construction.
- Rule verification controls schema existence, operator validity, ambiguity,
  and execution level.
- Candidate rules must not execute before confirmation or simulated
  confirmation.
- Runtime confirmation must reference a system-generated `candidate_id` from the
  previous Workbench response. Do not compile free-form second-turn user text
  into SQL.
- `partial_match` value-index candidates may become hard rules only after their
  `candidate_id` is confirmed and rechecked. `no_schema_field` preferences must
  remain non-executable even if the user tries to confirm them.
- Missing-schema or external-info preferences must be preserved but not
  executed.
- LLM-only baselines are evaluation baselines, not production execution paths.
- `DuckDBExecutor` is the primary Workbench executor for verified hard rules.
- `PandasExecutor` is retained for the legacy MVP demo, evaluation comparison,
  and focused tests; Workbench must not silently fall back from DuckDB to raw
  Excel/Pandas execution.
- `EvidencePack` is the only input to answer generation; raw Excel is not.
- `EvidencePack` must preserve confirmation evidence: confirmed rules,
  confirmation source, executed-after-confirmation rule IDs, unconfirmed
  candidates, and no-schema preferences.
- `WorkbenchResponse` is the frozen API contract for frontend consumption.
  Preserve the required top-level fields and status enum unless the API
  contract docs and snapshot tests are updated in the same quest.
- `TemplateReportBuilder` is deterministic and uses no LLM.
- `DeepSeekAnswerGenerator` is optional and evidence-only.
- `SchemaProfiler` is an offline schema-review tool, not runtime.

## Frontend Boundary

- Do not invent recommendation logic in the frontend.
- The frontend visualizes API output or mock output only.
- The frontend must preserve traceability for executable, confirmation-required,
  and not-executed preferences.
- Do not change API field names for language consistency.
- `top_results` must use frontend English keys such as `university_name`,
  `group_code`, `major_code`, `major_name`, `full_major_name`, `city`,
  `tuition`, `rank_2024`, and `plan_count`; Chinese source fields may remain
  inside `EvidencePack`.
- UI copy may explain that a preference was not executed, but must not imply
  unsupported filters were applied.

## Domain Rules

- For Guangdong application planning, rank is more important than score. If a
  user gives only score and no rank, ask for province rank instead of estimating
  risk from score alone.
- Do not output school-only recommendations when professional-group data is
  available.
- The minimum useful result shape is:

```text
院校名称
院校专业组代码
专业名称
城市
学费
专业组最低位次
专业最低位次 / if available
safety margin
```

- Explicit field/value constraints can be deterministic when schema-grounded.
  For example, `学费两万以内` can become `学费 <= 20000` if `学费` exists.
- Vague preferences such as `太贵`, `稳一点`, `学校好一点`, `计算机相关`, or
  `离家近` remain candidate or external-info needs until their boundaries are
  confirmed.

## Data Parsing And Knowledge Base Policy

- Whenever parsing Excel, CSV, or other large structured data, explicitly judge
  whether a knowledge base is needed before adding one.
- Prefer structured storage plus `schema/value index` for tabular admissions
  data. Do not embed or vectorize the full table by default.
- Use a knowledge base only for reviewed unstructured or semi-structured
  material that requires semantic retrieval, such as policy text, official
  notices, school descriptions, or documentation.
- A knowledge base hit may supply evidence or candidate context, but it must not
  bypass `AttributeGrounder`, `RuleVerifier`, or the evidence-pack boundary.
- Keep raw large files and local database artifacts out of commits unless the
  repository explicitly tracks that artifact class.

## Verification Guardrails

- Prefer deterministic execution paths for rule execution.
- Do not silently execute vague preferences.
- Do not relax verifier checks to improve benchmark scores.
- Do not add regex special cases only to chase benchmark results unless the
  expected behavior is documented and tested.
- Do not infer unsupported fields such as `cooperation_type`, employment
  outlook, dorm quality, school atmosphere, or city development potential from
  free text unless a reviewed structured field is added first.
- Answer-level evaluation checks result count, executed rules, top results,
  not-executed preferences, and claims unsupported by the verified evidence
  pack.
- `unsupported_claims` means unsupported by the verified evidence pack, not
  necessarily absent from raw Excel.

## Commands

Default Python environment:

- Before running Python commands, prefer the repository-local virtual
  environment when it exists.
- In an interactive shell session, activate it with:

```bash
source .venv/bin/activate
```

- For one-off commands, calling `.venv/bin/python` directly is also acceptable.
- Fall back to `python3` only when `.venv` is missing or unusable, and mention
  that fallback in the response if it affects verification.
- The Python commands below assume the virtual environment is active; use
  `python` from `.venv` after activation.

Run unit tests:

```bash
python -m unittest discover -s tests
```

Run the MVP demo:

```bash
python scripts/run_mvp_demo.py
```

Build the local structured data store and schema/value index:

```bash
python scripts/build_data_warehouse.py
```

Run the fast regex-only evaluator:

```bash
python scripts/eval_fuzzy_inputs.py --methods regex
```

Start the backend API:

```bash
python -m uvicorn src.api.server:app --reload --port 8001
```

Start the frontend:

```bash
cd frontend
npm run dev
```

Build the frontend:

```bash
cd frontend
npm run build
```

DeepSeek-backed checks read `.env` automatically and may incur API latency and
token usage:

```bash
python scripts/eval_modes.py
python scripts/eval_fuzzy_inputs.py --quick --output-path outputs/eval/fuzzy_deepseek_extractor_results.json
python scripts/eval_fuzzy_inputs.py --methods all
```

Never print or inspect secrets from `.env`.

## Tests And Artifacts

- After completing any chat quest, update relevant human-facing text,
  methodology docs, README sections, generated summaries, and mock/demo text
  that describe the changed behavior before committing.
- If a runtime, schema, executor, API payload, or evaluation behavior changes,
  search for stale public descriptions and update every related tracked text
  artifact in the same quest.
- When behavior changes, update focused tests and the docs that describe that
  behavior.
- When filenames change, update Markdown links, scripts, generated artifact
  paths, and public docs that mention those filenames.
- When evaluation logic or expected scores change, update:
  - `outputs/eval/eval_modes.json`
  - `outputs/eval/fuzzy_eval_results.json`
  - `outputs/eval/pipeline_token_budget.json`
  - `docs/evaluation_report.md`
  - `docs/methodology_report.md`
- When schema or rule policy changes, update tests that assert the relevant
  guardrail.

## Commit Hygiene

- After completing and verifying a chat quest, create a git commit with a
  concise, reasonable commit message.
- Stage only files that belong to the completed quest. Do not include unrelated
  user changes, generated scratch files, secrets, virtual environments, or large
  local database files.
- If unrelated worktree changes make a clean commit unsafe, explain the blocker
  instead of mixing unrelated changes into the commit.
