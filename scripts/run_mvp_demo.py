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
    "选科要求",
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
        "科类",
        "选科要求",
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
        "中外合作筛选状态",
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
            f"| `{rule['rule_id']}` | {rule['field']} | {_operator_text(rule['operator'])} | "
            f"{_format_value(rule['value'])} | {_bool_text(verification['executable'])} | {rule['trace_reason']} |"
        )

    candidate_lines = []
    for rule in rules_payload["candidate_rules"]:
        candidate_lines.append(
            f"| `{rule['rule_id']}` | {rule['source_text']} | {_status_text(rule['status'])} | "
            f"{_bool_text(rule['requires_human_confirmation'])} | {rule['trace_reason']} |"
        )

    coverage_lines = []
    for column, stats in coverage.items():
        coverage_lines.append(
            f"| `{column}` | {stats['non_null']} | {stats['total_rows']} | {stats['coverage']:.2%} |"
        )

    content = f"""# MVP 演示验证报告

## 输入

```text
{DEMO_INPUT}
```

## 数据表

- 工作表：`{dataset.sheet_name}`
- 检测到的表头行：`{dataset.header_row}`
- 本演示需要并已找到的字段：`{', '.join(REQUIRED_COLUMNS)}`

## 字段边界

当前字段定义只由本演示需要的真实表格字段构成。

缺失字段：

- 合作办学类型字段：当前不存在。因此“中外合作”偏好在本 MVP 中不可执行。

## 数据覆盖率

| 字段 | 非空行数 | 总行数 | 覆盖率 |
|---|---:|---:|---:|
{chr(10).join(coverage_lines)}

## 确定性规则验证

| 规则 | 字段 | 操作 | 规则值 | 是否可执行 | 原因 |
|---|---|---|---|---:|---|
{chr(10).join(deterministic_lines)}

## 候选规则

| 规则 | 来源文本 | 状态 | 是否需要确认 | 原因 |
|---|---|---|---:|---|
{chr(10).join(candidate_lines)}

## 模拟确认

- 位次窗口：10%，因此执行为“专业组最低位次1 位于 28800-35200 名的窗口内”。
- 学费上限：执行为“学费 不高于 20000”。
- 专业扩展：未扩展，只使用用户明确说出的关键词“计算机”。
- 中外合作排除：缺少合作办学类型字段，因此未执行。

## 最终筛选行为

最终筛选以 AND 逻辑执行六条已验证规则：

1. 生源地 等于 广东
2. 科类 等于 物理
3. 专业名称 包含 计算机
4. 城市 包含 广州 或 深圳
5. 专业组最低位次1 位于 28800-35200 名的窗口内
6. 学费 不高于 20000

系统不会从文本字段推断或过滤“中外合作”。

## 结果摘要

- 通过已验证规则的记录数：`{result_count}`
- 排序方式：限制在已确认位次窗口内，并按“专业组最低位次1”数值从小到大展示。

## 安全检查

- 本演示脚本不调用 LLM。
- 未执行语义专业扩展。
- 未虚构合作办学类型字段。
- 候选规则只通过模拟确认提升为可执行规则。
"""
    for filename in ["verification_report.md", "verification_report.zh.md"]:
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")


def write_result_trace(results: list[dict[str, Any]]) -> None:
    lines = [
        "# MVP 演示结果 Trace",
        "",
        "每条返回记录都通过了六条已执行规则。“中外合作”偏好因缺少合作办学类型字段而明确标记为未执行。",
        "",
        f"返回记录总数：{len(results)}",
        "",
    ]
    for rank, row in enumerate(results, start=1):
        lines.extend(
            [
                f"## {rank}. {row['院校名称']} - {row['专业名称']}",
                "",
                f"- ID: `{row['ID']}`",
                f"- 表格行号: `{row['excel_row_number']}`",
                f"- 专业组: `{row['院校专业组代码']} {row['专业组名称']}`",
                f"- 城市: `{row['城市']}`",
                f"- 学费: `{row['学费']:g}`",
                f"- 专业组最低位次1: `{row['专业组最低位次1']}`",
                f"- 排序键: `{row['ranking_key']}`",
                f"- 相对用户排位差: `{row['safety_margin_pct']:.2%}`",
                "",
                "| 规则 | 状态 | 原因 |",
                "|---|---|---|",
            ]
        )
        for trace_item in row["trace"]:
            lines.append(
                f"| `{trace_item['rule_id']}` | {_trace_status_text(trace_item['status'])} | {trace_item['reason']} |"
            )
        lines.append("")

    content = "\n".join(lines)
    for filename in ["result_trace.md", "result_trace.zh.md"]:
        (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = ExcelAdapter(WORKBOOK_NAME, REQUIRED_COLUMNS).load()
    missing_required = [column for column in REQUIRED_COLUMNS if column not in dataset.header_index]
    if missing_required:
        raise RuntimeError(f"缺少必需字段：{', '.join(missing_required)}")

    schema_registry = SchemaRegistry.from_file(SCHEMA_PATH, dataset.headers)
    slots = RegexExtractor().extract(DEMO_INPUT)
    verifier = RuleVerifier(schema_registry)
    classified_rules = RuleClassifier(TAXONOMY_PATH, verifier).classify(slots)
    final_executable_rules = RulePromoter(
        TAXONOMY_PATH,
        simulated_confirmation_enabled=True,
    ).final_executable_rules(classified_rules)

    raw_results = PandasExecutor().execute(
        dataset.dataframe,
        final_executable_rules,
        user_rank=slots.get("user_context", {}).get("user_rank"),
    )
    results = TraceGenerator().add_traces(
        raw_results,
        executable_rules=final_executable_rules,
        not_executed_preferences=classified_rules.get("non_executable_preferences", []),
    )
    coverage = data_coverage(dataset, REQUIRED_COLUMNS)
    rules_payload = build_rules_payload(slots, schema_registry, classified_rules, final_executable_rules)

    write_rules_json(rules_payload)
    write_filtered_results_csv(results)
    write_verification_report(dataset, rules_payload, coverage, len(results))
    write_result_trace(results)

    print(f"已写入 {OUTPUT_DIR / 'rules.json'}")
    print(f"已写入 {OUTPUT_DIR / 'verification_report.md'}")
    print(f"已写入 {OUTPUT_DIR / 'filtered_results.csv'}")
    print(f"已写入 {OUTPUT_DIR / 'result_trace.md'}")
    print(f"筛选结果数：{len(results)}")


def _operator_text(operator: Any) -> str:
    labels = {
        "eq": "等于",
        "neq": "不等于",
        "contains": "包含",
        "in_contains": "包含任一",
        "contains_any": "包含任一",
        "in": "属于",
        "not_in": "不属于",
        "<=": "不高于",
        ">=": "不低于",
        "between": "位于区间",
        "satisfies_subject_requirement": "满足选科要求",
    }
    return labels.get(str(operator), str(operator))


def _format_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _bool_text(value: Any) -> str:
    return "是" if value else "否"


def _status_text(status: Any) -> str:
    labels = {
        "pending_confirmation": "等待确认",
        "confirmable": "可确认后执行",
        "not_executable": "不可执行",
        "not_executed": "未执行",
    }
    return labels.get(str(status), str(status))


def _trace_status_text(status: Any) -> str:
    labels = {
        "pass": "通过",
        "not_executed": "未执行",
    }
    return labels.get(str(status), str(status))


if __name__ == "__main__":
    main()
