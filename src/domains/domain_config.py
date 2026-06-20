"""Domain pack loader for schema-grounded rule execution."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - JSON-compatible 配置仍可运行
    yaml = None


ROOT_DIR = Path(__file__).resolve().parents[2]
DOMAINS_DIR = ROOT_DIR / "domains"
DEFAULT_DOMAIN_ID = "admissions"


class DomainConfig:
    """读取 domain pack，并提供 canonical field 到源列的唯一入口。"""

    def __init__(self, domain_id: str, root: Path, payload: dict[str, Any]) -> None:
        self.domain_id = domain_id
        self.root = root
        self.payload = payload
        self._schema_payload: dict[str, Any] | None = None

    @classmethod
    def load(cls, domain_id: str = DEFAULT_DOMAIN_ID) -> "DomainConfig":
        return _load_domain(domain_id)

    @classmethod
    def from_path(
        cls,
        root: str | Path,
        domain_id: str | None = None,
    ) -> "DomainConfig":
        """从指定目录读取 domain pack，供生成器和测试使用。"""

        root_path = Path(root)
        path = root_path / "domain.json"
        if not path.exists():
            raise FileNotFoundError(f"Domain pack not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        resolved_domain_id = domain_id or str(
            payload.get("domain_id") or root_path.name
        )
        return cls(domain_id=resolved_domain_id, root=root_path, payload=payload)

    @property
    def schema_path(self) -> Path:
        return self._path("schema")

    @property
    def attribute_grounding_path(self) -> Path:
        return self._path("attribute_grounding")

    @property
    def rule_taxonomy_path(self) -> Path:
        return self._path("rule_taxonomy")

    @property
    def value_aliases_path(self) -> Path:
        return self._path("value_aliases")

    @property
    def answer_templates_path(self) -> Path:
        return self._path("answer_templates")

    @property
    def golden_cases_path(self) -> Path:
        return self._path("golden_cases")

    @property
    def top_result_mapping_path(self) -> Path | None:
        paths = self.payload.get("paths") or {}
        if "top_result_mapping" not in paths:
            return None
        return self.resolve_path(paths["top_result_mapping"])

    @property
    def career_decision_policy_path(self) -> Path | None:
        paths = self.payload.get("paths") or {}
        if "career_decision_policy" not in paths:
            return None
        return self.resolve_path(paths["career_decision_policy"])

    @property
    def domain_version(self) -> str:
        return str(self.payload.get("domain_version") or "1")

    @property
    def pack_status(self) -> str:
        status = str(self.payload.get("status") or "blocked")
        if status == "active":
            return "approved"
        if status in {"draft", "needs_review", "approved", "blocked"}:
            return status
        return "blocked"

    @property
    def fixture_path(self) -> Path | None:
        value = (self.payload.get("data") or {}).get("fixture_path")
        return self.resolve_path(value) if value else None

    @property
    def workbook_path(self) -> Path:
        return self.resolve_path((self.payload.get("data") or {})["workbook_path"])

    @property
    def warehouse_database_path(self) -> Path:
        return self.resolve_path(
            (self.payload.get("data") or {})["warehouse_database_path"]
        )

    @property
    def value_index_path(self) -> Path:
        return self.resolve_path((self.payload.get("data") or {})["value_index_path"])

    @property
    def table_name(self) -> str:
        return str((self.payload.get("data") or {}).get("table_name") or self.domain_id)

    @property
    def required_columns(self) -> list[str]:
        field_ids = (self.payload.get("data") or {}).get("required_field_ids") or []
        return [self.source_column(field_id) for field_id in field_ids]

    @property
    def schema_fields(self) -> dict[str, dict[str, Any]]:
        if self._schema_payload is None:
            self._schema_payload = json.loads(
                self.schema_path.read_text(encoding="utf-8")
            )
        return self._schema_payload["fields"]

    @property
    def execution(self) -> dict[str, Any]:
        return self.payload.get("execution") or {}

    @property
    def answer_templates(self) -> dict[str, Any]:
        return json.loads(self.answer_templates_path.read_text(encoding="utf-8"))

    @property
    def top_result_mapping(self) -> list[dict[str, Any]]:
        path = self.top_result_mapping_path
        if path and path.exists():
            return _load_json_like(path)
        return list(self.payload.get("top_result_mapping") or [])

    @property
    def subject_policy(self) -> dict[str, Any]:
        return self.payload.get("subject_policy") or {}

    @property
    def workbench(self) -> dict[str, Any]:
        return self.payload.get("workbench") or {}

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        root_path = self.root / path
        if root_path.exists() or str(value).startswith("fixtures/"):
            return root_path
        return ROOT_DIR / path

    def source_column(self, field_id: str) -> str:
        spec = self.schema_fields.get(field_id)
        if not spec or not spec.get("source_column"):
            raise KeyError(f"Domain {self.domain_id} has no active source column for {field_id}")
        return str(spec["source_column"])

    def source_column_or_none(self, field_id: str | None) -> str | None:
        if not field_id:
            return None
        spec = self.schema_fields.get(field_id) or {}
        source_column = spec.get("source_column")
        return str(source_column) if source_column else None

    def source_columns(self, field_ids: list[str]) -> list[str]:
        return [self.source_column(field_id) for field_id in field_ids]

    def field_id_for_source_column(self, source_column: str | None) -> str | None:
        if not source_column:
            return None
        for field_id, spec in self.schema_fields.items():
            if spec.get("source_column") == source_column:
                return field_id
        return None

    def field_label(self, field_id: str | None, fallback: str | None = None) -> str:
        if field_id:
            spec = self.schema_fields.get(field_id) or {}
            if spec.get("label"):
                return str(spec["label"])
            if spec.get("source_column"):
                return str(spec["source_column"])
        return fallback or str(field_id or "")

    def source_column_label(self, source_column: str | None) -> str:
        field_id = self.field_id_for_source_column(source_column)
        return self.field_label(field_id, fallback=source_column)

    def canonicalize_rule_field(self, rule: dict[str, Any]) -> dict[str, Any]:
        field_id = rule.get("field_id")
        source_column = self.source_column_or_none(str(field_id)) if field_id else None
        if not source_column:
            return rule
        if rule.get("field") == source_column:
            return rule
        updated = dict(rule)
        updated["field"] = source_column
        return updated

    def is_rank_field(self, field: Any) -> bool:
        rank_field_id = self.execution.get("rank_field_id")
        return bool(rank_field_id and field == self.source_column_or_none(rank_field_id))

    def _path(self, key: str) -> Path:
        paths = self.payload.get("paths") or {}
        if key not in paths:
            raise KeyError(f"Domain {self.domain_id} missing path config: {key}")
        return self.resolve_path(paths[key])


@lru_cache(maxsize=16)
def _load_domain(domain_id: str) -> DomainConfig:
    root = DOMAINS_DIR / domain_id
    path = root / "domain.json"
    if not path.exists():
        raise FileNotFoundError(f"Domain pack not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DomainConfig(domain_id=domain_id, root=root, payload=payload)


def _load_json_like(path: Path) -> Any:
    """读取 JSON/YAML 配置。"""

    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if yaml is None:
            raise
        return yaml.safe_load(text)
