"""运行多领域 Workbench demo acceptance cases。"""

from __future__ import annotations

import json
import math
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.generate_domain_pack import load_source_dataset
from src.adapters.data_warehouse import (
    build_structured_store,
    build_structured_store_from_dataset,
)
from src.api.dataset_service import DatasetService
from src.api.workbench import WorkbenchConfig, run_workbench
from src.domains import DomainConfig


OUTPUT_DIR = Path("outputs/demo_acceptance")
WAREHOUSE_DIR = OUTPUT_DIR / "warehouses"
REPORT_JSON_PATH = OUTPUT_DIR / "report.json"
REPORT_MD_PATH = OUTPUT_DIR / "report.md"
UPLOADED_DATASET_DIR = OUTPUT_DIR / "uploaded_datasets"
UPLOADED_SOURCE_DIR = OUTPUT_DIR / "uploaded_sources"

CONTRACT_KEYS = {
    "schema_version",
    "domain",
    "domain_version",
    "domain_pack_status",
    "status",
    "query_type",
    "query",
    "answer",
    "result_count",
    "items",
    "top_results",
    "result_sections",
    "executed_filters",
    "candidates_to_confirm",
    "confirmed_rules",
    "unconfirmed_candidates",
    "unexecuted_preferences",
    "no_schema_field_preferences",
    "rejected_confirmations",
    "warnings",
    "evidence_pack",
    "debug_trace",
}
ITEM_KEYS = {
    "item_id",
    "title",
    "subtitle",
    "primary_attributes",
    "secondary_attributes",
    "matched_filters",
    "raw",
}
EXECUTED_STATUSES = {"ok", "needs_confirmation", "no_results"}


@dataclass(frozen=True)
class DemoCase:
    case_id: str
    domain: str
    query: str
    expected_status: str
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    confirmed_candidates: list[str] = field(default_factory=list)
    acceptance_group: str = "builtin_domain_acceptance"

    def to_config(self) -> WorkbenchConfig:
        soft_preferences = {"prompt": self.query, **self.soft_preferences}
        return WorkbenchConfig(
            domain_name=self.domain,
            user_input=self.query,
            hard_filters=dict(self.hard_filters),
            soft_preferences=soft_preferences,
            extractor="regex",
            generator="template_evidence",
            confirmed_candidates=list(self.confirmed_candidates),
        )


CASES = [
    DemoCase(
        "admissions_01",
        "admissions",
        "广东物理，排位32000，想学计算机，广深优先。",
        "ok",
    ),
    DemoCase(
        "admissions_02",
        "admissions",
        "广东历史类，排位20000，想读法学。",
        "ok",
    ),
    DemoCase(
        "admissions_03",
        "admissions",
        "广东物理，排位30000，深圳，软件工程。",
        "ok",
    ),
    DemoCase(
        "admissions_04",
        "admissions",
        "广东物理，物化生，排位32000，想学计科，广深优先。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_05",
        "admissions",
        "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_06",
        "admissions",
        "广东物理，排位90000，想学网络安全，深圳。",
        "no_results",
    ),
    DemoCase(
        "admissions_07",
        "admissions",
        "广东物理，排位32000，不要中外合作。",
        "ok",
    ),
    DemoCase(
        "admissions_08",
        "admissions",
        "广东物理，排位60000，不想太贵。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_09",
        "admissions",
        "广东物理，排位32000，想冲一冲计算机。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_10",
        "admissions",
        "广东历史，排位25000，法学，预算有限。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_11",
        "admissions",
        "广东物理，排位40000，想要就业前景好。",
        "ok",
    ),
    DemoCase(
        "admissions_12",
        "admissions",
        "广东物理，排位35000，人工智能，好就业。",
        "ok",
    ),
    DemoCase(
        "admissions_13",
        "admissions",
        "广东物理，排位52000，软件工程，费用别太高。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_14",
        "admissions",
        "广东物理，排位42000，广州深圳都可以，人工智能。",
        "needs_confirmation",
    ),
    DemoCase(
        "admissions_15",
        "admissions",
        "广东历史，排位18000，广州，汉语言文学。",
        "ok",
    ),
    DemoCase(
        "admissions_16_group_detail",
        "admissions",
        "列出 2025 年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数",
        "ok",
    ),
    DemoCase(
        "admissions_17_recommendation_policy",
        "admissions",
        "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省",
        "ok",
    ),
    DemoCase(
        "housing_01",
        "housing",
        "Austin, at least 2 bedrooms, under 1900, apartment or townhouse.",
        "ok",
        hard_filters={
            "city": ["Austin"],
            "bedrooms_min": 2,
            "rent_cap": 1900,
            "property_types": ["apartment", "townhouse"],
        },
    ),
    DemoCase(
        "housing_02",
        "housing",
        "Dallas condos under 1900.",
        "ok",
        hard_filters={
            "city": ["Dallas"],
            "bedrooms_min": 1,
            "rent_cap": 1900,
            "property_types": ["condo"],
        },
    ),
    DemoCase(
        "housing_03",
        "housing",
        "Houston, at least 2 bedrooms, under 1700.",
        "ok",
        hard_filters={
            "city": ["Houston"],
            "bedrooms_min": 2,
            "rent_cap": 1700,
        },
    ),
    DemoCase(
        "housing_04",
        "housing",
        "Austin houses under 2500 with at least 3 bedrooms.",
        "ok",
        hard_filters={
            "city": ["Austin"],
            "bedrooms_min": 3,
            "rent_cap": 2500,
            "property_types": ["house"],
        },
    ),
    DemoCase(
        "housing_05",
        "housing",
        "Seattle under 1500.",
        "needs_confirmation",
        hard_filters={
            "city": ["Seattle"],
            "rent_cap": 1500,
        },
    ),
    DemoCase(
        "products_01",
        "products",
        "Audio products under 100.",
        "ok",
        hard_filters={"categories": ["audio"], "price_cap": 100},
    ),
    DemoCase(
        "products_02",
        "products",
        "Laptops under 1000 with rating at least 4.0.",
        "ok",
        hard_filters={
            "categories": ["laptop"],
            "price_cap": 1000,
            "rating_min": 4.0,
        },
    ),
    DemoCase(
        "products_03",
        "products",
        "Tablets under 500.",
        "ok",
        hard_filters={"categories": ["tablet"], "price_cap": 500},
    ),
    DemoCase(
        "products_04",
        "products",
        "Accessories under 50.",
        "ok",
        hard_filters={"categories": ["accessory"], "price_cap": 50},
    ),
    DemoCase(
        "products_05",
        "products",
        "Cameras under 100.",
        "no_results",
        hard_filters={"categories": ["camera"], "price_cap": 100},
    ),
]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    warehouse_paths = build_demo_warehouses()
    records = run_acceptance_cases(warehouse_paths)
    records.extend(run_uploaded_dataset_acceptance())
    report = build_report(records)
    REPORT_JSON_PATH.write_text(
        json.dumps(_json_ready(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(render_markdown_report(report), encoding="utf-8")
    print(f"Wrote {REPORT_MD_PATH}")
    print(f"Wrote {REPORT_JSON_PATH}")
    return 0 if report["summary"]["failed"] == 0 else 1


def build_demo_warehouses() -> dict[str, tuple[Path, Path]]:
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, tuple[Path, Path]] = {}
    for domain_id in ["admissions", "housing", "products"]:
        domain = DomainConfig.load(domain_id)
        database_path = WAREHOUSE_DIR / f"{domain_id}.duckdb"
        index_path = WAREHOUSE_DIR / f"{domain_id}_schema_value_index.json"
        if domain_id == "admissions":
            build_structured_store(
                workbook_path=domain.workbook_path,
                required_columns=domain.required_columns,
                schema_path=domain.schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name=domain.table_name,
            )
        else:
            dataset = load_source_dataset(domain.workbook_path)
            build_structured_store_from_dataset(
                dataset=dataset,
                schema_path=domain.schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name=domain.table_name,
                source_path=domain.workbook_path,
            )
        paths[domain_id] = (database_path, index_path)
    return paths


def run_acceptance_cases(
    warehouse_paths: dict[str, tuple[Path, Path]],
) -> list[dict[str, Any]]:
    def database_for_domain(domain_config: DomainConfig) -> Path:
        return warehouse_paths[domain_config.domain_id][0]

    def index_for_domain(domain_config: DomainConfig) -> Path:
        return warehouse_paths[domain_config.domain_id][1]

    records = []
    with patch("src.api.workbench._warehouse_database_path", database_for_domain):
        with patch("src.api.workbench._warehouse_value_index_path", index_for_domain):
            for case in CASES:
                response = run_workbench(case.to_config())
                records.append(record_from_response(case, response))
    return records


def record_from_response(
    case: DemoCase,
    response: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sql, params = _sql_and_params(response)
    failures = _contract_failures(case, response, sql, params)
    return {
        "case_id": case.case_id,
        "acceptance_group": case.acceptance_group,
        "domain": case.domain,
        "query": case.query,
        "expected_status": case.expected_status,
        "status": response.get("status"),
        "query_type": response.get("query_type"),
        "result_count": response.get("result_count"),
        "items": response.get("items", []),
        "top_results": response.get("top_results", []),
        "result_sections": response.get("result_sections", {}),
        "executed_filters": response.get("executed_filters", []),
        "candidates_to_confirm": response.get("candidates_to_confirm", []),
        "unexecuted_preferences": response.get("unexecuted_preferences", []),
        "sql": sql,
        "params": params,
        "evidence_pack": response.get("evidence_pack", {}),
        "answer": response.get("answer", ""),
        "pass": not failures,
        "failures": failures,
        **(extra or {}),
    }


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    domain_counts = Counter(record["domain"] for record in records)
    group_counts = Counter(record["acceptance_group"] for record in records)
    status_counts = Counter(str(record["status"]) for record in records)
    passed = sum(1 for record in records if record["pass"])
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "summary": {
            "total": len(records),
            "passed": passed,
            "failed": len(records) - passed,
            "by_domain": dict(sorted(domain_counts.items())),
            "by_acceptance_group": dict(sorted(group_counts.items())),
            "by_status": dict(sorted(status_counts.items())),
        },
        "records": records,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Demo Acceptance 验收报告",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 总记录数：`{summary['total']}`",
        f"- 通过：`{summary['passed']}`",
        f"- 失败：`{summary['failed']}`",
        f"- 按 domain 统计：`{json.dumps(summary['by_domain'], ensure_ascii=False)}`",
        f"- 按验收组统计：`{json.dumps(summary['by_acceptance_group'], ensure_ascii=False)}`",
        f"- 按 status 统计：`{json.dumps(summary['by_status'], ensure_ascii=False)}`",
        "",
        "| Case | Domain | Status | Result Count | 是否通过 |",
        "|---|---|---|---:|---:|",
    ]
    for record in report["records"]:
        pass_text = _pass_text(record)
        lines.append(
            "| {case_id} | {domain} | {status} | {count} | {pass_text} |".format(
                case_id=record["case_id"],
                domain=record["domain"],
                status=record["status"],
                count=record["result_count"],
                pass_text=pass_text,
            )
        )
    lines.append("")

    for record in report["records"]:
        pass_text = _pass_text(record)
        lines.extend(
            [
                f"## {record['case_id']} `{pass_text}`",
                "",
                f"- domain: `{record['domain']}`",
                f"- acceptance_group: `{record['acceptance_group']}`",
                f"- query: {record['query']}",
                f"- status: `{record['status']}`",
                f"- query_type: `{record['query_type']}`",
                f"- pass/fail：`{pass_text}`",
                "",
                "### items",
                _json_block(record["items"]),
                "### top_results",
                _json_block(record["top_results"]),
                "### result_sections",
                _json_block(record["result_sections"]),
                "### executed_filters",
                _json_block(record["executed_filters"]),
                "### candidates_to_confirm",
                _json_block(record["candidates_to_confirm"]),
                "### unexecuted_preferences",
                _json_block(record["unexecuted_preferences"]),
                "### SQL / params",
                _json_block({"sql": record["sql"], "params": record["params"]}),
                "### uploaded dataset flow",
                _json_block(record.get("uploaded_dataset_flow", {})),
                "### EvidencePack",
                _json_block(record["evidence_pack"]),
                "### answer",
                "",
                record["answer"],
                "",
            ]
        )
        if record["failures"]:
            lines.extend(["### failures", _json_block(record["failures"])])
    return "\n".join(lines).rstrip() + "\n"


def run_uploaded_dataset_acceptance() -> list[dict[str, Any]]:
    """跑上传数据集端到端验收，不依赖内置 admissions warehouse patch。"""

    service = DatasetService(UPLOADED_DATASET_DIR)
    sources = _write_uploaded_admissions_sources()
    uploaded_cases = [
        (
            DemoCase(
                "uploaded_dataset_01_group_detail_excel",
                "admissions",
                "列出25年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数",
                "ok",
                acceptance_group="uploaded_dataset_acceptance",
            ),
            sources["excel"],
            "ds_demo_uploaded_excel",
        ),
        (
            DemoCase(
                "uploaded_dataset_02_recommendation_csv",
                "admissions",
                "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省",
                "ok",
                acceptance_group="uploaded_dataset_acceptance",
            ),
            sources["csv"],
            "ds_demo_uploaded_csv",
        ),
    ]
    records = []
    for case, source_path, dataset_id in uploaded_cases:
        dataset_dir = UPLOADED_DATASET_DIR / dataset_id
        shutil.rmtree(dataset_dir, ignore_errors=True)
        upload = service.upload(
            filename=source_path.name,
            content=source_path.read_bytes(),
            dataset_id=dataset_id,
        )
        generated = service.generate_domain_pack(
            dataset_id,
            domain_name="admissions",
            base_domain="admissions",
        )
        approved = service.approve_domain(dataset_id)
        built = service.build_warehouse(dataset_id)
        response = service.query(
            dataset_id,
            user_input=case.query,
            soft_preferences={"prompt": case.query},
            extractor="regex",
        )
        records.append(
            record_from_response(
                case,
                response,
                extra={
                    "uploaded_dataset_flow": {
                        "dataset_id": dataset_id,
                        "upload_status": upload.get("status"),
                        "generate_status": generated.get("status"),
                        "approve_ok": approved.get("ok"),
                        "build_status": built.get("status"),
                        "source_fingerprint": upload.get("source_fingerprint"),
                    }
                },
            )
        )
    return records


def _write_uploaded_admissions_sources() -> dict[str, Path]:
    UPLOADED_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    dataframe = _uploaded_admissions_dataframe()
    excel_path = UPLOADED_SOURCE_DIR / "uploaded_admissions_acceptance.xlsx"
    csv_path = UPLOADED_SOURCE_DIR / "uploaded_admissions_acceptance.csv"
    dataframe.to_excel(excel_path, index=False)
    dataframe.to_csv(csv_path, index=False)
    return {"excel": excel_path, "csv": csv_path}


def _uploaded_admissions_dataframe() -> pd.DataFrame:
    base = {
        "批次": "本科",
        "科类": "物理",
        "选科要求": "化学",
        "学费": 6850,
        "生源地": "广东",
        "院校标签": "省内",
    }
    rows = [
            {
                **base,
                "ID": 1,
                "年份": 2024,
                "院校代码": "10590",
                "院校名称": "深圳大学",
                "院校专业组代码": "10590221",
                "专业组名称": "物理221组",
                "专业代码": "080901",
                "专业名称": "计算机科学与技术",
                "专业全称": "计算机科学与技术",
                "所在省": "广东",
                "城市": "深圳",
                "专业组最低位次1": 9000,
                "最低位次1": 8800,
                "专业组最低分1": 628,
                "最低分1": 626,
                "最高分1": 640,
                "计划人数": 30,
                "专业组计划人数": 100,
                "院校排名": 80,
            },
            {
                **base,
                "ID": 2,
                "年份": 2024,
                "院校代码": "10590",
                "院校名称": "深圳大学",
                "院校专业组代码": "10590221",
                "专业组名称": "物理221组",
                "专业代码": "080717",
                "专业名称": "人工智能",
                "专业全称": "人工智能",
                "所在省": "广东",
                "城市": "深圳",
                "专业组最低位次1": 9000,
                "最低位次1": 9100,
                "专业组最低分1": 628,
                "最低分1": 625,
                "最高分1": 638,
                "计划人数": 20,
                "专业组计划人数": 100,
                "院校排名": 80,
            },
            {
                **base,
                "ID": 3,
                "年份": 2024,
                "院校代码": "10558",
                "院校名称": "中山大学",
                "院校专业组代码": "10558219",
                "专业组名称": "物理219组",
                "专业代码": "080901",
                "专业名称": "计算机类",
                "专业全称": "计算机类",
                "所在省": "广东",
                "城市": "广州",
                "专业组最低位次1": 5000,
                "最低位次1": 5000,
                "专业组最低分1": 650,
                "最低分1": 650,
                "最高分1": 670,
                "计划人数": 40,
                "专业组计划人数": 120,
                "院校排名": 10,
            },
            {
                **base,
                "ID": 4,
                "年份": 2024,
                "院校代码": "11845",
                "院校名称": "广东工业大学",
                "院校专业组代码": "11845101",
                "专业组名称": "物理101组",
                "专业代码": "080717",
                "专业名称": "人工智能",
                "专业全称": "人工智能",
                "所在省": "广东",
                "城市": "广州",
                "专业组最低位次1": 30000,
                "最低位次1": 30000,
                "专业组最低分1": 595,
                "最低分1": 595,
                "最高分1": 610,
                "计划人数": 60,
                "专业组计划人数": 200,
                "院校排名": 120,
            },
        ]
    pilot_2025_rows = []
    for offset, row in enumerate(rows[:2], start=1):
        pilot_2025_rows.append(
            {
                **row,
                "ID": 100 + offset,
                "年份": 2025,
                "院校专业组代码": "10590225",
                "专业组名称": "物理225组",
                "专业组最低位次1": 7800,
                "最低位次1": 7600 + offset * 100,
                "专业组最低分1": 634,
                "最低分1": 632 - offset,
                "最高分1": 646 - offset,
            }
        )
    return pd.DataFrame(pilot_2025_rows + rows)


def _pass_text(record: dict[str, Any]) -> str:
    return "通过" if record["pass"] else "失败"


def _sql_and_params(response: dict[str, Any]) -> tuple[str, list[Any]]:
    evidence = response.get("evidence_pack") or {}
    execution = evidence.get("execution_summary") or {}
    if not execution:
        execution = (response.get("debug_trace") or {}).get("execution") or {}
    return str(execution.get("sql") or ""), list(execution.get("params") or [])


def _contract_failures(
    case: DemoCase,
    response: dict[str, Any],
    sql: str,
    params: list[Any],
) -> list[str]:
    failures = []
    missing = sorted(CONTRACT_KEYS - set(response))
    if missing:
        failures.append(f"missing contract keys: {', '.join(missing)}")
    if response.get("domain") != case.domain:
        failures.append(
            f"domain mismatch: expected {case.domain}, got {response.get('domain')}"
        )
    if response.get("status") != case.expected_status:
        failures.append(
            "status mismatch: expected "
            f"{case.expected_status}, got {response.get('status')}"
        )
    if response.get("domain_pack_status") != "approved":
        failures.append(
            "domain_pack_status mismatch: expected approved, "
            f"got {response.get('domain_pack_status')}"
        )
    for key in [
        "items",
        "top_results",
        "executed_filters",
        "candidates_to_confirm",
        "unexecuted_preferences",
        "warnings",
    ]:
        if not isinstance(response.get(key), list):
            failures.append(f"{key} is not a list")
    if not isinstance(response.get("evidence_pack"), dict):
        failures.append("evidence_pack is not a dict")
    if not isinstance(response.get("answer"), str):
        failures.append("answer is not a string")

    for item in response.get("items") or []:
        if not ITEM_KEYS <= set(item):
            failures.append(f"item missing keys: {sorted(ITEM_KEYS - set(item))}")
            break

    status = response.get("status")
    if status in EXECUTED_STATUSES and not sql:
        failures.append("executed status has empty SQL")
    if status in EXECUTED_STATUSES and not isinstance(params, list):
        failures.append("SQL params is not a list")
    if status == "ok" and not response.get("items"):
        failures.append("ok response has no items")
    if status == "needs_confirmation":
        warnings = response.get("warnings") or []
        has_warning = any(item.get("code") == "needs_confirmation" for item in warnings)
        if not has_warning and not response.get("candidates_to_confirm"):
            failures.append("needs_confirmation has no warning or candidates")
    if status == "no_results":
        if response.get("result_count") != 0:
            failures.append("no_results result_count is not 0")
        if response.get("items"):
            failures.append("no_results response has items")
    return failures


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        indent=2,
    ) + "\n```"


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _json_ready(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
