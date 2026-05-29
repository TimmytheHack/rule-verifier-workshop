# Preference-to-Rule Verification MVP

Chinese version: [README.zh.md](/Users/tz/Desktop/Projects/SZU/README.zh.md)

This repository contains a narrow research-engineering MVP for:

```text
Preference-to-Rule Verification Methodology for Guangdong College Application Planning
```

The project is not a normal college recommendation bot. It demonstrates how one natural-language college application preference can be decomposed into deterministic rules, candidate rules requiring confirmation, and semantic parts that should not be executed.

## Current MVP

The MVP supports exactly one demo input:

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

The pipeline:

1. Loads the Excel workbook.
2. Detects the real header row.
3. Builds a schema registry from real Excel fields only.
4. Uses hardcoded extracted slots for the demo input.
5. Verifies deterministic rules.
6. Keeps vague preferences as candidate rules.
7. Simulates confirmation for safety margin and tuition cap.
8. Executes only verified and confirmed rules.
9. Writes result artifacts with rule traces.

## Files

Planning docs:

- [docs/methodology_engineering_plan.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_engineering_plan.md)
- [docs/mvp_demo_spec.md](/Users/tz/Desktop/Projects/SZU/docs/mvp_demo_spec.md)
- [docs/methodology_report.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.md)

Demo script:

- [scripts/run_mvp_demo.py](/Users/tz/Desktop/Projects/SZU/scripts/run_mvp_demo.py)

Generated outputs:

- [outputs/mvp_demo/rules.json](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/rules.json)
- [outputs/mvp_demo/verification_report.md](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/verification_report.md)
- [outputs/mvp_demo/filtered_results.csv](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/filtered_results.csv)
- [outputs/mvp_demo/result_trace.md](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/result_trace.md)

## Run

From the project root:

```bash
/Users/tz/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_mvp_demo.py
```

Expected current output:

```text
Wrote outputs/mvp_demo/rules.json
Wrote outputs/mvp_demo/verification_report.md
Wrote outputs/mvp_demo/filtered_results.csv
Wrote outputs/mvp_demo/result_trace.md
Filtered rows: 93
```

## Final Executable Rules

The demo executes six rules:

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

The last two rules come from simulated confirmation:

- `稳一点` -> 10% safety margin for rank 32000.
- `太贵` -> tuition cap 20000 元/年.

## Safety Boundary

The preference `中外合作` is not executed because the Excel schema has no dedicated `cooperation_type` field. The MVP does not infer this from text fields such as专业全称, 专业备注, or专业组名称.

This is intentional. The core research question is not how to recommend more aggressively, but how to avoid silently turning vague or unsupported preferences into executable rules.

## Current Limitations

- Only one input is supported.
- Slot extraction is hardcoded.
- Confirmation is simulated.
- No LLM is used in code.
- No external web search is used.
- No full志愿表 is generated.
- No school reputation or employment prediction is attempted.
- No semantic expansion is applied for related majors.

See [docs/methodology_report.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.md) for the research interpretation and next evaluation plan.
