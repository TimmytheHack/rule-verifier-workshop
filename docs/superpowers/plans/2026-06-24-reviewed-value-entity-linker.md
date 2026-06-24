# Reviewed Value Entity Linker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 reviewed value entity linker，防止 `深圳大学` 被误执行为 `city=深圳`，同时保持 `深圳的大学` 可执行为城市筛选。

**Architecture:** 新增纯函数式 `src/schema/value_entity_linker.py`，只依赖 `SchemaRegistry`、`SchemaValueIndex` 和用户文本，输出 accepted/suppressed/ambiguous/not-executed entity evidence。Workbench 在 legacy verified flow 的 `AttributeGrounder` 之后调用 linker，把 accepted entity links 转成 verified proposed rules，再通过现有 `RuleVerifier` 和 `_merge_verified_proposed_rules` 进入执行层。

**Tech Stack:** Python 3.11、`unittest`、DuckDB structured warehouse、现有 `SchemaRegistry` / `SchemaValueIndex` / `EvidencePack` / `WorkbenchResponse`。

---

## File Structure

- Create: `src/schema/value_entity_linker.py`
  - 定义 `EntityLinkingResult`, `ReviewedValueEntityLinker`。
  - 不执行 SQL，不读 raw Excel，不调用 LLM。
  - 只读取 `SchemaRegistry.active_fields` 和 `SchemaValueIndex.fields`。
- Create: `tests/test_value_entity_linker.py`
  - 使用内存 schema/value index payload 覆盖 span、冲突、缺索引、partial lookup。
- Create: `tests/test_workbench_value_entity_linking.py`
  - 使用 `tests.warehouse_test_utils.run_workbench_with_test_warehouse` 跑真实 Workbench flow。
- Modify: `src/api/workbench.py`
  - 在 legacy verified flow 中调用 linker。
  - 把 accepted links 转成 proposed rules，再走 `RuleVerifier.audit_proposed_rules` 和 `_merge_verified_proposed_rules`。
  - 用 suppressed links 阻止同字段同值的既有 deterministic hard rule 继续执行。
  - 把 entity linking trace 写入 legacy payload、`EvidencePack` 和 `debug_trace`。
- Modify: `src/reporting/evidence_pack.py`
  - 增加 `entity_linking` 字段，并从 `from_verified_pipeline` 传入。
- Modify: `README.md`
  - 中文说明 entity linker 的证据边界。
- Modify: `docs/api_contract.md`
  - 中文说明 `evidence_pack.entity_linking`。
- Modify: `docs/methodology_report.md`
  - 中文说明完整实体优先、子串抑制和 verifier 边界。

## Task 1: Entity Linker Unit Tests

**Files:**
- Create: `tests/test_value_entity_linker.py`
- Create in Task 2: `src/schema/value_entity_linker.py`

- [ ] **Step 1: Write failing tests for exact entity vs city substring**

Create `tests/test_value_entity_linker.py` with:

```python
from __future__ import annotations

import unittest

from src.adapters.data_warehouse import SchemaValueIndex
from src.schema.schema_registry import SchemaRegistry
from src.schema.value_entity_linker import ReviewedValueEntityLinker


class ReviewedValueEntityLinkerTest(unittest.TestCase):
    def test_university_exact_span_suppresses_city_substring(self) -> None:
        result = _link("我想进深圳大学，目前排位15000")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.accepted_links],
            [("university_name", "深圳大学")],
        )
        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.suppressed_links],
            [("city", "深圳")],
        )
        self.assertEqual(result.ambiguous_links, [])
        self.assertEqual(result.not_executed_links, [])
        self.assertEqual(result.proposed_rules[0]["field_id"], "university_name")
        self.assertEqual(result.proposed_rules[0]["operator"], "eq")
        self.assertEqual(result.proposed_rules[0]["value"], "深圳大学")
        self.assertEqual(result.proposed_rules[0]["semantic_type"], "explicit_user_fact")

    def test_city_expression_executes_city_not_university(self) -> None:
        result = _link("我想去深圳的大学，目前排位15000")

        self.assertEqual(
            [(link["field_id"], link["value"]) for link in result.accepted_links],
            [("city", "深圳")],
        )
        self.assertEqual(result.suppressed_links, [])
        self.assertEqual(result.ambiguous_links, [])
        self.assertEqual(result.proposed_rules[0]["field_id"], "city")
        self.assertEqual(result.proposed_rules[0]["operator"], "in_contains")
        self.assertEqual(result.proposed_rules[0]["value"], ["深圳"])

    def test_nearby_expression_is_not_executed(self) -> None:
        result = _link("想找深圳大学附近的学校")

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["source_text"], "深圳大学附近")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "附近/周边表达需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。",
        )

    def test_same_span_exact_match_on_two_fields_is_ambiguous(self) -> None:
        result = _link(
            "想去南方学院",
            extra_fields={
                "college_name": {
                    "source_column": "学院名称",
                    "active": True,
                    "type": "string",
                    "allowed_ops": ["eq"],
                    "lookup_complete": True,
                    "lookup_values": ["南方学院"],
                }
            },
            university_values=["南方学院"],
        )

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(len(result.ambiguous_links), 2)
        self.assertEqual(result.proposed_rules, [])

    def test_incomplete_lookup_does_not_execute_by_default(self) -> None:
        result = _link("我想进深圳大学", university_lookup_complete=False)

        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])
        self.assertEqual(result.not_executed_links[0]["field_id"], "university_name")
        self.assertEqual(
            result.not_executed_links[0]["reason"],
            "字段值索引不完整，不能直接执行实体筛选。",
        )

    def test_missing_value_index_fails_closed(self) -> None:
        registry = _registry()
        result = ReviewedValueEntityLinker(registry, None).link("我想进深圳大学")

        self.assertEqual(result.status, "value_index_unavailable")
        self.assertEqual(result.accepted_links, [])
        self.assertEqual(result.proposed_rules, [])


def _link(
    text: str,
    *,
    university_values: list[str] | None = None,
    university_lookup_complete: bool = True,
    extra_fields: dict[str, dict[str, object]] | None = None,
):
    registry = _registry(extra_fields=extra_fields)
    value_index = SchemaValueIndex(
        _value_index_payload(
            university_values=university_values or ["深圳大学"],
            university_lookup_complete=university_lookup_complete,
            extra_fields=extra_fields,
        )
    )
    return ReviewedValueEntityLinker(registry, value_index).link(text)


def _registry(
    extra_fields: dict[str, dict[str, object]] | None = None,
) -> SchemaRegistry:
    configured = {
        "university_name": {
            "source_column": "院校名称",
            "type": "string",
            "allowed_ops": ["contains", "eq"],
        },
        "city": {
            "source_column": "城市",
            "type": "string",
            "allowed_ops": ["contains", "in_contains"],
        },
        **(extra_fields or {}),
    }
    active = {
        field_id: spec
        for field_id, spec in configured.items()
        if spec.get("active", True)
    }
    return SchemaRegistry(active_fields=active, configured_fields=configured)


def _value_index_payload(
    *,
    university_values: list[str],
    university_lookup_complete: bool,
    extra_fields: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    fields = {
        "university_name": {
            "source_column": "院校名称",
            "active": True,
            "type": "string",
            "allowed_ops": ["contains", "eq"],
            "lookup_complete": university_lookup_complete,
            "lookup_values": university_values,
        },
        "city": {
            "source_column": "城市",
            "active": True,
            "type": "string",
            "allowed_ops": ["contains", "in_contains"],
            "lookup_complete": True,
            "lookup_values": ["深圳", "广州"],
        },
    }
    for field_id, spec in (extra_fields or {}).items():
        fields[field_id] = dict(spec)
    return {
        "source": {"fingerprint": "fixture-index"},
        "warehouse": {"row_count": 3},
        "fields": fields,
    }


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify import failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_value_entity_linker
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.schema.value_entity_linker'`.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_value_entity_linker.py
git commit -m "test: cover reviewed value entity linking"
```

## Task 2: Implement Pure ReviewedValueEntityLinker

**Files:**
- Create: `src/schema/value_entity_linker.py`
- Modify: `src/schema/__init__.py` only if that package already exports schema helpers; otherwise leave it unchanged.
- Test: `tests/test_value_entity_linker.py`

- [ ] **Step 1: Add implementation skeleton and result dataclass**

Create `src/schema/value_entity_linker.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.adapters.data_warehouse import SchemaValueIndex
from src.schema.schema_registry import SchemaRegistry


TEXT_FIELD_TYPES = {"string", "enum", "enum_or_category", "category"}
DEFAULT_LINKABLE_FIELDS = {
    "university_name": {"operator": "eq", "mode": "entity"},
    "city": {"operator": "in_contains", "mode": "location"},
    "major_name": {"operator": "contains_any", "mode": "major"},
}
NEARBY_TERMS = ("附近", "周边", "旁边", "那边")
LOCATION_PATTERNS = ("的大学", "市高校", "高校", "读大学", "上大学")


@dataclass(frozen=True)
class EntityLinkingResult:
    status: str
    accepted_links: list[dict[str, Any]] = field(default_factory=list)
    suppressed_links: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_links: list[dict[str, Any]] = field(default_factory=list)
    not_executed_links: list[dict[str, Any]] = field(default_factory=list)
    proposed_rules: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted_links": self.accepted_links,
            "suppressed_links": self.suppressed_links,
            "ambiguous_links": self.ambiguous_links,
            "not_executed_links": self.not_executed_links,
        }


class ReviewedValueEntityLinker:
    """用 reviewed schema/value index 解析文本实体，不执行 SQL。"""

    def __init__(
        self,
        schema_registry: SchemaRegistry,
        value_index: SchemaValueIndex | None,
        *,
        linkable_fields: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.schema_registry = schema_registry
        self.value_index = value_index
        self.linkable_fields = linkable_fields or DEFAULT_LINKABLE_FIELDS

    def link(self, text: str) -> EntityLinkingResult:
        if self.value_index is None:
            return EntityLinkingResult(status="value_index_unavailable")
        nearby = _nearby_not_executed(text)
        if nearby:
            return EntityLinkingResult(
                status="applied",
                not_executed_links=[nearby],
            )
        candidates = self._candidates(text)
        accepted, suppressed, ambiguous, not_executed = _resolve_candidates(candidates)
        proposed_rules = [_proposed_rule(index, link) for index, link in enumerate(accepted, start=1)]
        return EntityLinkingResult(
            status="applied",
            accepted_links=accepted,
            suppressed_links=suppressed,
            ambiguous_links=ambiguous,
            not_executed_links=not_executed,
            proposed_rules=proposed_rules,
        )

    def _candidates(self, text: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for field_id, policy in self.linkable_fields.items():
            field = self.schema_registry.configured_field(field_id)
            if not self.schema_registry.has_field(field_id):
                continue
            if str(field.get("type")) not in TEXT_FIELD_TYPES:
                continue
            index_field = (self.value_index.fields or {}).get(field_id) or {}
            if not index_field.get("active"):
                continue
            lookup_values = [str(value) for value in index_field.get("lookup_values") or []]
            lookup_complete = bool(index_field.get("lookup_complete"))
            if not lookup_values:
                continue
            for value in lookup_values:
                for span in _find_spans(text, value):
                    output.append(
                        _candidate_record(
                            text=text,
                            field_id=field_id,
                            field=field,
                            policy=policy,
                            value=value,
                            span=span,
                            lookup_complete=lookup_complete,
                        )
                    )
        return output
```

- [ ] **Step 2: Add helper functions**

Append to `src/schema/value_entity_linker.py`:

```python
def _candidate_record(
    *,
    text: str,
    field_id: str,
    field: dict[str, Any],
    policy: dict[str, Any],
    value: str,
    span: tuple[int, int],
    lookup_complete: bool,
) -> dict[str, Any]:
    source_text = text[span[0]:span[1]]
    mode = str(policy.get("mode") or "entity")
    executable = lookup_complete
    return {
        "source_text": source_text,
        "span": [span[0], span[1]],
        "field_id": field_id,
        "source_column": field.get("source_column"),
        "value": value,
        "op": policy.get("operator") or "eq",
        "match_type": "exact_full_span",
        "mode": mode,
        "executable": executable,
        "value_evidence": {
            "source": "schema_value_index",
            "status": "exact_match",
            "lookup_complete": lookup_complete,
            "matched_values": [value],
        },
    }


def _find_spans(text: str, value: str) -> list[tuple[int, int]]:
    if not text or not value:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(value, start)
        if index < 0:
            break
        spans.append((index, index + len(value)))
        start = index + 1
    return spans


def _nearby_not_executed(text: str) -> dict[str, Any] | None:
    for term in NEARBY_TERMS:
        index = text.find(term)
        if index < 0:
            continue
        start = max(0, index - 4)
        source_text = text[start:index + len(term)]
        return {
            "source_text": source_text,
            "field_id": None,
            "match_type": "entity_linking_boundary_required",
            "executable": False,
            "reason": "附近/周边表达需要地理距离或用户确认边界，不能直接执行为院校或城市筛选。",
        }
    return None


def _resolve_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    incomplete = [
        {
            **candidate,
            "executable": False,
            "reason": "字段值索引不完整，不能直接执行实体筛选。",
        }
        for candidate in candidates
        if not candidate.get("value_evidence", {}).get("lookup_complete")
    ]
    executable = [
        candidate
        for candidate in candidates
        if candidate.get("value_evidence", {}).get("lookup_complete")
    ]
    exact_groups: dict[tuple[int, int, str], list[dict[str, Any]]] = {}
    for candidate in executable:
        span = candidate.get("span") or []
        if len(span) != 2:
            continue
        exact_groups.setdefault((int(span[0]), int(span[1]), str(candidate.get("source_text"))), []).append(candidate)
    ambiguous = [
        item
        for group in exact_groups.values()
        if len({candidate.get("field_id") for candidate in group}) > 1
        for item in group
    ]
    ambiguous_ids = {id(item) for item in ambiguous}
    remaining = [item for item in executable if id(item) not in ambiguous_ids]
    location_candidates = [item for item in remaining if item.get("mode") == "location"]
    entity_candidates = [item for item in remaining if item.get("mode") != "location"]
    accepted: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for entity in sorted(entity_candidates, key=_candidate_sort_key):
        accepted.append({**entity, "resolution": "accepted_longest_exact_entity"})
    for location in location_candidates:
        suppressor = _containing_entity(location, accepted)
        if suppressor:
            suppressed.append(
                {
                    **location,
                    "match_type": "substring_inside_exact_entity",
                    "executable": False,
                    "resolution": f"suppressed_by_{suppressor['field_id']}_exact_full_span",
                }
            )
            continue
        if _looks_like_location_expression(location):
            accepted.append({**location, "resolution": "accepted_location_expression"})
    accepted = _dedupe_links(accepted)
    return accepted, suppressed, ambiguous, incomplete


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int]:
    span = candidate.get("span") or [0, 0]
    return (-(int(span[1]) - int(span[0])), int(span[0]))


def _containing_entity(
    location: dict[str, Any],
    accepted_entities: list[dict[str, Any]],
) -> dict[str, Any] | None:
    span = location.get("span") or []
    if len(span) != 2:
        return None
    start, end = int(span[0]), int(span[1])
    for entity in accepted_entities:
        entity_span = entity.get("span") or []
        if len(entity_span) != 2:
            continue
        if int(entity_span[0]) <= start and end <= int(entity_span[1]):
            return entity
    return None


def _looks_like_location_expression(candidate: dict[str, Any]) -> bool:
    source_text = str(candidate.get("source_text") or "")
    return any(pattern in source_text for pattern in LOCATION_PATTERNS) or source_text in {"深圳", "广州"}


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    output = []
    for link in links:
        key = (str(link.get("field_id")), str(link.get("op")), str(link.get("value")))
        if key in seen:
            continue
        output.append(link)
        seen.add(key)
    return output


def _proposed_rule(index: int, link: dict[str, Any]) -> dict[str, Any]:
    value: Any = link.get("value")
    if link.get("op") in {"in_contains", "contains_any"}:
        value = [value]
    return {
        "rule_id": f"value_entity_{index:03d}",
        "source_text": link.get("source_text"),
        "category": "deterministic",
        "field_id": link.get("field_id"),
        "field": link.get("source_column"),
        "operator": link.get("op"),
        "value": value,
        "semantic_type": "explicit_user_fact",
        "value_source": "explicit_user_fact",
        "requires_human_confirmation": False,
        "reason": "reviewed value index exact match",
        "proposed_by": "reviewed_value_entity_linker",
    }
```

- [ ] **Step 3: Run unit tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_value_entity_linker
```

Expected: all tests pass.

- [ ] **Step 4: Run compile check**

Run:

```bash
.venv/bin/python -m py_compile src/schema/value_entity_linker.py
```

Expected: exit code 0.

- [ ] **Step 5: Commit implementation**

```bash
git add src/schema/value_entity_linker.py tests/test_value_entity_linker.py
git commit -m "feat: add reviewed value entity linker"
```

## Task 3: Workbench Regression Tests

**Files:**
- Create: `tests/test_workbench_value_entity_linking.py`
- Modify in Task 4: `src/api/workbench.py`

- [ ] **Step 1: Write failing Workbench tests**

Create `tests/test_workbench_value_entity_linking.py`:

```python
from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse
from tests.workbench_contract_utils import assert_workbench_contract


class WorkbenchValueEntityLinkingTest(unittest.TestCase):
    def test_shenzhen_university_prompt_filters_university_not_city(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        response = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                soft_preferences={"prompt": prompt},
            )
        )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        filters = response["executed_filters"]
        self.assertIn(
            ("院校名称", "eq", "深圳大学"),
            [(item["field"], item["operator"], item["value"]) for item in filters],
        )
        self.assertNotIn(
            ("城市", "in_contains", ["深圳"]),
            [(item["field"], item["operator"], item["value"]) for item in filters],
        )
        self.assertTrue(response["top_results"])
        self.assertTrue(
            all(item["university_name"] == "深圳大学" for item in response["top_results"])
        )
        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(linking["status"], "applied")
        self.assertEqual(linking["accepted_links"][0]["field_id"], "university_name")
        self.assertEqual(linking["suppressed_links"][0]["field_id"], "city")

    def test_shenzhen_city_prompt_filters_city_not_university(self) -> None:
        prompt = "我想去深圳的大学，目前排位15000，帮我看看有什么专业可以选"
        response = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                soft_preferences={"prompt": prompt},
            )
        )

        assert_workbench_contract(self, response)
        filters = response["executed_filters"]
        self.assertIn(
            ("城市", "in_contains", ["深圳"]),
            [(item["field"], item["operator"], item["value"]) for item in filters],
        )
        self.assertNotIn(
            ("院校名称", "eq", "深圳大学"),
            [(item["field"], item["operator"], item["value"]) for item in filters],
        )
        self.assertTrue(response["top_results"])
        self.assertTrue(
            any(item["university_name"] != "深圳大学" for item in response["top_results"])
        )

    def test_nearby_prompt_does_not_execute_entity_link(self) -> None:
        prompt = "我想找深圳大学附近的学校，目前排位15000"
        response = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                soft_preferences={"prompt": prompt},
            )
        )

        assert_workbench_contract(self, response)
        linking = response["evidence_pack"]["entity_linking"]
        self.assertEqual(linking["accepted_links"], [])
        self.assertEqual(linking["not_executed_links"][0]["match_type"], "entity_linking_boundary_required")
        serialized_filters = str(response["executed_filters"])
        self.assertNotIn("深圳大学", serialized_filters)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_value_entity_linking
```

Expected: FAIL because `entity_linking` is absent and `深圳大学` still executes as city-only.

- [ ] **Step 3: Commit failing integration tests**

```bash
git add tests/test_workbench_value_entity_linking.py
git commit -m "test: cover workbench entity linking"
```

## Task 4: Wire Entity Linker Into Legacy Workbench

**Files:**
- Modify: `src/api/workbench.py`
- Test: `tests/test_workbench_value_entity_linking.py`

- [ ] **Step 1: Import linker and add helper call site**

In `src/api/workbench.py`, add import:

```python
from src.schema.value_entity_linker import (
    EntityLinkingResult,
    ReviewedValueEntityLinker,
)
```

In `_run_workbench`, immediately after the existing `AttributeGrounder` call assigns `attribute_grounding`, add:

```python
    entity_linking = _run_value_entity_linker(
        user_request=_compose_user_request(config),
        schema_registry=schema_registry,
        value_index=value_index,
        domain_config=domain_config,
    )
```

- [ ] **Step 2: Add `_run_value_entity_linker` helper**

Add near `_load_value_index` helpers:

```python
def _run_value_entity_linker(
    *,
    user_request: str,
    schema_registry: SchemaRegistry,
    value_index: SchemaValueIndex | None,
    domain_config: DomainConfig,
) -> EntityLinkingResult:
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return EntityLinkingResult(status="not_applicable")
    try:
        return ReviewedValueEntityLinker(schema_registry, value_index).link(user_request)
    except Exception:  # noqa: BLE001 - entity linking 失败必须 fail closed。
        return EntityLinkingResult(status="failed")
```

- [ ] **Step 3: Merge entity proposed rules through existing verifier boundary**

Replace:

```python
    proposed_rules = verifier.audit_proposed_rules(slots.get("proposed_rules", []))
```

with:

```python
    proposed_rules = verifier.audit_proposed_rules(
        [
            *slots.get("proposed_rules", []),
            *entity_linking.proposed_rules,
        ]
    )
```

After:

```python
    final_rules.extend(confirmation_state["confirmed_rules"])
```

add:

```python
    final_rules = _merge_verified_proposed_rules(
        final_rules,
        proposed_rules,
        domain_config=domain_config,
    )
```

Then replace `_merge_verified_proposed_rules` with:

```python
def _merge_verified_proposed_rules(
    final_rules: list[dict[str, Any]],
    proposed_rules: list[dict[str, Any]],
    domain_config: DomainConfig | None = None,
) -> list[dict[str, Any]]:
    domain_config = domain_config or DomainConfig.load()
    merged = list(final_rules)
    seen = {_rule_identity(rule) for rule in merged}
    for proposed in proposed_rules:
        verification = proposed.get("verification", {})
        if not verification.get("executable"):
            proposed["execution_merge_status"] = "not_mergeable"
            continue
        executable_rule = {
            "rule_id": f"e_{proposed['rule_id']}",
            "derived_from": proposed["rule_id"],
            "field": proposed.get("field"),
            "operator": proposed.get("operator"),
            "value": verification.get("normalized_value", proposed.get("value")),
            "verification_origin": "verified_proposed_rule",
        }
        identity = _rule_identity(executable_rule)
        if identity in seen:
            proposed["execution_merge_status"] = "not_merged"
            proposed["execution_merge_reason"] = "执行层已存在同等规则，提议仅保留审查记录。"
            continue
        merge_block_reason = _proposed_rule_merge_block_reason(
            proposed=proposed,
            existing_rules=merged,
            domain_config=domain_config,
        )
        if merge_block_reason:
            proposed["execution_merge_status"] = "not_merged"
            proposed["execution_merge_reason"] = merge_block_reason
            continue
        merged.append(executable_rule)
        seen.add(identity)
        proposed["execution_merge_status"] = "merged"
        proposed["execution_merge_reason"] = "字段、操作符和值已通过验证，并已进入执行层。"
    return merged
```

This keeps existing tests that call `_merge_verified_proposed_rules(final_rules, proposed_rules)` valid.

- [ ] **Step 4: Suppress deterministic rules shadowed by accepted entity links**

After the `_merge_verified_proposed_rules` call and before the `_apply_value_index_hard_filter_guard`
call, add:

```python
    final_rules = _apply_entity_linking_hard_filter_guard(
        final_rules,
        entity_linking,
    )
```

Add helper near `_apply_value_index_hard_filter_guard`:

```python
def _apply_entity_linking_hard_filter_guard(
    final_rules: list[dict[str, Any]],
    entity_linking: EntityLinkingResult,
) -> list[dict[str, Any]]:
    suppressed = _entity_linking_suppressed_values(entity_linking)
    if not suppressed:
        return final_rules
    guarded = []
    for rule in final_rules:
        updated = dict(rule)
        field = str(rule.get("field") or "")
        values = _rule_values_for_entity_guard(rule.get("value"))
        if any((field, value) in suppressed for value in values):
            updated["hard_filter_allowed"] = False
            updated["hard_filter_block_reason"] = (
                "该字段值命中被完整实体链接抑制，不能作为 hard filter 执行。"
            )
        guarded.append(updated)
    return guarded


def _entity_linking_suppressed_values(
    entity_linking: EntityLinkingResult,
) -> set[tuple[str, str]]:
    return {
        (str(link.get("source_column") or ""), str(link.get("value") or ""))
        for link in entity_linking.suppressed_links
        if link.get("source_column") and link.get("value")
    }


def _rule_values_for_entity_guard(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in (None, ""):
        return []
    return [str(value)]
```

This guard is required because existing extractors may already have produced `city=深圳`
before entity linking runs. Suppression must affect execution, not only EvidencePack trace.

- [ ] **Step 5: Add entity trace to classified rules and payload**

After `classified_rules["proposed_rules"] = proposed_rules`, add:

```python
    classified_rules["entity_linking"] = entity_linking.to_dict()
```

In `legacy_payload`, add:

```python
        "entity_linking": entity_linking.to_dict(),
```

In `_debug_trace`, add `"entity_linking"` to the keys list.

- [ ] **Step 6: Pass entity trace into EvidencePack**

Update the `EvidencePack.from_verified_pipeline` call:

```python
        entity_linking=entity_linking.to_dict(),
```

This requires Task 5 to update `EvidencePack` signature before tests pass.

- [ ] **Step 7: Run targeted tests**

Run:

```bash
.venv/bin/python -m py_compile src/api/workbench.py
.venv/bin/python -m unittest tests.test_rule_verifier
```

Expected: compile check exits 0 and `tests.test_rule_verifier` passes. `tests.test_workbench_value_entity_linking`
is intentionally completed in Task 5 after `EvidencePack` accepts `entity_linking`.

## Task 5: Add Entity Linking to EvidencePack and Display Contract

**Files:**
- Modify: `src/reporting/evidence_pack.py`
- Modify: `src/api/workbench.py`
- Test: `tests/test_workbench_value_entity_linking.py`

- [ ] **Step 1: Extend EvidencePack dataclass**

In `src/reporting/evidence_pack.py`, add field:

```python
    entity_linking: dict[str, Any] = field(default_factory=dict)
```

Add parameter to `from_verified_pipeline`:

```python
        entity_linking: dict[str, Any] | None = None,
```

In the returned `cls` constructor call, add:

```python
            entity_linking=entity_linking or {"status": "not_applicable"},
```

- [ ] **Step 2: Add response trace assertion**

Append this assertion to `test_shenzhen_university_prompt_filters_university_not_city`:

```python
        self.assertIn("entity_linking", response["evidence_pack"])
        self.assertEqual(
            response["debug_trace"]["entity_linking"]["accepted_links"][0]["value"],
            "深圳大学",
        )
```

- [ ] **Step 3: Add answer warning for suppressed city**

Do not change `TemplateReportBuilder` behavior in this task. Instead add a warning record from Workbench by appending to `legacy_payload["natural_language_report"]["warnings"]` before `_contract_success_payload`:

```python
        *[
            {
                "code": "entity_substring_suppressed",
                "severity": "info",
                "message": (
                    f"已按“{link.get('source_text')}”的完整实体匹配执行，"
                    "未把其中的地名子串作为城市筛选。"
                ),
            }
            for link in entity_linking.suppressed_links
        ],
```

If direct mutation of `report` is clearer, use:

```python
    report = {
        **report,
        "warnings": [
            *report.get("warnings", []),
            *_entity_linking_warnings(entity_linking),
        ],
    }
```

and add:

```python
def _entity_linking_warnings(
    entity_linking: EntityLinkingResult,
) -> list[dict[str, Any]]:
    return [
        {
            "code": "entity_substring_suppressed",
            "severity": "info",
            "message": (
                f"已按“{link.get('source_text')}”的完整实体匹配执行，"
                "未把其中的地名子串作为城市筛选。"
            ),
        }
        for link in entity_linking.suppressed_links
    ]
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_value_entity_linker tests.test_workbench_value_entity_linking tests.test_api_workbench tests.test_workbench_api_contract
```

Expected: all tests pass.

- [ ] **Step 5: Commit Workbench integration**

```bash
git add src/api/workbench.py src/reporting/evidence_pack.py tests/test_workbench_value_entity_linking.py
git commit -m "feat: apply reviewed value entity links in workbench"
```

## Task 6: Strengthen Safety and Regression Coverage

**Files:**
- Modify: `tests/test_value_entity_linker.py`
- Modify: `tests/test_workbench_value_entity_linking.py`
- Modify: `src/schema/value_entity_linker.py`

- [ ] **Step 1: Add test for no hardcoded university behavior**

Append to `tests/test_value_entity_linker.py`:

```python
    def test_arbitrary_index_value_can_link_without_code_change(self) -> None:
        result = _link("我想进测试理工大学", university_values=["测试理工大学"])

        self.assertEqual(result.accepted_links[0]["field_id"], "university_name")
        self.assertEqual(result.accepted_links[0]["value"], "测试理工大学")
```

- [ ] **Step 2: Add test for city substring outside entity**

Append:

```python
    def test_city_and_university_can_both_apply_when_spans_do_not_overlap(self) -> None:
        result = _link("想在深圳读中山大学", university_values=["中山大学"])

        self.assertEqual(
            sorted((link["field_id"], link["value"]) for link in result.accepted_links),
            [("city", "深圳"), ("university_name", "中山大学")],
        )
```

- [ ] **Step 3: Add Workbench assertion that warnings preserve missing context**

Append to `test_shenzhen_university_prompt_filters_university_not_city`:

```python
        warning_messages = [warning["message"] for warning in response["warnings"]]
        self.assertTrue(any("缺少科类" in message for message in warning_messages))
        self.assertTrue(any("再选科目" in message for message in warning_messages))
```

- [ ] **Step 4: Run safety tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_value_entity_linker tests.test_workbench_value_entity_linking
```

Expected: all tests pass.

- [ ] **Step 5: Commit safety coverage**

```bash
git add tests/test_value_entity_linker.py tests/test_workbench_value_entity_linking.py src/schema/value_entity_linker.py
git commit -m "test: strengthen entity linking safety cases"
```

## Task 7: Documentation Sync

**Files:**
- Modify: `README.md`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`

- [ ] **Step 1: Update README**

Add a Chinese paragraph under the Workbench or semantic capability section:

```markdown
Workbench 在 legacy verified flow 中会使用 `ReviewedValueEntityLinker` 处理 reviewed value entity。
它只依赖当前 `schema/value index` 和已审核字段，不维护硬编码学校名单。完整实体精确命中优先于内部子串：
例如 `深圳大学` 会按 `院校名称=深圳大学` 执行，并抑制内部 `城市=深圳`；而 `深圳的大学`
会按地理表达执行 `城市=深圳`。`深圳大学附近` 这类表达需要地理距离或用户确认边界，不能直接执行。
```

- [ ] **Step 2: Update API contract**

In `docs/api_contract.md`, document:

```markdown
`evidence_pack.entity_linking` 记录 reviewed value entity linker 的证据：
`status`、`accepted_links`、`suppressed_links`、`ambiguous_links` 和 `not_executed_links`。
该节点只解释实体链接，不代表绕过 `RuleVerifier`；真正执行的 filter 仍以 `executed_filters`
和 `executed_rules` 为准。
```

- [ ] **Step 3: Update methodology report**

In `docs/methodology_report.md`, add:

```markdown
`ReviewedValueEntityLinker` 解决值实体重叠问题：自然语言 span 必须先在 reviewed
`schema/value index` 中命中，才能变成 proposed rule；完整实体 exact match 会抑制内部子串命中。
这不是学校名单 hardcode，而是当前数据集的 value evidence。若 lookup 不完整或多个字段同级冲突，
系统不自动执行，必须进入确认或 not executed。
```

- [ ] **Step 4: Check docs for stale language**

Run:

```bash
rg -n "深圳大学|value entity|entity_linking|EvidencePack|schema/value index" README.md docs -S
```

Expected: hits include the new behavior and no sentence claims entity linking is unsupported after this implementation.

- [ ] **Step 5: Commit docs**

```bash
git add README.md docs/api_contract.md docs/methodology_report.md
git commit -m "docs: describe reviewed value entity linking"
```

## Task 8: Final Verification and Branch Completion

**Files:**
- No source edits unless verification finds a real issue.

- [ ] **Step 1: Compile touched Python files**

Run:

```bash
.venv/bin/python -m py_compile \
  src/schema/value_entity_linker.py \
  src/api/workbench.py \
  src/reporting/evidence_pack.py
```

Expected: exit code 0.

- [ ] **Step 2: Run focused tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_value_entity_linker \
  tests.test_workbench_value_entity_linking \
  tests.test_api_workbench \
  tests.test_workbench_api_contract \
  tests.test_rule_verifier
```

Expected: all tests pass.

- [ ] **Step 3: Run full suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: all tests pass, preserving the existing expected failure count if present.

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output, exit code 0.

- [ ] **Step 5: Inspect final status**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: worktree clean after commits; recent commits show entity linker tests, implementation, safety coverage, and docs.

- [ ] **Step 6: Request final code review**

Use `superpowers:requesting-code-review` with:

```text
DESCRIPTION: Added reviewed value entity linker and Workbench integration to resolve complete entity vs substring field ambiguity.
REQUIREMENTS: docs/superpowers/specs/2026-06-24-reviewed-value-entity-linker-design.md and this plan.
BASE_SHA: commit before Task 1
HEAD_SHA: current HEAD
```

Fix Critical and Important findings before completing.

- [ ] **Step 7: Finish branch**

Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`.

## Implementation Notes

- Do not execute entity links without `RuleVerifier` verification.
- Do not relax `_proposed_rule_merge_block_reason`; entity proposed rules must use `semantic_type=explicit_user_fact`.
- Do not add school-specific code paths such as `if value == "深圳大学"`.
- Do not add a static list of universities to source code.
- Do not execute `nearby` / `周边` expressions.
- Keep comments in project-owned source Chinese if comments are needed.
- Keep human-facing docs Chinese.
