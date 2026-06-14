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
from src.domains import DomainConfig


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
]
SUPPORTED_UPLOAD_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".xls"}
RESERVED_DATASET_IDS = {"admissions", "housing", "products"}
DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,79}$")


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


@dataclass(frozen=True)
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
        llm: str = "off",
    ) -> dict[str, Any]:
        """生成 draft pack；base_domain=admissions 时复用已审查招生模板。"""

        metadata = self._load_metadata(dataset_id)
        source_path = Path(metadata["source_path"])
        base_domain = base_domain or None
        domain_name = domain_name or base_domain or f"uploaded_{dataset_id}"
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
        if base_domain:
            self._apply_base_domain_template(
                domain_dir=result.domain_dir,
                base_domain=base_domain,
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
        return {
            "dataset_id": dataset_id,
            "status": metadata["status"],
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
            "warnings": metadata.get("warnings", []),
        }

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
        if metadata.get("base_domain") == "admissions":
            result = self._approve_template_domain(
                domain_dir=domain_dir,
                title_field=title_field or "university_name",
                primary_fields=primary_fields
                or ["group_code", "major_name", "city"],
                reviewed_by=reviewed_by,
                note=note,
            )
        else:
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
            confirmed_candidates=confirmed_candidates or [],
            domain_name=domain_name,
            domain_path=str(self._domain_dir(metadata)),
            dataset_id=dataset_id,
        )
        return run_workbench(config)

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

    def _apply_base_domain_template(
        self,
        *,
        domain_dir: Path,
        base_domain: str,
        source_path: Path,
    ) -> None:
        if base_domain != "admissions":
            raise DatasetServiceError(
                code="unsupported_base_domain",
                message=f"暂不支持复用 base_domain：{base_domain}",
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
        self._seed_template_review(domain_dir)

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
                "reviewed_by": "built_in_admissions_template",
                "reviewed_at": _utc_now(),
                "note": "复用已审查 admissions domain pack；上传源仍需 approve-domain。",
            }
            if ops:
                approved_ops[field_id] = ops
        review = load_review_metadata(domain_dir)
        review.update(
            {
                "domain": "admissions",
                "domain_version": str(domain.get("domain_version") or "1"),
                "domain_pack_status": "needs_review",
                "reviewed_fields": reviewed_fields,
                "approved_ops": approved_ops,
                "review_notes": [
                    "该托管 pack 复用内置 admissions runtime 配置。",
                    "approve-domain 前仍不能执行 SQL。",
                ],
                "reviewed_at": _utc_now(),
                "reviewed_by": "built_in_admissions_template",
            }
        )
        _append_review_history(
            review,
            "seed-template-review",
            "built_in_admissions_template",
            {"base_domain": "admissions"},
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


def _required_field_status(
    metadata: dict[str, Any],
    summary: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if metadata.get("base_domain") != "admissions":
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
