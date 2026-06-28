"""上传数据集的托管、审查、入仓和 Workbench 查询服务。"""

from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.generate_domain_pack import (
    generate_domain_pack as generate_draft_domain_pack,
    inspect_source_dataset,
    load_source_dataset,
)
from scripts.review_domain_pack import (
    approve_domain,
    approve_field,
    approve_op,
    block_field,
    load_review_metadata,
    summarize_domain_pack,
    validate_domain_pack,
)
from src.adapters.data_warehouse import (
    audit_data_warehouse_fingerprints,
    build_structured_store_from_dataset,
)
from src.api.workbench import WorkbenchConfig, run_workbench
from src.api.workbench_preflight import WorkbenchPreflightConfig, run_workbench_preflight
from src.domains import DomainConfig
from src.schema.schema_registry import SchemaRegistry
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.query_options import SemanticQueryOptionsBuilder
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.semantic_candidates import RuleBasedSemanticCandidateGenerator


DATASET_STATUS_VALUES = {
    "uploaded",
    "profiled",
    "draft_domain_generated",
    "needs_review",
    "approved",
    "warehouse_ready",
    "queryable",
    "blocked",
    "error",
}
DOMAIN_PACK_TEMPLATE_FILES = [
    "domain.json",
    "schema_registry.json",
    "rule_taxonomy.json",
    "attribute_grounding.json",
    "answer_templates.json",
    "golden_cases.json",
    "value_aliases.json",
    "top_result_mapping.yaml",
    "semantic_capabilities.json",
]
ADMISSIONS_SCHEMA_TEMPLATE_ID = "admissions_schema_v1"
LEGACY_ADMISSIONS_BASE_DOMAIN = "admissions"
SUPPORTED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".xls"}
RESERVED_DATASET_IDS = {"admissions", "housing", "products"}
DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,79}$")
ADMISSIONS_UPLOAD_SOURCE_COLUMN_ALIASES = {
    "group_code": ["院校专业组代码", "所属专业组"],
    "group_name": ["专业组名称", "所属专业组"],
    "major_name": ["专业名称", "专业"],
    "full_major_name": ["专业全称", "专业"],
    "school_province": ["所在省", "学校所在"],
    "plan_count": ["计划人数", "录取人数"],
    "major_min_rank_2024": ["最低位次1", "最低位次"],
    "group_min_rank_2024": ["专业组最低位次1", "最低位次"],
    "major_min_score_2024": ["最低分1", "最低分数"],
    "group_min_score_2024": ["专业组最低分1", "最低分数"],
}


def _upload_max_bytes() -> int:
    try:
        return int(float(os.getenv("UPLOAD_MAX_MB", "25")) * 1024 * 1024)
    except ValueError:
        return 25 * 1024 * 1024


MAX_UPLOAD_BYTES = _upload_max_bytes()
WARNING_ROW_LIMIT = 100_000
ERROR_ROW_LIMIT = 250_000
WARNING_COLUMN_LIMIT = 200
ERROR_COLUMN_LIMIT = 500


@dataclass
class DatasetServiceError(ValueError):
    """面向 API 的结构化错误。"""

    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


class DatasetService:
    """把 CLI 能力接成可复用的上传数据集产品流。"""

    def __init__(self, root: str | Path = "outputs/uploaded_datasets") -> None:
        self.root = Path(root)

    def upload(
        self,
        *,
        filename: str,
        content: bytes,
        dataset_id: str | None = None,
        sheet_name: str | None = None,
    ) -> dict[str, Any]:
        """保存 CSV/Excel，并返回路径安全 dataset_id 和 source fingerprint。"""

        warnings = self._validate_upload_bytes(filename, content)
        source_fingerprint = _bytes_fingerprint(content)
        dataset_id = dataset_id or _generated_dataset_id(filename, source_fingerprint)
        self._validate_dataset_id(dataset_id)
        dataset_dir = self._dataset_dir(dataset_id)
        if dataset_dir.exists():
            raise DatasetServiceError(
                code="dataset_exists",
                message=f"dataset_id 已存在：{dataset_id}",
                status_code=409,
            )

        source_dir = dataset_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=False)
        source_path = source_dir / _safe_filename(filename)
        source_path.write_bytes(content)
        inspection = self._inspect_source(source_path, sheet_name=sheet_name)
        warnings.extend(inspection["warnings"])
        metadata = {
            "dataset_id": dataset_id,
            "status": "uploaded",
            "domain_pack_status": "blocked",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "original_filename": filename,
            "source_path": str(source_path),
            "source_fingerprint": source_fingerprint,
            "sheet_name": inspection["sheet_name"],
            "sheet_summaries": inspection["sheet_summaries"],
            "detected_header_row": inspection["detected_header_row"],
            "header_detection_status": inspection["header_detection_status"],
            "original_column_mapping": inspection["original_column_mapping"],
            "row_count": inspection["row_count"],
            "column_count": inspection["column_count"],
            "warnings": warnings,
            "errors": [],
            "history": [],
        }
        _append_history(metadata, "uploaded", {"filename": filename})
        self._save_metadata(metadata)
        return self._public_metadata(metadata)

    def generate_domain_pack(
        self,
        dataset_id: str,
        *,
        domain_name: str | None = None,
        base_domain: str | None = None,
        template_id: str | None = None,
        llm: str = "off",
    ) -> dict[str, Any]:
        """生成 draft pack；template_id 可复用已审查字段模板。"""

        metadata = self._load_metadata(dataset_id)
        source_path = Path(metadata["source_path"])
        base_domain = base_domain or None
        template_id = _resolve_domain_template_id(template_id, base_domain)
        domain_name = (
            domain_name
            or _domain_name_for_template(template_id)
            or base_domain
            or f"uploaded_{dataset_id}"
        )
        domain_name = _safe_domain_name(domain_name)
        output_root = self._dataset_dir(dataset_id) / "domain_packs"
        result = generate_draft_domain_pack(
            source_path=source_path,
            domain_name=domain_name,
            output_root=output_root,
            llm=llm,
            sheet_name=metadata.get("sheet_name"),
        )
        _set_domain_status(result.domain_dir, "needs_review")
        if template_id:
            self._apply_domain_template(
                domain_dir=result.domain_dir,
                template_id=template_id,
                source_path=source_path,
            )
        profile = _load_json(result.schema_profile_path)
        _append_history(metadata, "profiled", {"row_count": result.row_count})
        _append_history(metadata, "draft_domain_generated", {"domain": domain_name})
        _append_history(metadata, "needs_review", {"domain": domain_name})
        metadata.update(
            {
                "status": "needs_review",
                "domain_name": domain_name,
                "base_domain": base_domain,
                "domain_template_id": template_id,
                "domain_dir": str(result.domain_dir),
                "domain_pack_status": "needs_review",
                "schema_profile_path": str(result.schema_profile_path),
                "schema_value_index_path": str(result.value_index_path),
                "ingestion_summary_path": str(result.ingestion_summary_path),
                "warehouse_database_path": str(
                    DomainConfig.from_path(result.domain_dir, domain_name)
                    .warehouse_database_path
                ),
                "updated_at": _utc_now(),
            }
        )
        self._save_metadata(metadata)
        return {
            **self._public_metadata(metadata),
            "profile": profile,
            "domain_pack": result.to_dict(),
        }

    def profile(self, dataset_id: str) -> dict[str, Any]:
        """返回 schema profile 中可审查的字段事实。"""

        metadata = self._load_metadata(dataset_id)
        path = metadata.get("schema_profile_path")
        if not path or not Path(path).exists():
            raise DatasetServiceError(
                code="profile_not_generated",
                message="请先生成 draft domain pack。",
                status_code=409,
            )
        profile = _load_json(path)
        expected_source_columns = _semantic_expected_source_columns(metadata)
        dataset = load_source_dataset(
            metadata["source_path"],
            sheet_name=metadata.get("sheet_name"),
        )
        capability_graph_object = DatasetCapabilityGraph.from_dataset(
            dataset,
            expected_source_columns=expected_source_columns,
        )
        capability_graph = capability_graph_object.to_dict()
        semantic_query_options: dict[str, Any] = {}
        semantic_mapping_candidates: dict[str, Any] = {
            "rule_based": [],
            "llm": {
                "status": "not_available",
                "reason": "domain pack not generated",
                "candidates": [],
                "rejected_candidates": [],
            },
        }
        if metadata.get("domain_dir") and metadata.get("domain_name"):
            domain_config = DomainConfig.from_path(
                Path(metadata["domain_dir"]),
                metadata["domain_name"],
            )
            schema_registry = SchemaRegistry.from_domain(
                domain_config,
                list(dataset.dataframe.columns),
            )
            registry = ReviewedMappingRegistry.from_domain(
                domain_config,
                capability_graph_object,
            )
            semantic_query_options = SemanticQueryOptionsBuilder(
                registry,
                schema_registry=schema_registry,
            ).build()
            semantic_mapping_candidates = {
                "rule_based": [
                    {**candidate, "status": "candidate_only"}
                    for candidate in RuleBasedSemanticCandidateGenerator.from_domain(
                        domain_config
                    ).generate(capability_graph_object)
                ],
                "llm": {
                    "status": "not_run",
                    "reason": (
                        "LLM semantic mapping candidates require explicit probe "
                        "or admin action."
                    ),
                    "candidates": [],
                    "rejected_candidates": [],
                },
            }
        return {
            "dataset_id": dataset_id,
            "status": metadata["status"],
            "domain_name": metadata.get("domain_name"),
            "domain_pack_status": metadata.get("domain_pack_status"),
            "capability_level": metadata.get("capability_level")
            or _default_capability_level(metadata),
            "recommendation_readiness": metadata.get("recommendation_readiness")
            or _default_recommendation_readiness(metadata),
            "source_fingerprint": metadata["source_fingerprint"],
            "row_count": profile.get("row_count"),
            "column_count": profile.get("column_count"),
            "sheet_name": (profile.get("source") or {}).get("sheet_name"),
            "sheet_summaries": (profile.get("source") or {}).get(
                "sheet_summaries",
                [],
            ),
            "detected_header_row": (profile.get("source") or {}).get(
                "detected_header_row"
            ),
            "header_detection_status": (profile.get("source") or {}).get(
                "header_detection_status"
            ),
            "fields": [
                _profile_field(column)
                for column in profile.get("columns", [])
            ],
            "capability_graph": capability_graph,
            "semantic_query_options": semantic_query_options,
            "semantic_mapping_candidates": semantic_mapping_candidates,
            "warnings": metadata.get("warnings", []),
        }

    def list_datasets(self) -> dict[str, Any]:
        """列出本机托管数据源，不暴露本地文件路径。"""

        datasets: list[dict[str, Any]] = []
        if not self.root.exists():
            return {"datasets": datasets}
        for child in sorted(self.root.iterdir(), key=lambda path: path.name):
            if not child.is_dir():
                continue
            metadata_path = child / "dataset.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = _load_json(metadata_path)
                if not isinstance(metadata, dict):
                    continue
                if metadata.get("status") not in DATASET_STATUS_VALUES:
                    continue
                raw_dataset_id = metadata.get("dataset_id")
                if not raw_dataset_id:
                    continue
                dataset_id = str(raw_dataset_id)
                self._validate_dataset_id(dataset_id, allow_reserved=False)
                if self._dataset_dir(dataset_id).resolve() != child.resolve():
                    continue
            except (DatasetServiceError, OSError, ValueError, json.JSONDecodeError):
                continue
            datasets.append(_dataset_list_item(metadata))
        return {"datasets": datasets}

    def review_summary(self, dataset_id: str) -> dict[str, Any]:
        """返回 review UI 所需的字段、seed ops 和风险摘要。"""

        metadata = self._load_metadata(dataset_id)
        domain_dir = self._domain_dir(metadata)
        summary = summarize_domain_pack(domain_dir)
        profile = _load_json(metadata["schema_profile_path"]) if metadata.get("schema_profile_path") else {}
        profile_by_source = {
            column.get("source_column"): column
            for column in profile.get("columns", [])
            if column.get("source_column")
        }
        fields = []
        for field in summary["fields"]:
            profile_column = profile_by_source.get(field.get("source_column")) or {}
            risk_flags = sorted(
                set(_risk_flags(field)) | set(_risk_flags(profile_column))
            )
            fields.append(
                {
                    **field,
                    "risk_flags": risk_flags,
                    "seed_ops": field.get("candidate_allowed_ops") or [],
                    "admissions_semantics": profile_column.get(
                        "admissions_semantics",
                        {},
                    ),
                    "special_plan_risk": profile_column.get(
                        "special_plan_risk",
                        {},
                    ),
                }
            )
        required_fields = _required_field_status(metadata, summary, profile)
        return {
            "dataset_id": dataset_id,
            "status": metadata["status"],
            "domain_pack_status": summary["domain_pack_status"],
            "reviewable_fields": fields,
            "required_fields": required_fields,
            "risky_fields": [field for field in fields if field["risk_flags"]],
            "missing_fields": [
                item
                for item in required_fields
                if not item["present"]
            ],
            "summary": summary,
        }

    def approve_field(
        self,
        dataset_id: str,
        field_id: str,
        *,
        reviewed_by: str = "api_reviewer",
        note: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._load_metadata(dataset_id)
        result = approve_field(
            self._domain_dir(metadata),
            field_id,
            reviewed_by=reviewed_by,
            note=note,
            write=True,
        )
        self._sync_review_metadata(metadata)
        return _review_result_payload(dataset_id, result)

    def approve_op(
        self,
        dataset_id: str,
        field_id: str,
        op: str,
        *,
        reviewed_by: str = "api_reviewer",
        note: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._load_metadata(dataset_id)
        result = approve_op(
            self._domain_dir(metadata),
            field_id,
            op,
            reviewed_by=reviewed_by,
            note=note,
            write=True,
        )
        self._sync_review_metadata(metadata)
        return _review_result_payload(dataset_id, result)

    def block_field(
        self,
        dataset_id: str,
        field_id: str,
        *,
        reviewed_by: str = "api_reviewer",
        note: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._load_metadata(dataset_id)
        result = block_field(
            self._domain_dir(metadata),
            field_id,
            reviewed_by=reviewed_by,
            note=note,
            write=True,
        )
        self._sync_review_metadata(metadata)
        return _review_result_payload(dataset_id, result)

    def approve_domain(
        self,
        dataset_id: str,
        *,
        title_field: str | None = None,
        primary_fields: list[str] | None = None,
        sort_field: str | None = None,
        default_safe_sort: bool = False,
        reviewed_by: str = "api_reviewer",
        note: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._load_metadata(dataset_id)
        domain_dir = self._domain_dir(metadata)
        if _uses_admissions_schema_template(metadata):
            result = self._approve_template_domain(
                domain_dir=domain_dir,
                title_field=title_field or "university_name",
                primary_fields=primary_fields
                or ["group_code", "major_name", "city"],
                reviewed_by=reviewed_by,
                note=note,
            )
        else:
            if default_safe_sort and (not title_field or not primary_fields):
                defaults = self._auto_review_generic_domain(
                    domain_dir=domain_dir,
                    reviewed_by=reviewed_by,
                    note=note,
                )
                title_field = title_field or defaults.get("title_field")
                primary_fields = primary_fields or defaults.get("primary_fields")
                sort_field = sort_field or defaults.get("sort_field")
            result = _review_result_payload(
                dataset_id,
                approve_domain(
                    domain_dir,
                    title_field=title_field,
                    primary_fields=primary_fields or [],
                    sort_field=sort_field,
                    default_safe_sort=default_safe_sort,
                    reviewed_by=reviewed_by,
                    note=note,
                    write=True,
                ),
            )
        if "dataset_id" not in result:
            result = {"dataset_id": dataset_id, **result}
        if not result["ok"]:
            return result
        _append_history(metadata, "approved", {"domain": metadata["domain_name"]})
        metadata.update(
            {
                "status": "approved",
                "domain_pack_status": "approved",
                "updated_at": _utc_now(),
            }
        )
        self._save_metadata(metadata)
        return result

    def _auto_review_generic_domain(
        self,
        *,
        domain_dir: Path,
        reviewed_by: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        summary = summarize_domain_pack(domain_dir)
        for field in summary.get("fields", []):
            field_id = field.get("field_id")
            if not field_id or field.get("reviewed"):
                continue
            approve_field(
                domain_dir,
                str(field_id),
                reviewed_by=reviewed_by,
                note=note or "一键导入自动审查：仅批准后端判定安全的字段和操作。",
                write=True,
            )

        refreshed = summarize_domain_pack(domain_dir)
        approved_fields = [
            field
            for field in refreshed.get("fields", [])
            if field.get("reviewed") and field.get("approved_ops")
        ]
        title_field = _auto_title_field(approved_fields)
        primary_fields = _auto_primary_fields(approved_fields, title_field)
        sort_field = _auto_sort_field(approved_fields)
        return {
            "title_field": title_field,
            "primary_fields": primary_fields,
            "sort_field": sort_field,
        }

    def build_warehouse(self, dataset_id: str) -> dict[str, Any]:
        """基于 approved domain pack 构建 DuckDB 和 schema/value index。"""

        metadata = self._load_metadata(dataset_id)
        with _warehouse_build_lock(self._dataset_dir(dataset_id)):
            metadata = self._load_metadata(dataset_id)
            domain_dir = self._domain_dir(metadata)
            domain = DomainConfig.from_path(domain_dir, metadata["domain_name"])
            if domain.pack_status != "approved":
                raise DatasetServiceError(
                    code="domain_not_approved",
                    message="未 approved 的 domain pack 不能构建 queryable warehouse。",
                    status_code=409,
                )
            dataset = load_source_dataset(
                metadata["source_path"],
                sheet_name=metadata.get("sheet_name"),
            )
            build_result = _build_warehouse_atomic(
                dataset=dataset,
                domain=domain,
                source_path=metadata["source_path"],
                summary_path=domain_dir / "ingestion_summary.json",
            )
            audit = audit_data_warehouse_fingerprints(
                workbook_path=domain.workbook_path,
                database_path=domain.warehouse_database_path,
                index_path=domain.value_index_path,
                table_name=domain.table_name,
            )
            _append_history(metadata, "warehouse_ready", build_result.to_dict())
            status = "queryable" if audit["ok"] else "blocked"
            _append_history(metadata, status, {"warehouse_audit": audit})
            metadata.update(
                {
                    "status": status,
                    "warehouse_database_path": str(domain.warehouse_database_path),
                    "schema_value_index_path": str(domain.value_index_path),
                    "ingestion_summary_path": str(domain_dir / "ingestion_summary.json"),
                    "updated_at": _utc_now(),
                }
            )
            self._save_metadata(metadata)
            return {
                **self._public_metadata(metadata),
                "warehouse": build_result.to_dict(),
                "warehouse_audit": audit,
            }

    def query(
        self,
        dataset_id: str,
        *,
        user_input: str,
        hard_filters: dict[str, Any] | None = None,
        soft_preferences: dict[str, Any] | None = None,
        extractor: str = "regex",
        generator: str = "template_evidence",
        model: str = "deepseek-v4-flash",
        planner_mode: str = "auto",
        confirmed_candidates: list[str] | None = None,
        domain_name: str | None = None,
    ) -> dict[str, Any]:
        """使用 uploaded dataset 对 WorkbenchResponse contract 运行查询。"""

        metadata = self._load_metadata(dataset_id)
        domain_name = domain_name or metadata.get("domain_name")
        if not domain_name:
            raise DatasetServiceError(
                code="domain_pack_missing",
                message="请先生成并审查 domain pack。",
                status_code=409,
            )
        soft = {"prompt": user_input, **(soft_preferences or {})}
        config = WorkbenchConfig(
            user_input=user_input,
            hard_filters=hard_filters or {},
            soft_preferences=soft,
            extractor=extractor,
            generator=generator,
            model=model,
            planner_mode=planner_mode,
            confirmed_candidates=confirmed_candidates or [],
            domain_name=domain_name,
            domain_path=str(self._domain_dir(metadata)),
            dataset_id=dataset_id,
        )
        return run_workbench(config)

    def preflight(
        self,
        dataset_id: str,
        *,
        user_input: str,
        hard_filters: dict[str, Any] | None = None,
        soft_preferences: dict[str, Any] | None = None,
        model: str = "deepseek-v4-flash",
        planner_mode: str = "llm_semantic",
        domain_name: str | None = None,
    ) -> dict[str, Any]:
        """对 uploaded dataset 主查询做查询前检查。"""

        metadata = self._load_metadata(dataset_id)
        domain_name = domain_name or metadata.get("domain_name")
        if not domain_name:
            raise DatasetServiceError(
                code="domain_pack_missing",
                message="请先生成并审查 domain pack。",
                status_code=409,
            )
        domain_dir = self._domain_dir(metadata)
        config = WorkbenchPreflightConfig(
            user_input=user_input,
            hard_filters=hard_filters or {},
            soft_preferences={"prompt": user_input, **(soft_preferences or {})},
            model=model,
            planner_mode=planner_mode,
            domain_name=domain_name,
            domain_path=str(domain_dir),
            dataset_id=dataset_id,
        )
        return run_workbench_preflight(
            config,
            domain_config=DomainConfig.from_path(domain_dir, domain_name),
        )

    def _load_metadata(self, dataset_id: str) -> dict[str, Any]:
        self._validate_dataset_id(dataset_id, allow_reserved=False)
        path = self._metadata_path(dataset_id)
        if not path.exists():
            raise DatasetServiceError(
                code="dataset_not_found",
                message=f"dataset 不存在：{dataset_id}",
                status_code=404,
            )
        return _load_json(path)

    def _save_metadata(self, metadata: dict[str, Any]) -> None:
        metadata["updated_at"] = _utc_now()
        path = self._metadata_path(metadata["dataset_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _metadata_path(self, dataset_id: str) -> Path:
        return self._dataset_dir(dataset_id) / "dataset.json"

    def _dataset_dir(self, dataset_id: str) -> Path:
        self._validate_dataset_id(dataset_id, allow_reserved=False)
        root = self.root.resolve()
        path = (root / dataset_id).resolve()
        if root != path and root not in path.parents:
            raise DatasetServiceError(
                code="unsafe_dataset_id",
                message="dataset_id 不能包含路径穿越。",
                status_code=400,
            )
        return path

    def _domain_dir(self, metadata: dict[str, Any]) -> Path:
        path = metadata.get("domain_dir")
        if not path:
            raise DatasetServiceError(
                code="domain_pack_missing",
                message="请先生成 domain pack。",
                status_code=409,
            )
        domain_dir = Path(path)
        dataset_dir = self._dataset_dir(metadata["dataset_id"]).resolve()
        resolved = domain_dir.resolve()
        if dataset_dir != resolved and dataset_dir not in resolved.parents:
            raise DatasetServiceError(
                code="unsafe_domain_path",
                message="domain pack 路径不在托管 dataset 目录下。",
                status_code=400,
            )
        return resolved

    def _validate_dataset_id(
        self,
        dataset_id: str,
        *,
        allow_reserved: bool = False,
    ) -> None:
        if not DATASET_ID_PATTERN.fullmatch(str(dataset_id or "")):
            raise DatasetServiceError(
                code="unsafe_dataset_id",
                message="dataset_id 只能包含字母、数字、下划线或连字符。",
                status_code=400,
            )
        if not allow_reserved and dataset_id in RESERVED_DATASET_IDS:
            raise DatasetServiceError(
                code="reserved_dataset_id",
                message="上传 dataset_id 不能覆盖内置 domain。",
                status_code=400,
            )

    def _validate_upload_bytes(
        self,
        filename: str,
        content: bytes,
    ) -> list[dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise DatasetServiceError(
                code="unsupported_extension",
                message=f"不支持的上传格式：{suffix}",
                status_code=400,
            )
        if not content:
            raise DatasetServiceError(
                code="empty_upload",
                message="上传文件为空。",
                status_code=400,
            )
        if len(content) > MAX_UPLOAD_BYTES:
            raise DatasetServiceError(
                code="upload_too_large",
                message="上传文件超过大小限制。",
                status_code=413,
                details={
                    "size_bytes": len(content),
                    "max_size_bytes": MAX_UPLOAD_BYTES,
                },
            )
        return [
            {
                "code": "upload_received",
                "severity": "info",
                "message": "文件已保存到托管数据目录。",
                "size_bytes": len(content),
                "extension": suffix,
            }
        ]

    def _inspect_source(
        self,
        source_path: Path,
        *,
        sheet_name: str | None,
    ) -> dict[str, Any]:
        try:
            inspection = inspect_source_dataset(source_path, sheet_name=sheet_name)
        except ValueError as exc:
            raise DatasetServiceError(
                code="source_inspection_failed",
                message=str(exc),
                status_code=400,
            ) from exc
        dataset = inspection.dataset
        row_count = len(dataset.dataframe)
        column_count = len(dataset.headers)
        warnings = list(inspection.warnings)
        if row_count > ERROR_ROW_LIMIT:
            raise DatasetServiceError(
                code="too_many_rows",
                message="上传文件行数超过安全限制。",
                details={"row_count": row_count, "limit": ERROR_ROW_LIMIT},
            )
        if column_count > ERROR_COLUMN_LIMIT:
            raise DatasetServiceError(
                code="too_many_columns",
                message="上传文件列数超过安全限制。",
                details={"column_count": column_count, "limit": ERROR_COLUMN_LIMIT},
            )
        if row_count > WARNING_ROW_LIMIT:
            warnings.append(
                _warning(
                    "large_row_count",
                    "上传文件行数较多，生成 profile 和 warehouse 可能较慢。",
                    row_count=row_count,
                )
            )
        if column_count > WARNING_COLUMN_LIMIT:
            warnings.append(
                _warning(
                    "large_column_count",
                    "上传文件列数较多，请重点审查字段映射。",
                    column_count=column_count,
                )
            )
        return {
            "sheet_name": dataset.sheet_name,
            "sheet_summaries": inspection.sheet_summaries,
            "detected_header_row": inspection.detected_header_row,
            "header_detection_status": inspection.header_detection_status,
            "original_column_mapping": inspection.original_column_mapping,
            "row_count": row_count,
            "column_count": column_count,
            "warnings": warnings,
        }

    def _apply_domain_template(
        self,
        *,
        domain_dir: Path,
        template_id: str,
        source_path: Path,
    ) -> None:
        if template_id != ADMISSIONS_SCHEMA_TEMPLATE_ID:
            raise DatasetServiceError(
                code="unsupported_domain_template",
                message=f"暂不支持领域模板：{template_id}",
                status_code=400,
            )
        source = Path("domains/admissions")
        for filename in DOMAIN_PACK_TEMPLATE_FILES:
            shutil.copy2(source / filename, domain_dir / filename)
        domain_path = domain_dir / "domain.json"
        payload = _load_json(domain_path)
        warehouse_dir = domain_dir / "warehouse"
        payload["status"] = "needs_review"
        payload["review_required"] = True
        payload["data"]["workbook_path"] = str(source_path)
        payload["data"]["warehouse_database_path"] = str(
            warehouse_dir / "admissions.duckdb"
        )
        payload["data"]["value_index_path"] = str(
            warehouse_dir / "schema_value_index.json"
        )
        payload["data"]["table_name"] = "admissions"
        _write_json(domain_path, payload)
        self._adapt_admissions_template_source_columns(domain_dir)
        self._seed_template_review(domain_dir)

    def _adapt_admissions_template_source_columns(self, domain_dir: Path) -> None:
        profile = _load_json(domain_dir / "schema_profile.json")
        available_columns = {
            str(column.get("source_column"))
            for column in profile.get("columns") or []
            if column.get("source_column")
        }
        if not available_columns:
            return
        schema_path = domain_dir / "schema_registry.json"
        schema = _load_json(schema_path)
        fields = schema.get("fields") or {}
        changed = False
        for field_id, candidates in ADMISSIONS_UPLOAD_SOURCE_COLUMN_ALIASES.items():
            spec = fields.get(field_id)
            if not spec:
                continue
            current = spec.get("source_column")
            if current in available_columns:
                continue
            replacement = next(
                (candidate for candidate in candidates if candidate in available_columns),
                None,
            )
            if not replacement:
                continue
            spec["source_column"] = replacement
            spec["label"] = replacement
            note = str(spec.get("notes") or "")
            suffix = f"上传表列名适配：{current or '未配置'} -> {replacement}。"
            spec["notes"] = f"{note} {suffix}".strip()
            changed = True
        if changed:
            _write_json(schema_path, schema)

    def _seed_template_review(self, domain_dir: Path) -> None:
        domain = _load_json(domain_dir / "domain.json")
        schema = _load_json(domain_dir / "schema_registry.json")
        reviewed_fields = {}
        approved_ops = {}
        for field_id, spec in (schema.get("fields") or {}).items():
            if spec.get("status") == "missing" or not spec.get("source_column"):
                continue
            ops = list(spec.get("allowed_ops") or [])
            reviewed_fields[field_id] = {
                "status": "approved_template_seed",
                "approved_ops": ops,
                "reviewed_by": ADMISSIONS_SCHEMA_TEMPLATE_ID,
                "reviewed_at": _utc_now(),
                "note": "复用已审查 admissions 字段模板；数据行只来自上传文件，上传源仍需 approve-domain。",
            }
            if ops:
                approved_ops[field_id] = ops
        review = load_review_metadata(domain_dir)
        review.update(
            {
                "domain": "admissions",
                "domain_version": str(domain.get("domain_version") or "1"),
                "domain_pack_status": "needs_review",
                "domain_template_id": ADMISSIONS_SCHEMA_TEMPLATE_ID,
                "reviewed_fields": reviewed_fields,
                "approved_ops": approved_ops,
                "review_notes": [
                    "该托管 pack 复用 admissions_schema_v1 字段模板。",
                    "模板不读取内置 admissions 数据表行。",
                    "approve-domain 前仍不能执行 SQL。",
                ],
                "reviewed_at": _utc_now(),
                "reviewed_by": ADMISSIONS_SCHEMA_TEMPLATE_ID,
            }
        )
        _append_review_history(
            review,
            "seed-template-review",
            ADMISSIONS_SCHEMA_TEMPLATE_ID,
            {"domain_template_id": ADMISSIONS_SCHEMA_TEMPLATE_ID},
        )
        _write_yaml(domain_dir / "review.yaml", review)

    def _approve_template_domain(
        self,
        *,
        domain_dir: Path,
        title_field: str,
        primary_fields: list[str],
        reviewed_by: str,
        note: str | None,
    ) -> dict[str, Any]:
        validation = validate_domain_pack(domain_dir)
        domain = _load_json(domain_dir / "domain.json")
        schema = _load_json(domain_dir / "schema_registry.json")
        failures = [
            item["message"] for item in validation["checks"] if not item["ok"]
        ]
        if title_field not in schema.get("fields", {}):
            failures.append(f"title field 不存在：{title_field}")
        for field_id in primary_fields:
            if field_id not in schema.get("fields", {}):
                failures.append(f"primary field 不存在：{field_id}")
        if failures:
            return {
                "ok": False,
                "written": False,
                "message": "approve-domain checks failed",
                "payload": {"failures": failures},
            }
        review = load_review_metadata(domain_dir)
        review["domain_pack_status"] = "approved"
        review["item_mapping"] = {
            "title_field_id": title_field,
            "primary_attribute_field_ids": primary_fields,
        }
        review["sort_policy"] = {
            "sort_field_id": None,
            "default_safe_sort": True,
        }
        _append_review_history(
            review,
            "approve-domain",
            reviewed_by,
            {
                "title_field": title_field,
                "primary_fields": primary_fields,
                "default_safe_sort": True,
                "note": note,
            },
        )
        review["reviewed_at"] = _utc_now()
        review["reviewed_by"] = reviewed_by
        domain["status"] = "approved"
        domain["review_required"] = False
        _write_json(domain_dir / "domain.json", domain)
        _write_yaml(domain_dir / "review.yaml", review)
        return {
            "ok": True,
            "written": True,
            "message": "approved domain admissions uploaded dataset",
            "payload": {
                "domain": "admissions",
                "domain_pack_status": "approved",
                "review": review,
            },
        }

    def _sync_review_metadata(self, metadata: dict[str, Any]) -> None:
        domain_dir = self._domain_dir(metadata)
        review = load_review_metadata(domain_dir)
        metadata["domain_pack_status"] = review["domain_pack_status"]
        metadata["updated_at"] = _utc_now()
        self._save_metadata(metadata)

    def _public_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        keys = [
            "dataset_id",
            "status",
            "domain_name",
            "base_domain",
            "domain_template_id",
            "domain_pack_status",
            "source_fingerprint",
            "sheet_name",
            "sheet_summaries",
            "detected_header_row",
            "header_detection_status",
            "original_column_mapping",
            "row_count",
            "column_count",
            "source_path",
            "domain_dir",
            "warehouse_database_path",
            "schema_profile_path",
            "schema_value_index_path",
            "ingestion_summary_path",
            "warnings",
            "errors",
            "history",
            "created_at",
            "updated_at",
        ]
        return {key: metadata.get(key) for key in keys if key in metadata}


def _profile_field(column: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_id": column.get("field_id"),
        "source_column": column.get("source_column"),
        "dtype": column.get("dtype"),
        "inferred_type": column.get("inferred_type"),
        "role": column.get("role"),
        "null_rate": column.get("null_rate"),
        "unique_count": column.get("unique_count"),
        "sample_values": column.get("sample_values", []),
        "numeric": column.get("numeric"),
        "risk_flags": _risk_flags(column),
        "candidate_allowed_ops": column.get("candidate_allowed_ops", []),
        "filter_policy": column.get("filter_policy"),
        "admissions_semantics": column.get("admissions_semantics", {}),
        "special_plan_risk": column.get("special_plan_risk", {}),
    }


def _risk_flags(field: dict[str, Any]) -> list[str]:
    flags = []
    if field.get("pii_risk"):
        flags.append("pii")
    if field.get("high_cardinality"):
        flags.append("high_cardinality")
    if field.get("type") == "long_text" or field.get("inferred_type") == "long_text":
        flags.append("text")
    if (field.get("special_plan_risk") or {}).get("needs_schema_approval"):
        flags.append("special_plan_needs_schema_approval")
    seed_ops = field.get("seed_ops") or field.get("candidate_allowed_ops") or []
    if any(op in {"contains", "contains_any"} for op in seed_ops):
        flags.append("text_filter_needs_review")
    return flags


def _review_result_payload(dataset_id: str, result: Any) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "ok": result.ok,
        "written": result.written,
        "message": result.message,
        "payload": result.payload,
    }


def _dataset_list_item(metadata: dict[str, Any]) -> dict[str, Any]:
    warning_summary = _safe_issue_summary(metadata.get("warnings", []))
    error_summary = _safe_issue_summary(metadata.get("errors", []))
    item = {
        "dataset_id": metadata.get("dataset_id"),
        "status": metadata.get("status"),
        "domain_name": metadata.get("domain_name"),
        "domain_pack_status": metadata.get("domain_pack_status"),
        "capability_level": metadata.get("capability_level")
        or _default_capability_level(metadata),
        "recommendation_readiness": metadata.get("recommendation_readiness")
        or _default_recommendation_readiness(metadata),
        "source_fingerprint": metadata.get("source_fingerprint"),
        "original_filename": _safe_original_filename(
            metadata.get("original_filename")
        ),
        "row_count": metadata.get("row_count"),
        "column_count": metadata.get("column_count"),
        "sheet_name": metadata.get("sheet_name"),
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
        "warning_count": warning_summary["count"],
        "error_count": error_summary["count"],
        "warning_codes": warning_summary["codes"],
        "error_codes": error_summary["codes"],
    }
    return {key: value for key, value in item.items() if value is not None}


def _auto_title_field(fields: list[dict[str, Any]]) -> str | None:
    if not fields:
        return None
    return _best_field(
        fields,
        [
            _field_name_contains("name", "名称", "学校", "院校", "title", "标题"),
            _field_name_contains("code", "代码", "编号", "id"),
            _field_role_is("identifier"),
            _field_type_is("enum"),
        ],
    )


def _auto_primary_fields(
    fields: list[dict[str, Any]],
    title_field: str | None,
) -> list[str]:
    candidates = [field for field in fields if field.get("field_id") != title_field]
    ordered_ids = [
        field_id
        for field_id in [
            _matching_field(candidates, [_field_type_is("enum")]),
            _matching_field(candidates, [_field_role_is("metric")]),
            _matching_field(candidates, [_field_role_is("identifier")]),
        ]
        if field_id
    ]
    ordered_ids = _unique_strings(ordered_ids)
    for field in candidates:
        field_id = str(field.get("field_id") or "")
        if field_id and field_id not in ordered_ids:
            ordered_ids.append(field_id)
        if len(ordered_ids) >= 3:
            break
    if not ordered_ids and title_field:
        return [title_field]
    return ordered_ids[:3]


def _matching_field(
    fields: list[dict[str, Any]],
    predicates: list[Any],
) -> str | None:
    for predicate in predicates:
        for field in fields:
            if predicate(field):
                return str(field.get("field_id"))
    return None


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _auto_sort_field(fields: list[dict[str, Any]]) -> str | None:
    sortable = [
        field
        for field in fields
        if "sort" in (field.get("approved_ops") or [])
    ]
    return _best_field(
        sortable,
        [
            _field_name_contains("rank", "位次", "排名"),
            _field_name_contains("score", "分数"),
            _field_role_is("metric"),
        ],
    )


def _best_field(
    fields: list[dict[str, Any]],
    predicates: list[Any],
) -> str | None:
    for predicate in predicates:
        for field in fields:
            if predicate(field):
                return str(field.get("field_id"))
    if fields:
        return str(fields[0].get("field_id"))
    return None


def _field_name_contains(*needles: str) -> Any:
    lowered_needles = [needle.lower() for needle in needles]

    def predicate(field: dict[str, Any]) -> bool:
        text = " ".join(
            str(field.get(key) or "")
            for key in ["field_id", "source_column"]
        ).lower()
        return any(needle in text for needle in lowered_needles)

    return predicate


def _field_role_is(role: str) -> Any:
    return lambda field: field.get("role") == role


def _field_type_is(field_type: str) -> Any:
    return lambda field: field.get("type") == field_type


def _safe_issue_summary(entries: Any) -> dict[str, Any]:
    if not isinstance(entries, list):
        return {"count": 0, "codes": []}
    codes = sorted(
        {
            code
            for entry in entries
            if isinstance(entry, dict)
            for code in [entry.get("code")]
            if _is_safe_issue_code(code)
        }
    )
    return {"count": len(entries), "codes": codes}


def _is_safe_issue_code(code: Any) -> bool:
    return isinstance(code, str) and bool(re.fullmatch(r"[A-Za-z0-9_.-]+", code))


def _safe_original_filename(filename: Any) -> str | None:
    if filename is None:
        return None
    normalized = str(filename).replace("\\", "/")
    return Path(normalized).name


def _default_capability_level(metadata: dict[str, Any]) -> str:
    if metadata.get("status") != "queryable":
        return "profile_only"
    if _uses_admissions_schema_template(metadata):
        return "admissions_filterable"
    return "filterable"


def _default_recommendation_readiness(metadata: dict[str, Any]) -> str:
    if metadata.get("status") != "queryable":
        return "not_ready"
    return (
        "candidate_list"
        if _uses_admissions_schema_template(metadata)
        else "not_applicable"
    )


def _resolve_domain_template_id(
    template_id: str | None,
    base_domain: str | None,
) -> str | None:
    template_id = template_id or None
    base_domain = base_domain or None
    if base_domain and base_domain != LEGACY_ADMISSIONS_BASE_DOMAIN:
        raise DatasetServiceError(
            code="unsupported_base_domain",
            message=f"暂不支持复用 base_domain：{base_domain}",
            status_code=400,
        )
    legacy_template_id = (
        ADMISSIONS_SCHEMA_TEMPLATE_ID
        if base_domain == LEGACY_ADMISSIONS_BASE_DOMAIN
        else None
    )
    if template_id and template_id != ADMISSIONS_SCHEMA_TEMPLATE_ID:
        raise DatasetServiceError(
            code="unsupported_domain_template",
            message=f"暂不支持领域模板：{template_id}",
            status_code=400,
        )
    if template_id and legacy_template_id and template_id != legacy_template_id:
        raise DatasetServiceError(
            code="domain_template_conflict",
            message="template_id 与 base_domain 不一致。",
            status_code=400,
        )
    return template_id or legacy_template_id


def _domain_name_for_template(template_id: str | None) -> str | None:
    if template_id == ADMISSIONS_SCHEMA_TEMPLATE_ID:
        return "admissions"
    return None


def _uses_admissions_schema_template(metadata: dict[str, Any]) -> bool:
    return (
        metadata.get("domain_template_id") == ADMISSIONS_SCHEMA_TEMPLATE_ID
        or metadata.get("base_domain") == LEGACY_ADMISSIONS_BASE_DOMAIN
    )


def _required_field_status(
    metadata: dict[str, Any],
    summary: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not _uses_admissions_schema_template(metadata):
        return []
    domain_dir = metadata.get("domain_dir")
    if not domain_dir:
        return []
    domain = DomainConfig.from_path(domain_dir, metadata.get("domain_name"))
    fields = domain.payload.get("query_planner", {})
    required_ids = []
    group_detail = fields.get("group_detail_report") or {}
    recommendation = fields.get("recommendation") or {}
    required_ids.extend((group_detail.get("fields") or {}).values())
    metric = (group_detail.get("default_metric") or {}).get("field_id")
    if metric:
        required_ids.append(metric)
    required_ids.extend(
        field_id
        for field_id in (recommendation.get("fields") or {}).values()
        if field_id not in {
            "cooperation_type",
            "school_country_or_region",
            "special_plan_type",
        }
    )
    if profile is None and metadata.get("schema_profile_path"):
        profile = _load_json(metadata["schema_profile_path"])
    actual_source_columns = {
        column.get("source_column")
        for column in (profile or {}).get("columns", [])
        if column.get("source_column")
    }
    if not actual_source_columns:
        actual_source_columns = {
            field.get("source_column")
            for field in summary.get("fields", [])
            if field.get("source_column")
        }
    statuses = []
    for field_id in sorted(set(str(item) for item in required_ids if item)):
        source_column = domain.source_column_or_none(field_id)
        statuses.append(
            {
                "field_id": field_id,
                "source_column": source_column,
                "present": bool(source_column and source_column in actual_source_columns),
            }
        )
    return statuses


def _semantic_expected_source_columns(metadata: dict[str, Any]) -> list[str]:
    domain_dir = metadata.get("domain_dir")
    domain_name = metadata.get("domain_name")
    if not domain_dir or not domain_name:
        return []
    domain = DomainConfig.from_path(domain_dir, domain_name)
    capability_profile = (
        domain.semantic_capabilities.get("capability_profile") or {}
    )
    return [
        str(item)
        for item in capability_profile.get("expected_source_columns") or []
    ]


def _set_domain_status(domain_dir: Path, status: str) -> None:
    domain_path = domain_dir / "domain.json"
    payload = _load_json(domain_path)
    payload["status"] = status
    payload["review_required"] = True
    _write_json(domain_path, payload)
    domain_yaml = domain_dir / "domain.yaml"
    if domain_yaml.exists():
        data = yaml.safe_load(domain_yaml.read_text(encoding="utf-8")) or {}
        data["status"] = status
        _write_yaml(domain_yaml, data)


def _append_history(
    metadata: dict[str, Any],
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    if status not in DATASET_STATUS_VALUES:
        raise ValueError(f"Unsupported dataset status: {status}")
    metadata.setdefault("history", []).append(
        {
            "status": status,
            "at": _utc_now(),
            "details": _json_ready(details or {}),
        }
    )
    metadata["status"] = status


def _build_warehouse_atomic(
    *,
    dataset: Any,
    domain: DomainConfig,
    source_path: str,
    summary_path: Path,
) -> Any:
    warehouse_dir = domain.warehouse_database_path.parent
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".warehouse_build_",
        dir=str(warehouse_dir),
    ) as directory:
        temp_dir = Path(directory)
        temp_database = temp_dir / domain.warehouse_database_path.name
        temp_index = temp_dir / domain.value_index_path.name
        temp_summary = temp_dir / summary_path.name
        temp_result = build_structured_store_from_dataset(
            dataset=dataset,
            schema_path=domain.schema_path,
            database_path=temp_database,
            index_path=temp_index,
            table_name=domain.table_name,
            source_path=source_path,
        )
        final_result = replace(
            temp_result,
            database_path=domain.warehouse_database_path,
            index_path=domain.value_index_path,
        )
        temp_summary.write_text(
            json.dumps(final_result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_database, domain.warehouse_database_path)
        os.replace(temp_index, domain.value_index_path)
        os.replace(temp_summary, summary_path)
        return final_result


@contextmanager
def _warehouse_build_lock(dataset_dir: Path):
    lock_path = dataset_dir / ".warehouse_build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _append_review_history(
    review: dict[str, Any],
    action: str,
    reviewed_by: str,
    details: dict[str, Any],
) -> None:
    review.setdefault("approval_history", []).append(
        {
            "action": action,
            "reviewed_by": reviewed_by,
            "reviewed_at": _utc_now(),
            "details": _json_ready(details),
        }
    )


def _warning(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "warning",
        "message": message,
        **details,
    }


def _generated_dataset_id(filename: str, fingerprint: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", Path(filename).stem.lower()).strip("_")
    stem = stem[:24] or "dataset"
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"ds_{timestamp}_{fingerprint[:12]}_{stem}"[:80]


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._-")
    suffix = Path(name).suffix.lower()
    return f"{stem or 'source'}{suffix}"


def _safe_domain_name(domain_name: str) -> str:
    if domain_name == "admissions":
        return domain_name
    value = domain_name.strip().lower().replace("-", "_")
    value = re.sub(r"[^a-z0-9_]+", "_", value).strip("_")
    if not value or not value[0].isalpha():
        value = f"uploaded_{value}"
    return value[:64]


def _bytes_fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_yaml(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        yaml.safe_dump(
            _json_ready(payload),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
    return value
