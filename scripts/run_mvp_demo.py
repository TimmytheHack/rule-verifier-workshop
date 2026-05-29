"""Run the first MVP demo through the reusable framework skeleton.

The behavior intentionally remains the same as the original single-file MVP:
- same input
- same simulated confirmations
- same final executable rules
- same non-execution of 中外合作
- same four output artifacts
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.adapters.excel_adapter import ExcelAdapter, ExcelDataSet
from src.executors.pandas_executor import PandasExecutor
from src.extractors.regex_extractor import RegexExtractor
from src.rules.rule_classifier import RuleClassifier
from src.rules.rule_promoter import RulePromoter
from src.rules.rule_verifier import RuleVerifier
from src.schema.schema_registry import SchemaRegistry
from src.tracing.trace_generator import TraceGenerator


WORKBOOK_NAME = "广东省2025年志愿填报大数据（24-25）0523.xlsx"
OUTPUT_DIR = Path("outputs/mvp_demo")
SCHEMA_PATH = Path("schemas/schema_registry.json")
TAXONOMY_PATH = Path("rules/rule_taxonomy.json")

DEMO_INPUT = "我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。"

REQUIRED_COLUMNS = [
    "生源地",
    "科类",
    "专业名称",
    "城市",
    "专业组最低位次1",
    "学费",
]


def data_coverage(dataset: ExcelDataSet, columns: list[str]) -> dict[str, Any]:
    """统计 MVP 必需字段的数据覆盖率，用于验证报告。"""

    total = len(dataset.dataframe)
    coverage: dict[str, Any] = {}
    for column in columns:
        non_null = int(dataset.dataframe[column].notna().sum()) if column in dataset.dataframe.columns else 0
        coverage[column] = {
            "non_null": non_null,
            "total_rows": total,
            "coverage": round(non_null / total, 4) if total else 0,
        }
    return coverage


def build_rules_payload(
    slots: dict[str, Any],
    schema_registry: SchemaRegistry,
    classified_rules: dict[str, Any],
    final_executable_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """组装 rules.json，保持原 MVP 输出结构。"""

    return {
        "input": DEMO_INPUT,
        "extracted_slots": slots,
        "schema_registry": schema_registry.to_dict(),
        "deterministic_rules": classified_rules["deterministic_rules"],
        "context_rules": classified_rules["context_rules"],
        "candidate_rules": classified_rules["candidate_rules"],
        "llm_needed_parts": classified_rules["llm_needed_parts"],
        "confirmation_questions": classified_rules["confirmation_questions"],
        "simulated_confirmations": classified_rules["simulated_confirmations"],
        "final_executable_rules": final_executable_rules,
        "non_executable_preferences": classified_rules["non_executable_preferences"],
    }


def write_rules_json(rules_payload: dict[str, Any]) -> None:
    (OUTPUT_DIR / "rules.json").write_text(
        json.dumps(rules_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_filtered_results_csv(results: list[dict[str, Any]]) -> None:
    columns = [
        "rank",
        "excel_row_number",
        "ID",
        "年份",
        "批次",
        "院校代码",
        "院校名称",
        "院校专业组代码",
        "专业组名称",
        "专业代码",
        "专业名称",
        "专业全称",
        "城市",
        "学费",
        "专业组最低位次1",
        "最低位次1",
        "院校标签",
        "院校排名",
        "ranking_key",
        "safety_margin_pct",
        "cooperation_filter_status",
    ]
    with (OUTPUT_DIR / "filtered_results.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for rank, row in enumerate(results, start=1):
            csv_row = {column: row.get(column) for column in columns}
            csv_row["rank"] = rank
            writer.writerow(csv_row)


def write_verification_report(
    dataset: ExcelDataSet,
    rules_payload: dict[str, Any],
    coverage: dict[str, Any],
    result_count: int,
) -> None:
    deterministic_lines = []
    for rule in rules_payload["deterministic_rules"]:
        verification = rule["verification"]
        deterministic_lines.append(
            f"| `{rule['rule_id']}` | `{rule['field']}` | `{rule['operator']}` | "
            f"`{rule['value']}` | {verification['executable']} | {rule['trace_reason']} |"
        )

    candidate_lines = []
    for rule in rules_payload["candidate_rules"]:
        candidate_lines.append(
            f"| `{rule['rule_id']}` | {rule['source_text']} | {rule['status']} | "
            f"{rule['requires_human_confirmation']} | {rule['trace_reason']} |"
        )

    coverage_lines = []
    for column, stats in coverage.items():
        coverage_lines.append(
            f"| `{column}` | {stats['non_null']} | {stats['total_rows']} | {stats['coverage']:.2%} |"
        )

    content = f"""# MVP Demo Verification Report

## Input

```text
{DEMO_INPUT}
```

## Workbook

- Sheet: `{dataset.sheet_name}`
- Detected header row: `{dataset.header_row}`
- Required demo columns found: `{', '.join(REQUIRED_COLUMNS)}`

## Schema Boundary

The schema registry was built only from real Excel fields needed for this demo.

Missing field:

- `cooperation_type`: not present. The 中外合作 preference is not executable in this MVP.

## Data Coverage

| Column | Non-null | Total rows | Coverage |
|---|---:|---:|---:|
{chr(10).join(coverage_lines)}

## Deterministic Rule Verification

| Rule | Field | Operator | Value | Executable | Reason |
|---|---|---|---|---:|---|
{chr(10).join(deterministic_lines)}

## Candidate Rules

| Rule | Source text | Status | Requires confirmation | Reason |
|---|---|---|---:|---|
{chr(10).join(candidate_lines)}

## Simulated Confirmations

- Safety margin: 10%, so `专业组最低位次1 >= 35200`.
- Tuition cap: `学费 <= 20000`.
- Major expansion: false; only exact keyword `计算机` is used.
- Cooperation type exclusion: not executed because `cooperation_type` is missing.

## Final Query Behavior

The query applies six executable rules with AND logic:

1. `生源地 == 广东`
2. `科类 == 物理`
3. `专业名称 contains 计算机`
4. `城市 contains 广州 or 深圳`
5. `专业组最低位次1 >= 35200`
6. `学费 <= 20000`

The query does not infer or filter 中外合作 from text fields.

## Result Summary

- Filtered row count: `{result_count}`
- Ranking: closest safe professional-group rank first, using `专业组最低位次1 - 35200`.

## Safety Checks

- No LLM is used in code.
- No semantic major expansion is applied.
- No `cooperation_type` field is invented.
- Candidate rules are promoted only through simulated confirmation.
"""
    (OUTPUT_DIR / "verification_report.md").write_text(content, encoding="utf-8")


def write_result_trace(results: list[dict[str, Any]]) -> None:
    lines = [
        "# MVP Demo Result Trace",
        "",
        "Every returned row passed the six executable rules. The 中外合作 preference is shown as not executed because the schema lacks a dedicated `cooperation_type` field.",
        "",
        f"Total returned rows: {len(results)}",
        "",
    ]
    for rank, row in enumerate(results, start=1):
        lines.extend(
            [
                f"## {rank}. {row['院校名称']} - {row['专业名称']}",
                "",
                f"- ID: `{row['ID']}`",
                f"- Excel row: `{row['excel_row_number']}`",
                f"- 专业组: `{row['院校专业组代码']} {row['专业组名称']}`",
                f"- 城市: `{row['城市']}`",
                f"- 学费: `{row['学费']:g}`",
                f"- 专业组最低位次1: `{row['专业组最低位次1']}`",
                f"- Ranking key: `{row['ranking_key']}`",
                f"- Safety margin vs user rank: `{row['safety_margin_pct']:.2%}`",
                "",
                "| Rule | Status | Reason |",
                "|---|---|---|",
            ]
        )
        for trace_item in row["trace"]:
            lines.append(
                f"| `{trace_item['rule_id']}` | {trace_item['status']} | {trace_item['reason']} |"
            )
        lines.append("")

    (OUTPUT_DIR / "result_trace.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = ExcelAdapter(WORKBOOK_NAME, REQUIRED_COLUMNS).load()
    missing_required = [column for column in REQUIRED_COLUMNS if column not in dataset.header_index]
    if missing_required:
        raise RuntimeError(f"Missing required columns: {', '.join(missing_required)}")

    schema_registry = SchemaRegistry.from_file(SCHEMA_PATH, dataset.headers)
    slots = RegexExtractor().extract(DEMO_INPUT)
    verifier = RuleVerifier(schema_registry)
    classified_rules = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
    final_executable_rules = RulePromoter(
        TAXONOMY_PATH,
        simulated_confirmation_enabled=True,
    ).final_executable_rules(classified_rules)

    raw_results = PandasExecutor().execute(dataset.dataframe, final_executable_rules)
    results = TraceGenerator().add_traces(raw_results)
    coverage = data_coverage(dataset, REQUIRED_COLUMNS)
    rules_payload = build_rules_payload(slots, schema_registry, classified_rules, final_executable_rules)

    write_rules_json(rules_payload)
    write_filtered_results_csv(results)
    write_verification_report(dataset, rules_payload, coverage, len(results))
    write_result_trace(results)

    print(f"Wrote {OUTPUT_DIR / 'rules.json'}")
    print(f"Wrote {OUTPUT_DIR / 'verification_report.md'}")
    print(f"Wrote {OUTPUT_DIR / 'filtered_results.csv'}")
    print(f"Wrote {OUTPUT_DIR / 'result_trace.md'}")
    print(f"Filtered rows: {len(results)}")


if __name__ == "__main__":
    main()
