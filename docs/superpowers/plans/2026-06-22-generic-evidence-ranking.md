# Generic Evidence Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把推荐链路从 admissions-specific 排序升级为 LLM 提出证据需求和 RankingPlan、系统验证、通用排序引擎执行、EvidencePack 约束回答。

**Architecture:** 上传表先生成完整字段事实和 one-hot/boolean 统计；DeepSeek 只提出字段语义候选、证据需求分类和结构化 RankingPlan rationale。系统验证字段、operation、value、priority 和外部知识需求后，用 SQL 召回候选集，再用 GenericRankingEngine 对 verified criteria 排序并生成结构化 criterion evidence。

**Tech Stack:** Python `unittest`、Pydantic v2、DuckDB、现有 `DeepSeekClient`、`DatasetService`、`DatasetCapabilityGraph`、`ReviewedMappingRegistry`、`WorkbenchResponse`、EvidencePack。

---

## 文件结构

- Modify: `src/semantic/capability_graph.py`
  - 扩展 `CapabilityField`，加入完整 profile 事实：`top_values`、`parse_success_rate`、`boolean_profile`、低基数字段完整值集合。
- Create: `src/semantic/llm_semantic_candidates.py`
  - DeepSeek 根据列名、字段事实、canonical fields 提出 `source_column -> canonical_field_id` 候选；只输出候选，不激活映射。
- Create: `src/semantic/evidence_requirements.py`
  - 定义 EvidenceRequirement 分类模型和 DeepSeek classifier，拆分 `table_field`、`knowledge_base_or_reviewed_field`、`reviewed_ranking_policy`、`user_boundary`、`unsupported`。
- Create: `src/semantic/ranking_plan.py`
  - 定义 `RankingPlan`、`RankingCriterion`、`ExcludedCriterion`、允许的通用 operation。
- Create: `src/semantic/ranking_verifier.py`
  - 校验 LLM RankingPlan：字段必须 reviewed，operation 必须通用且字段 op/类型兼容，value 必须来自用户或 value index，缺字段/KB/policy 进入 excluded。
- Create: `src/semantic/generic_ranking.py`
  - 通用排序引擎，执行 verified criteria，输出 sorted rows、criterion evidence、excluded rows。
- Modify: `src/semantic/admissions_recommendation.py`
  - 保留 SQL 候选集召回；可选接收 verified RankingPlan；没有 verified plan 时标记为候选列表，不称作推荐排序。
- Modify: `src/api/workbench.py`
  - Workbench 接收可注入 `semantic_ranking_plan` / `evidence_requirements`；live LLM 只在 uploaded dataset 且显式开启时运行；EvidencePack 写入 ranking evidence。
- Modify: `src/api/dataset_service.py`
  - `profile()` 增加非执行型 `semantic_mapping_candidates`，默认只返回 rule-based 和字段事实；live LLM 候选只通过显式 probe 或后续 endpoint 触发。
- Modify: `scripts/run_semantic_capability_probe.py`
  - 增加 `--live-semantic-candidates`、`--live-ranking-plan`，用于人工验证 DeepSeek 候选和 RankingPlan，不默认调用 LLM。
- Docs: `README.md`、`docs/api_contract.md`、`docs/methodology_report.md`
  - 更新候选集优先、RankingPlan verifier、evidence-only explanation 边界。

## Task 1: 完整字段 profile 与 one-hot/boolean 统计

**Files:**
- Modify: `src/semantic/capability_graph.py`
- Test: `tests/test_semantic_capability_graph.py`

- [ ] **Step 1: 写失败测试**

Add this test to `tests/test_semantic_capability_graph.py`:

```python
    def test_graph_profiles_boolean_like_sparse_columns_and_top_values(self) -> None:
        from pathlib import Path

        import pandas as pd
        from src.adapters.excel_adapter import ExcelDataSet

        dataframe = pd.DataFrame(
            [
                {"专业": "计算机科学与技术", "是否中外合作": "否", "最低位次": "10242"},
                {"专业": "人工智能", "是否中外合作": "否", "最低位次": "15000"},
                {"专业": "软件工程", "是否中外合作": "是", "最低位次": "18000"},
                {"专业": "人工智能", "是否中外合作": "", "最低位次": "无"},
            ]
        )
        dataset = ExcelDataSet(
            workbook_path=Path("fixture.xlsx"),
            sheet_name="Sheet1",
            header_row=0,
            headers=list(dataframe.columns),
            header_index={name: index for index, name in enumerate(dataframe.columns)},
            dataframe=dataframe,
        )

        graph = DatasetCapabilityGraph.from_dataset(dataset)
        cooperation = graph.fields["是否中外合作"].to_dict()
        rank = graph.fields["最低位次"].to_dict()
        major = graph.fields["专业"].to_dict()

        self.assertEqual(cooperation["boolean_profile"]["true_count"], 1)
        self.assertEqual(cooperation["boolean_profile"]["false_count"], 2)
        self.assertEqual(cooperation["boolean_profile"]["null_count"], 1)
        self.assertEqual(cooperation["boolean_profile"]["other_count"], 0)
        self.assertAlmostEqual(cooperation["boolean_profile"]["true_rate"], 0.25)
        self.assertIn("boolean_preferred_value", cooperation["candidate_ops"])
        self.assertEqual(rank["parse_success_rate"], 0.75)
        self.assertEqual(major["top_values"][0], {"value": "人工智能", "count": 2})
        self.assertTrue(major["distinct_values_complete"])
        self.assertIn("计算机科学与技术", major["distinct_values"])
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_capability_graph.SemanticCapabilityGraphTest.test_graph_profiles_boolean_like_sparse_columns_and_top_values
```

Expected: FAIL with missing `boolean_profile` / `parse_success_rate` / `top_values`.

- [ ] **Step 3: 扩展字段 profile 数据结构**

Modify `CapabilityField` in `src/semantic/capability_graph.py`:

```python
@dataclass(frozen=True)
class CapabilityField:
    """数据源字段的可执行能力画像。"""

    source_column: str
    inferred_type: str
    non_null_count: int
    missing_rate: float
    distinct_count: int
    sample_values: list[str]
    numeric_min: float | None
    numeric_max: float | None
    candidate_ops: list[str]
    parse_success_rate: float
    top_values: list[dict[str, Any]]
    distinct_values: list[str]
    distinct_values_complete: bool
    boolean_profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "inferred_type": self.inferred_type,
            "non_null_count": self.non_null_count,
            "missing_rate": self.missing_rate,
            "distinct_count": self.distinct_count,
            "sample_values": self.sample_values,
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "candidate_ops": self.candidate_ops,
            "parse_success_rate": self.parse_success_rate,
            "top_values": self.top_values,
            "distinct_values": self.distinct_values,
            "distinct_values_complete": self.distinct_values_complete,
            "boolean_profile": self.boolean_profile,
        }
```

- [ ] **Step 4: 实现完整统计 helper**

Add these helpers in `src/semantic/capability_graph.py`:

```python
LOW_CARDINALITY_VALUE_LIMIT = 200
BOOLEAN_TRUE_VALUES = {"是", "有", "1", "true", "TRUE", "True", "Y", "y", "yes", "YES"}
BOOLEAN_FALSE_VALUES = {"否", "无", "0", "false", "FALSE", "False", "N", "n", "no", "NO"}


def _top_values(values: list[str], limit: int = 20) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"value": value, "count": count} for value, count in ordered[:limit]]


def _top_count_items(counts: dict[str, int], limit: int = 20) -> list[dict[str, Any]]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"value": value, "count": count} for value, count in ordered[:limit]]


def _boolean_profile(values: list[str], row_count: int) -> dict[str, Any]:
    true_count = 0
    false_count = 0
    other_values: dict[str, int] = {}
    for value in values:
        normalized = value.strip()
        if normalized in BOOLEAN_TRUE_VALUES:
            true_count += 1
        elif normalized in BOOLEAN_FALSE_VALUES:
            false_count += 1
        else:
            other_values[normalized] = other_values.get(normalized, 0) + 1
    null_count = max(row_count - len(values), 0)
    other_count = sum(other_values.values())
    return {
        "true_count": true_count,
        "false_count": false_count,
        "null_count": null_count,
        "other_count": other_count,
        "true_rate": true_count / row_count if row_count else 0.0,
        "false_rate": false_count / row_count if row_count else 0.0,
        "other_values": _top_count_items(other_values, limit=5),
        "is_boolean_like": (true_count + false_count > 0 and other_count == 0),
    }
```

- [ ] **Step 5: 更新 `_field_profile` 和 `_candidate_ops`**

Replace the return block in `_field_profile` with:

```python
    boolean_profile = _boolean_profile(non_empty, row_count)
    candidate_ops = _candidate_ops(inferred_type)
    if boolean_profile["is_boolean_like"] and "boolean_preferred_value" not in candidate_ops:
        candidate_ops = [*candidate_ops, "boolean_preferred_value"]
    distinct_values_for_output = distinct_values[:LOW_CARDINALITY_VALUE_LIMIT]
    return CapabilityField(
        source_column=source_column,
        inferred_type=inferred_type,
        non_null_count=non_null_count,
        missing_rate=(row_count - non_null_count) / row_count if row_count else 0.0,
        distinct_count=distinct_count,
        sample_values=distinct_values[:5],
        numeric_min=min(numeric_values) if numeric_values else None,
        numeric_max=max(numeric_values) if numeric_values else None,
        candidate_ops=candidate_ops,
        parse_success_rate=(
            len(numeric_values) / non_null_count if non_null_count else 0.0
        ),
        top_values=_top_values(non_empty),
        distinct_values=distinct_values_for_output,
        distinct_values_complete=distinct_count <= LOW_CARDINALITY_VALUE_LIMIT,
        boolean_profile=boolean_profile,
    )
```

Keep `_candidate_ops` generic:

```python
def _candidate_ops(inferred_type: str) -> list[str]:
    if inferred_type == "number":
        return ["eq", "<=", ">=", "between", "sort", "numeric_distance_to_user_value", "numeric_higher_is_better", "numeric_lower_is_better"]
    if inferred_type == "enum_or_category":
        return ["eq", "in", "not_in", "contains", "contains_any", "sort", "equals_preferred_value", "in_preferred_set"]
    return ["contains", "contains_any", "eq", "sort", "text_match"]
```

- [ ] **Step 6: 运行 profile 测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_capability_graph
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/semantic/capability_graph.py tests/test_semantic_capability_graph.py
git commit -m "feat: enrich semantic field profiles"
```

## Task 2: LLM 语义字段候选生成器

**Files:**
- Create: `src/semantic/llm_semantic_candidates.py`
- Modify: `src/semantic/__init__.py`
- Test: `tests/test_llm_semantic_candidates.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_llm_semantic_candidates.py`:

```python
from __future__ import annotations

import unittest
from dataclasses import dataclass

from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.llm_semantic_candidates import DeepSeekSemanticCandidateGenerator
from tests.semantic_test_utils import new_admissions_dataset


@dataclass(frozen=True)
class _FakeResponse:
    payload: dict
    usage: dict | None = None


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.system_prompt = ""
        self.user_prompt = ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> _FakeResponse:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return _FakeResponse(payload=self.payload, usage={"total_tokens": 12})


class DeepSeekSemanticCandidateGeneratorTest(unittest.TestCase):
    def test_generates_validated_candidates_without_activating_mapping(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        domain = DomainConfig.load("admissions")
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.87,
                        "evidence": ["列名包含最低位次", "样例是正整数排名"],
                        "risks": [],
                        "proposed_ops": ["between", "sort"],
                    },
                    {
                        "source_column": "不存在列",
                        "canonical_field_id": "city",
                        "confidence": 0.9,
                        "evidence": ["无效候选"],
                        "risks": [],
                        "proposed_ops": ["eq"],
                    },
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0]["source_column"], "最低位次")
        self.assertEqual(result.candidates[0]["canonical_field_id"], "major_min_rank")
        self.assertEqual(result.candidates[0]["status"], "candidate_only")
        self.assertEqual(result.rejected_candidates[0]["reason"], "unknown_source_column")
        self.assertIn("canonical_fields", client.user_prompt)
        self.assertNotIn("raw_sql", client.user_prompt)
        self.assertEqual(result.usage["total_tokens"], 12)

    def test_rejects_raw_sql_payload(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        domain = DomainConfig.load("admissions")
        client = _FakeClient(
            {
                "candidates": [
                    {
                        "source_column": "最低位次",
                        "canonical_field_id": "major_min_rank",
                        "confidence": 0.9,
                        "evidence": ["x"],
                        "risks": [],
                        "proposed_ops": ["sort"],
                        "raw_sql": "SELECT * FROM admissions",
                    }
                ]
            }
        )

        result = DeepSeekSemanticCandidateGenerator(client).generate(
            graph=graph,
            domain_config=domain,
        )

        self.assertEqual(result.candidates, [])
        self.assertEqual(result.rejected_candidates[0]["reason"], "raw_sql_forbidden")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_llm_semantic_candidates
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: 实现 LLM candidate generator**

Create `src/semantic/llm_semantic_candidates.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.query_ast import _reject_raw_sql_key


class JSONChatClient(Protocol):
    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """返回带 payload 和 usage 的 JSON 响应。"""


@dataclass(frozen=True)
class SemanticCandidateGenerationResult:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


class DeepSeekSemanticCandidateGenerator:
    """DeepSeek 只提出字段语义候选，不写 reviewed mapping。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def generate(self, *, graph: Any, domain_config: Any) -> SemanticCandidateGenerationResult:
        response = self.client.chat_json(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(graph=graph, domain_config=domain_config),
        )
        payload = getattr(response, "payload", response)
        usage = dict(getattr(response, "usage", {}) or {})
        return _validate_payload(payload, graph=graph, domain_config=domain_config, usage=usage)
```

Append helper functions:

```python
def _system_prompt() -> str:
    return (
        "你是结构化表格字段语义候选生成器。"
        "只能提出候选 source_column 到 canonical_field_id 的映射；"
        "不能生成 SQL，不能声称字段已审核，不能输出可执行规则。"
        "只返回 JSON object。"
    )


def _user_prompt(*, graph: Any, domain_config: Any) -> str:
    canonical_fields = sorted(
        (domain_config.semantic_capabilities.get("reviewed_mappings") or {}).keys()
    )
    columns = [
        {
            "source_column": field.source_column,
            "inferred_type": field.inferred_type,
            "missing_rate": field.missing_rate,
            "distinct_count": field.distinct_count,
            "sample_values": field.sample_values,
            "numeric_min": field.numeric_min,
            "numeric_max": field.numeric_max,
            "candidate_ops": field.candidate_ops,
            "top_values": field.top_values[:5],
            "boolean_profile": field.boolean_profile,
        }
        for field in graph.fields.values()
    ]
    return json.dumps(
        {
            "task": "propose_semantic_mapping_candidates",
            "canonical_fields": canonical_fields,
            "columns": columns,
            "output_schema": {
                "candidates": [
                    {
                        "source_column": "当前表里的列名",
                        "canonical_field_id": "canonical field",
                        "confidence": 0.0,
                        "evidence": ["只引用列名、类型和样例"],
                        "risks": ["歧义或需要 review 的原因"],
                        "proposed_ops": ["候选操作"],
                    }
                ]
            },
        },
        ensure_ascii=False,
    )
```

Append validation:

```python
def _validate_payload(
    payload: Any,
    *,
    graph: Any,
    domain_config: Any,
    usage: dict[str, int],
) -> SemanticCandidateGenerationResult:
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    canonical_fields = set(
        (domain_config.semantic_capabilities.get("reviewed_mappings") or {}).keys()
    )
    raw_candidates = payload.get("candidates") if isinstance(payload, dict) else []
    for raw in raw_candidates or []:
        if not isinstance(raw, dict):
            rejected.append({"candidate": raw, "reason": "invalid_candidate_shape"})
            continue
        try:
            _reject_raw_sql_key(raw, "semantic mapping candidate")
        except ValueError:
            rejected.append({"candidate": _safe_candidate(raw), "reason": "raw_sql_forbidden"})
            continue
        source_column = str(raw.get("source_column") or "")
        field_id = str(raw.get("canonical_field_id") or "")
        if source_column not in graph.fields:
            rejected.append({"candidate": _safe_candidate(raw), "reason": "unknown_source_column"})
            continue
        if field_id not in canonical_fields:
            rejected.append({"candidate": _safe_candidate(raw), "reason": "unknown_canonical_field"})
            continue
        graph_ops = set(graph.fields[source_column].candidate_ops)
        proposed_ops = [
            str(op)
            for op in raw.get("proposed_ops") or []
            if str(op) in graph_ops or str(op) == "satisfies_subject_requirement"
        ]
        candidates.append(
            {
                "source_column": source_column,
                "canonical_field_id": field_id,
                "confidence": float(raw.get("confidence") or 0.0),
                "evidence": [str(item) for item in raw.get("evidence") or []],
                "risks": [str(item) for item in raw.get("risks") or []],
                "proposed_ops": proposed_ops,
                "status": "candidate_only",
            }
        )
    return SemanticCandidateGenerationResult(
        candidates=candidates,
        rejected_candidates=rejected,
        usage=usage,
    )


def _safe_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in raw.items()
        if key not in {"raw_sql", "sql"}
    }
```

- [ ] **Step 4: 导出模块**

Modify `src/semantic/__init__.py`:

```python
from src.semantic.llm_semantic_candidates import (
    DeepSeekSemanticCandidateGenerator,
    SemanticCandidateGenerationResult,
)
```

Add to `__all__`:

```python
    "DeepSeekSemanticCandidateGenerator",
    "SemanticCandidateGenerationResult",
```

- [ ] **Step 5: 运行测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_llm_semantic_candidates
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/semantic/llm_semantic_candidates.py src/semantic/__init__.py tests/test_llm_semantic_candidates.py
git commit -m "feat: propose llm semantic mapping candidates"
```

## Task 3: 证据需求分类器

**Files:**
- Create: `src/semantic/evidence_requirements.py`
- Modify: `src/semantic/__init__.py`
- Test: `tests/test_evidence_requirements.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_evidence_requirements.py`:

```python
from __future__ import annotations

import unittest
from dataclasses import dataclass

import pydantic

from src.semantic.evidence_requirements import (
    DeepSeekEvidenceRequirementClassifier,
    EvidenceRequirement,
    EvidenceRequirementResult,
)


@dataclass(frozen=True)
class _FakeResponse:
    payload: dict
    usage: dict | None = None


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def chat_json(self, system_prompt: str, user_prompt: str) -> _FakeResponse:
        return _FakeResponse(payload=self.payload, usage={"total_tokens": 9})


class EvidenceRequirementTest(unittest.TestCase):
    def test_model_rejects_raw_sql(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            EvidenceRequirement(
                source_text="想读计算机",
                requirement_type="table_field",
                candidate_semantic="major_name",
                rationale="x",
                raw_sql="SELECT 1",
            )

    def test_classifier_splits_table_kb_boundary_and_unsupported_needs(self) -> None:
        client = _FakeClient(
            {
                "requirements": [
                    {
                        "source_text": "人工智能，计算机",
                        "requirement_type": "table_field",
                        "candidate_semantic": "major_name",
                        "rationale": "需要专业字段。",
                    },
                    {
                        "source_text": "好就业",
                        "requirement_type": "knowledge_base_or_reviewed_field",
                        "candidate_semantic": "employment_outcome",
                        "rationale": "需要就业数据或审核知识库。",
                    },
                    {
                        "source_text": "学校好一点",
                        "requirement_type": "reviewed_ranking_policy",
                        "candidate_semantic": "school_quality",
                        "rationale": "需要审核排序策略。",
                    },
                ]
            }
        )

        result = DeepSeekEvidenceRequirementClassifier(client).classify(
            text="想读人工智能，计算机，学校好一点，好就业",
            schema_context=[{"field_id": "major_name", "source_column": "专业"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )

        self.assertEqual([item.requirement_type for item in result.requirements], [
            "table_field",
            "knowledge_base_or_reviewed_field",
            "reviewed_ranking_policy",
        ])
        self.assertEqual(result.usage["total_tokens"], 9)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_evidence_requirements
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: 实现模型和 classifier**

Create `src/semantic/evidence_requirements.py`:

```python
from __future__ import annotations

import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.query_ast import _reject_raw_sql_key


RequirementType = Literal[
    "table_field",
    "knowledge_base_or_reviewed_field",
    "reviewed_ranking_policy",
    "user_boundary",
    "unsupported",
]


class EvidenceRequirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_text: str
    requirement_type: RequirementType
    candidate_semantic: str | None = None
    rationale: str

    @field_validator("source_text", "rationale")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("文本不能为空。")
        return text

    @model_validator(mode="before")
    @classmethod
    def _reject_raw_sql(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "evidence requirement")


class EvidenceRequirementResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requirements: list[EvidenceRequirement] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class JSONChatClient(Protocol):
    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """返回带 payload 和 usage 的 JSON 响应。"""


class DeepSeekEvidenceRequirementClassifier:
    """DeepSeek 只判断用户偏好需要什么证据，不决定可执行性。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def classify(
        self,
        *,
        text: str,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementResult:
        response = self.client.chat_json(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(
                text=text,
                schema_context=schema_context,
                query_options=query_options,
            ),
        )
        payload = getattr(response, "payload", response)
        usage = dict(getattr(response, "usage", {}) or {})
        return EvidenceRequirementResult(
            requirements=[
                EvidenceRequirement.model_validate(item)
                for item in payload.get("requirements", [])
                if isinstance(item, dict)
            ],
            usage=usage,
        )
```

Append prompts:

```python
def _system_prompt() -> str:
    return (
        "你是 evidence requirement classifier。"
        "你只判断每个用户偏好需要 table field、reviewed KB、ranking policy、user boundary "
        "还是 unsupported；不能生成 SQL，不能声称可执行。只返回 JSON object。"
    )


def _user_prompt(
    *,
    text: str,
    schema_context: list[dict[str, Any]],
    query_options: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "user_text": text,
            "schema_context": schema_context,
            "query_options": query_options,
            "allowed_requirement_types": [
                "table_field",
                "knowledge_base_or_reviewed_field",
                "reviewed_ranking_policy",
                "user_boundary",
                "unsupported",
            ],
            "output_schema": {
                "requirements": [
                    {
                        "source_text": "用户原文片段",
                        "requirement_type": "table_field",
                        "candidate_semantic": "canonical field 或外部语义",
                        "rationale": "只说明需要什么证据，不说明已执行",
                    }
                ]
            },
        },
        ensure_ascii=False,
    )
```

- [ ] **Step 4: 导出模块**

Modify `src/semantic/__init__.py`:

```python
from src.semantic.evidence_requirements import (
    DeepSeekEvidenceRequirementClassifier,
    EvidenceRequirement,
    EvidenceRequirementResult,
)
```

Add to `__all__`:

```python
    "DeepSeekEvidenceRequirementClassifier",
    "EvidenceRequirement",
    "EvidenceRequirementResult",
```

- [ ] **Step 5: 运行测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_evidence_requirements
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/semantic/evidence_requirements.py src/semantic/__init__.py tests/test_evidence_requirements.py
git commit -m "feat: classify evidence requirements"
```

## Task 4: RankingPlan 合同与 verifier

**Files:**
- Create: `src/semantic/ranking_plan.py`
- Create: `src/semantic/ranking_verifier.py`
- Modify: `src/semantic/__init__.py`
- Test: `tests/test_ranking_plan_verifier.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_ranking_plan_verifier.py`:

```python
from __future__ import annotations

import unittest

import pydantic

from src.semantic.ranking_plan import RankingCriterion, RankingPlan
from src.semantic.ranking_verifier import RankingVerifier
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry


def _registry() -> ReviewedMappingRegistry:
    return ReviewedMappingRegistry(
        active_fields={
            "major_name": ReviewedFieldMapping(
                field_id="major_name",
                source_column="专业",
                field_type="string",
                allowed_ops=("contains_any", "contains", "text_match"),
                required_for=("filter", "display"),
            ),
            "school_province": ReviewedFieldMapping(
                field_id="school_province",
                source_column="学校所在",
                field_type="enum_or_category",
                allowed_ops=("in", "eq", "equals_preferred_value"),
                required_for=("filter", "display"),
            ),
            "major_min_rank": ReviewedFieldMapping(
                field_id="major_min_rank",
                source_column="最低位次",
                field_type="number",
                allowed_ops=("between", "sort", "numeric_distance_to_user_value"),
                required_for=("rank_analysis", "display"),
            ),
        },
        unsupported_fields={
            "school_country_or_region": "当前数据缺少办学国家或地区字段。"
        },
    )


class RankingPlanVerifierTest(unittest.TestCase):
    def test_ranking_plan_rejects_raw_sql(self) -> None:
        with self.assertRaises(pydantic.ValidationError):
            RankingPlan.model_validate(
                {
                    "criteria": [
                        {
                            "criterion_id": "bad",
                            "source_text": "x",
                            "required_field": "major_name",
                            "operation": "text_match",
                            "priority": 1,
                            "rationale": "x",
                            "raw_sql": "SELECT 1",
                        }
                    ]
                }
            )

    def test_verifier_accepts_reviewed_generic_criteria_and_excludes_missing(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    {
                        "criterion_id": "major_text_match",
                        "source_text": "想读人工智能，计算机",
                        "required_field": "major_name",
                        "operation": "text_match",
                        "value": ["人工智能", "计算机"],
                        "priority": 1,
                        "rationale": "专业字段可验证。",
                    },
                    {
                        "criterion_id": "province_match",
                        "source_text": "想留在广东省",
                        "required_field": "school_province",
                        "operation": "equals_preferred_value",
                        "value": "广东",
                        "priority": 2,
                        "rationale": "学校所在字段可验证。",
                    },
                    {
                        "criterion_id": "overseas",
                        "source_text": "不想去国外",
                        "required_field": "school_country_or_region",
                        "operation": "equals_preferred_value",
                        "value": "中国",
                        "priority": 3,
                        "rationale": "需要国家地区字段。",
                    },
                ]
            }
        )

        result = RankingVerifier(_registry()).verify(plan)

        self.assertTrue(result.ok)
        self.assertEqual(
            [criterion.criterion_id for criterion in result.verified_plan.criteria],
            ["major_text_match", "province_match"],
        )
        self.assertEqual(result.excluded_criteria[0]["criterion_id"], "overseas")
        self.assertEqual(result.excluded_criteria[0]["reason"], "missing_field")

    def test_verifier_rejects_unsupported_operation(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    {
                        "criterion_id": "employment",
                        "source_text": "好就业",
                        "required_field": "major_name",
                        "operation": "external_prestige_score",
                        "priority": 1,
                        "rationale": "非法 operation。",
                    }
                ]
            }
        )

        result = RankingVerifier(_registry()).verify(plan)

        self.assertFalse(result.ok)
        self.assertEqual(result.excluded_criteria[0]["reason"], "unsupported_operation")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_ranking_plan_verifier
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: 实现 RankingPlan 模型**

Create `src/semantic/ranking_plan.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.semantic.query_ast import _reject_raw_sql_key


RankingOperation = Literal[
    "text_match",
    "equals_preferred_value",
    "in_preferred_set",
    "numeric_distance_to_user_value",
    "numeric_higher_is_better",
    "numeric_lower_is_better",
    "boolean_preferred_value",
    "missing_value_penalty",
]


class RankingCriterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str
    source_text: str
    required_field: str
    operation: RankingOperation
    value: Any = None
    priority: int
    direction: str = "desc"
    rationale: str

    @model_validator(mode="before")
    @classmethod
    def _reject_raw_sql(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "ranking criterion")

    @field_validator("criterion_id", "source_text", "required_field", "rationale")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("文本不能为空。")
        return text

    @field_validator("priority")
    @classmethod
    def _positive_priority(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("priority 必须为正整数。")
        return value


class RankingPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    criteria: list[RankingCriterion] = Field(default_factory=list)
    rationale_summary: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_raw_sql(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "ranking plan")
```

- [ ] **Step 4: 实现 RankingVerifier**

Create `src/semantic/ranking_verifier.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.semantic.ranking_plan import RankingCriterion, RankingPlan
from src.semantic.reviewed_mapping import ReviewedMappingRegistry


OP_TO_REVIEWED_OP = {
    "text_match": "contains_any",
    "equals_preferred_value": "eq",
    "in_preferred_set": "in",
    "numeric_distance_to_user_value": "sort",
    "numeric_higher_is_better": "sort",
    "numeric_lower_is_better": "sort",
    "boolean_preferred_value": "eq",
    "missing_value_penalty": "sort",
}


@dataclass(frozen=True)
class RankingVerificationResult:
    ok: bool
    verified_plan: RankingPlan
    excluded_criteria: list[dict[str, Any]] = field(default_factory=list)


class RankingVerifier:
    """只允许 reviewed fields 和通用 operation 进入排序引擎。"""

    def __init__(self, registry: ReviewedMappingRegistry) -> None:
        self.registry = registry

    def verify(self, plan: RankingPlan) -> RankingVerificationResult:
        verified: list[RankingCriterion] = []
        excluded: list[dict[str, Any]] = []
        for criterion in sorted(plan.criteria, key=lambda item: item.priority):
            if not self.registry.has_field(criterion.required_field):
                excluded.append(_excluded(criterion, "missing_field", self.registry.unsupported_reason(criterion.required_field)))
                continue
            reviewed_op = OP_TO_REVIEWED_OP.get(criterion.operation)
            if reviewed_op is None:
                excluded.append(_excluded(criterion, "unsupported_operation", "排序 operation 不在通用白名单中。"))
                continue
            if not self.registry.has_op(criterion.required_field, reviewed_op):
                excluded.append(_excluded(criterion, "unsupported_operation", f"字段不支持排序 operation {criterion.operation}。"))
                continue
            verified.append(criterion)
        return RankingVerificationResult(
            ok=bool(verified) and not any(item["reason"] == "unsupported_operation" for item in excluded),
            verified_plan=RankingPlan(criteria=verified, rationale_summary=plan.rationale_summary),
            excluded_criteria=excluded,
        )


def _excluded(
    criterion: RankingCriterion,
    reason: str,
    message: str | None,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion.criterion_id,
        "source_text": criterion.source_text,
        "required_field": criterion.required_field,
        "operation": criterion.operation,
        "reason": reason,
        "message": message or reason,
    }
```

- [ ] **Step 5: 导出模块**

Modify `src/semantic/__init__.py`:

```python
from src.semantic.ranking_plan import RankingCriterion, RankingPlan
from src.semantic.ranking_verifier import RankingVerifier, RankingVerificationResult
```

Add to `__all__`:

```python
    "RankingCriterion",
    "RankingPlan",
    "RankingVerifier",
    "RankingVerificationResult",
```

- [ ] **Step 6: 运行测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_ranking_plan_verifier
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/semantic/ranking_plan.py src/semantic/ranking_verifier.py src/semantic/__init__.py tests/test_ranking_plan_verifier.py
git commit -m "feat: verify generic ranking plans"
```

## Task 5: 通用排序引擎与结构化 criterion evidence

**Files:**
- Create: `src/semantic/generic_ranking.py`
- Test: `tests/test_generic_ranking.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_generic_ranking.py`:

```python
from __future__ import annotations

import unittest

from src.semantic.generic_ranking import GenericRankingEngine
from src.semantic.ranking_plan import RankingPlan


class GenericRankingEngineTest(unittest.TestCase):
    def test_sorts_by_verified_criteria_and_returns_evidence(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    {
                        "criterion_id": "major_text_match",
                        "source_text": "想读人工智能，计算机",
                        "required_field": "major_name",
                        "operation": "text_match",
                        "value": ["人工智能", "计算机"],
                        "priority": 1,
                        "rationale": "专业字段可验证。",
                    },
                    {
                        "criterion_id": "rank_distance",
                        "source_text": "我的排位是15000",
                        "required_field": "major_min_rank",
                        "operation": "numeric_distance_to_user_value",
                        "value": 15000,
                        "priority": 2,
                        "rationale": "最低位次字段可验证。",
                    },
                ]
            }
        )
        rows = [
            {"row_id": "r1", "major_name": "软件工程", "major_min_rank": 16000},
            {"row_id": "r2", "major_name": "计算机科学与技术", "major_min_rank": 18000},
            {"row_id": "r3", "major_name": "人工智能", "major_min_rank": 15100},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["r3", "r2", "r1"])
        evidence = {item["row_id"]: item for item in result.criterion_evidence}
        self.assertEqual(evidence["r3"]["criteria"][0]["matched_terms"], ["人工智能"])
        self.assertEqual(evidence["r3"]["criteria"][1]["derived"]["distance"], 100)
        self.assertEqual(evidence["r1"]["criteria"][0]["score"], 0)

    def test_generic_engine_works_for_non_admissions_rows(self) -> None:
        plan = RankingPlan.model_validate(
            {
                "criteria": [
                    {
                        "criterion_id": "city_match",
                        "source_text": "想住 Austin",
                        "required_field": "city",
                        "operation": "equals_preferred_value",
                        "value": "Austin",
                        "priority": 1,
                        "rationale": "城市字段可验证。",
                    },
                    {
                        "criterion_id": "rent_low",
                        "source_text": "租金低一点",
                        "required_field": "rent_usd",
                        "operation": "numeric_lower_is_better",
                        "priority": 2,
                        "rationale": "租金字段可验证。",
                    },
                ]
            }
        )
        rows = [
            {"row_id": "h1", "city": "Dallas", "rent_usd": 1200},
            {"row_id": "h2", "city": "Austin", "rent_usd": 1800},
            {"row_id": "h3", "city": "Austin", "rent_usd": 1500},
        ]

        result = GenericRankingEngine().rank(rows=rows, plan=plan)

        self.assertEqual([row["row_id"] for row in result.rows], ["h3", "h2", "h1"])
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_generic_ranking
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: 实现 GenericRankingEngine**

Create `src/semantic/generic_ranking.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from src.semantic.ranking_plan import RankingCriterion, RankingPlan


@dataclass(frozen=True)
class GenericRankingResult:
    rows: list[dict[str, Any]]
    criterion_evidence: list[dict[str, Any]] = field(default_factory=list)


class GenericRankingEngine:
    """执行 verified RankingPlan 的通用排序算子。"""

    def rank(
        self,
        *,
        rows: list[dict[str, Any]],
        plan: RankingPlan,
    ) -> GenericRankingResult:
        scored = []
        evidence_items = []
        for index, row in enumerate(rows):
            sort_key = []
            criteria_evidence = []
            for criterion in sorted(plan.criteria, key=lambda item: item.priority):
                score, evidence = _score_criterion(row, criterion)
                sort_key.append(-score)
                criteria_evidence.append(evidence)
            stable_key = (str(row.get("row_id") or index),)
            scored.append((tuple(sort_key), stable_key, dict(row)))
            evidence_items.append(
                {
                    "row_id": row.get("row_id") or f"row_{index}",
                    "criteria": criteria_evidence,
                }
            )
        scored.sort(key=lambda item: (item[0], item[1]))
        evidence_by_id = {
            item["row_id"]: item
            for item in evidence_items
        }
        ordered_rows = [row for _, _, row in scored]
        return GenericRankingResult(
            rows=ordered_rows,
            criterion_evidence=[
                evidence_by_id[row.get("row_id")]
                for row in ordered_rows
                if row.get("row_id") in evidence_by_id
            ],
        )
```

Append scoring helpers:

```python
def _score_criterion(
    row: dict[str, Any],
    criterion: RankingCriterion,
) -> tuple[float, dict[str, Any]]:
    value = row.get(criterion.required_field)
    if criterion.operation == "text_match":
        terms = [str(item) for item in criterion.value or [] if str(item)]
        text = "" if value is None else str(value)
        matched_terms = [term for term in terms if term in text]
        score = 1.0 if matched_terms else 0.0
        return score, _evidence(criterion, value, score, matched_terms=matched_terms)
    if criterion.operation == "equals_preferred_value":
        score = 1.0 if str(value) == str(criterion.value) else 0.0
        return score, _evidence(criterion, value, score)
    if criterion.operation == "in_preferred_set":
        preferred = {str(item) for item in criterion.value or []}
        score = 1.0 if str(value) in preferred else 0.0
        return score, _evidence(criterion, value, score)
    if criterion.operation == "numeric_distance_to_user_value":
        row_number = _number(value)
        target = _number(criterion.value)
        if row_number is None or target is None:
            return 0.0, _evidence(criterion, value, 0.0, derived={"distance": None})
        distance = abs(row_number - target)
        score = 1.0 / (1.0 + distance)
        return score, _evidence(criterion, value, score, derived={"distance": int(distance)})
    if criterion.operation == "numeric_higher_is_better":
        row_number = _number(value)
        score = row_number if row_number is not None else float("-inf")
        return score, _evidence(criterion, value, score)
    if criterion.operation == "numeric_lower_is_better":
        row_number = _number(value)
        score = -row_number if row_number is not None else float("-inf")
        return score, _evidence(criterion, value, score)
    if criterion.operation == "boolean_preferred_value":
        score = 1.0 if str(value) == str(criterion.value) else 0.0
        return score, _evidence(criterion, value, score)
    if criterion.operation == "missing_value_penalty":
        score = -1.0 if value in {None, ""} else 0.0
        return score, _evidence(criterion, value, score)
    return 0.0, _evidence(criterion, value, 0.0)


def _evidence(
    criterion: RankingCriterion,
    row_value: Any,
    score: float,
    *,
    matched_terms: list[str] | None = None,
    derived: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "criterion_id": criterion.criterion_id,
        "field_id": criterion.required_field,
        "operation": criterion.operation,
        "row_value": row_value,
        "score": score if math.isfinite(score) else None,
        "status": "pass" if score and score > 0 else "neutral_or_fail",
    }
    if matched_terms is not None:
        payload["matched_terms"] = matched_terms
    if derived is not None:
        payload["derived"] = derived
    return payload


def _number(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").replace("，", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
```

- [ ] **Step 4: 运行测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_generic_ranking
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/generic_ranking.py tests/test_generic_ranking.py
git commit -m "feat: add generic ranking engine"
```

## Task 6: Workbench semantic recommendation 接入 RankingPlan 和候选集优先

**Files:**
- Modify: `src/semantic/admissions_recommendation.py`
- Modify: `src/api/workbench.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 写失败测试**

Add to `UploadedSemanticAdmissionsFlowTest` in `tests/test_uploaded_dataset_flow.py`:

```python
    def test_semantic_recommendation_with_ranking_plan_records_criterion_evidence(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": {
                        "criteria": [
                            {
                                "criterion_id": "major_text_match",
                                "source_text": "想读人工智能，计算机",
                                "required_field": "major_name",
                                "operation": "text_match",
                                "value": ["人工智能", "计算机"],
                                "priority": 1,
                                "rationale": "专业字段可验证。",
                            },
                            {
                                "criterion_id": "province_match",
                                "source_text": "想留在广东省",
                                "required_field": "school_province",
                                "operation": "equals_preferred_value",
                                "value": "广东",
                                "priority": 2,
                                "rationale": "学校所在字段可验证。",
                            },
                        ]
                    },
                },
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "recommendation")
        ranking = response["evidence_pack"]["ranking"]
        self.assertEqual(ranking["status"], "ranked")
        self.assertEqual(
            ranking["verified_ranking_plan"]["criteria"][0]["criterion_id"],
            "major_text_match",
        )
        self.assertTrue(ranking["criterion_evidence"])
        self.assertIn("criterion_evidence", response["answer"])

    def test_semantic_recommendation_without_ranking_plan_is_candidate_list(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                },
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["evidence_pack"]["ranking"]["status"], "candidate_list_only")
        self.assertIn("候选列表", response["answer"])
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_semantic_recommendation_with_ranking_plan_records_criterion_evidence tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_semantic_recommendation_without_ranking_plan_is_candidate_list
```

Expected: FAIL because `evidence_pack["ranking"]` is missing.

- [ ] **Step 3: 让 planner 接收 verified ranking plan**

Modify `SemanticAdmissionsRecommendationPlanner.__init__` in `src/semantic/admissions_recommendation.py`:

```python
        ranking_plan: Any | None = None,
        ranking_verifier: Any | None = None,
        ranking_engine: Any | None = None,
```

Set instance fields:

```python
        self.ranking_plan = ranking_plan
        self.ranking_verifier = ranking_verifier
        self.ranking_engine = ranking_engine
```

Import:

```python
from src.semantic.generic_ranking import GenericRankingEngine
from src.semantic.ranking_verifier import RankingVerifier
```

- [ ] **Step 4: 在 planner 中执行通用排序**

After `rows = _ordered_rows(result_sections)` in `SemanticAdmissionsRecommendationPlanner.run`, insert:

```python
        ranking_summary = {
            "status": "candidate_list_only",
            "verified_ranking_plan": None,
            "excluded_criteria": [],
            "criterion_evidence": [],
        }
        if self.ranking_plan is not None:
            ranking_verifier = self.ranking_verifier or RankingVerifier(registry)
            ranking_result = ranking_verifier.verify(self.ranking_plan)
            ranking_summary["verified_ranking_plan"] = ranking_result.verified_plan.model_dump()
            ranking_summary["excluded_criteria"] = ranking_result.excluded_criteria
            if ranking_result.verified_plan.criteria:
                ranked = (self.ranking_engine or GenericRankingEngine()).rank(
                    rows=rows,
                    plan=ranking_result.verified_plan,
                )
                rows = ranked.rows
                ranking_summary["status"] = "ranked"
                ranking_summary["criterion_evidence"] = ranked.criterion_evidence
```

Add `ranking_summary` to `execution_summary`:

```python
                "ranking": ranking_summary,
```

- [ ] **Step 5: Workbench 解析 injected RankingPlan**

In `src/api/workbench.py`, import:

```python
from src.semantic.ranking_plan import RankingPlan
```

Add helper:

```python
def _semantic_ranking_plan(config: WorkbenchConfig) -> RankingPlan | None:
    payload = config.soft_preferences.get("semantic_ranking_plan")
    if not payload:
        return None
    return RankingPlan.model_validate(payload)
```

Pass it into `SemanticAdmissionsRecommendationPlanner`:

```python
        ranking_plan=_semantic_ranking_plan(config),
```

- [ ] **Step 6: EvidencePack 写入 ranking**

In `_semantic_evidence_pack`, add:

```python
        "ranking": (
            semantic_result.execution_summary.get("ranking")
            or {
                "status": "not_applicable",
                "verified_ranking_plan": None,
                "excluded_criteria": [],
                "criterion_evidence": [],
            }
        ),
```

- [ ] **Step 7: Answer 文案区分候选列表和排序推荐**

In `_semantic_recommendation_answer`, before building lines, add:

```python
    ranking = summary.get("ranking") or {}
```

Replace the rerank sentence branch with:

```python
    if ranking.get("status") == "ranked":
        ranking_sentence = "本次使用 verified RankingPlan 排序，criterion_evidence 已写入 EvidencePack。"
    else:
        ranking_sentence = "当前没有 verified RankingPlan；以下是满足确定性条件的候选列表，不声称为推荐排序。"
```

- [ ] **Step 8: 运行集成测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/semantic/admissions_recommendation.py src/api/workbench.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: rank semantic candidates with verified plans"
```

## Task 7: profile/review 输出语义候选和证据需求

**Files:**
- Modify: `src/api/dataset_service.py`
- Modify: `scripts/run_semantic_capability_probe.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 写失败测试**

Add to `UploadedSemanticAdmissionsFlowTest`:

```python
    def test_profile_exposes_candidate_only_semantic_mapping_records(self) -> None:
        with TemporaryDirectory() as directory:
            source = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_candidate_profile",
            )
            service.generate_domain_pack(
                "ds_candidate_profile",
                domain_name="admissions",
                base_domain="admissions",
            )

            profile = service.profile("ds_candidate_profile")

        self.assertIn("semantic_mapping_candidates", profile)
        candidates = profile["semantic_mapping_candidates"]["rule_based"]
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["status"], "candidate_only")
```

- [ ] **Step 2: 运行失败测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_profile_exposes_candidate_only_semantic_mapping_records
```

Expected: FAIL because `semantic_mapping_candidates` is missing.

- [ ] **Step 3: DatasetService profile 增加 candidate-only 输出**

In `src/api/dataset_service.py`, import:

```python
from src.semantic.semantic_candidates import RuleBasedSemanticCandidateGenerator
```

In `profile()`, after `semantic_query_options`, add:

```python
            semantic_mapping_candidates = {
                "rule_based": [
                    {**candidate, "status": "candidate_only"}
                    for candidate in RuleBasedSemanticCandidateGenerator.from_domain(
                        domain_config
                    ).generate(capability_graph_object)
                ],
                "llm": {
                    "status": "not_run",
                    "reason": "LLM semantic mapping candidates require explicit probe or admin action.",
                    "candidates": [],
                    "rejected_candidates": [],
                },
            }
```

Initialize before the domain block:

```python
        semantic_mapping_candidates: dict[str, Any] = {
            "rule_based": [],
            "llm": {
                "status": "not_available",
                "reason": "domain pack not generated",
                "candidates": [],
                "rejected_candidates": [],
            },
        }
```

Add to returned dict:

```python
            "semantic_mapping_candidates": semantic_mapping_candidates,
```

- [ ] **Step 4: Probe 增加 live semantic candidates 输出**

In `scripts/run_semantic_capability_probe.py`, add parser flag:

```python
    parser.add_argument(
        "--live-semantic-candidates",
        action="store_true",
        help="显式调用 DeepSeek 生成 candidate-only 字段语义候选。",
    )
```

Thread the flag into `run_probe(...)`, and after `build = service.build_warehouse(dataset_id)` add:

```python
    profile = service.profile(dataset_id)
```

If `live_semantic_candidates` is true, call:

```python
    from scripts.generate_domain_pack import load_source_dataset
    from src.domains import DomainConfig
    from src.semantic.capability_graph import DatasetCapabilityGraph
    from src.semantic.llm_semantic_candidates import DeepSeekSemanticCandidateGenerator

    domain = DomainConfig.from_path(Path(service._load_metadata(dataset_id)["domain_dir"]), "admissions")
    dataset = load_source_dataset(workbook_path)
    graph = DatasetCapabilityGraph.from_dataset(dataset)
    llm_candidates = DeepSeekSemanticCandidateGenerator().generate(
        graph=graph,
        domain_config=domain,
    )
```

Add to output:

```python
        "semantic_mapping_candidates": (
            llm_candidates.__dict__
            if live_semantic_candidates
            else profile.get("semantic_mapping_candidates")
        ),
```

- [ ] **Step 5: 运行测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_profile_exposes_candidate_only_semantic_mapping_records
.venv/bin/python scripts/run_semantic_capability_probe.py --help
```

Expected: test PASS; help includes `--live-semantic-candidates`.

- [ ] **Step 6: Commit**

```bash
git add src/api/dataset_service.py scripts/run_semantic_capability_probe.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: expose semantic mapping candidates"
```

## Task 8: 文档、验收和防幻觉回归

**Files:**
- Modify: `README.md`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 增加 unsupported preference 回归测试**

Add to `UploadedSemanticAdmissionsFlowTest`:

```python
    def test_external_knowledge_preference_is_not_ranked_without_reviewed_evidence(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，好就业，城市发展好，想留在广东省"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.query(
                dataset_id,
                user_input=query,
                soft_preferences={
                    "prompt": query,
                    "semantic_intent": _semantic_recommendation_intent(),
                    "semantic_ranking_plan": {
                        "criteria": [
                            {
                                "criterion_id": "major_text_match",
                                "source_text": "想读人工智能，计算机",
                                "required_field": "major_name",
                                "operation": "text_match",
                                "value": ["人工智能", "计算机"],
                                "priority": 1,
                                "rationale": "专业字段可验证。",
                            },
                            {
                                "criterion_id": "employment",
                                "source_text": "好就业",
                                "required_field": "employment_outcome",
                                "operation": "numeric_higher_is_better",
                                "priority": 2,
                                "rationale": "需要就业字段。",
                            },
                        ]
                    },
                },
            )

        excluded = response["evidence_pack"]["ranking"]["excluded_criteria"]
        self.assertIn("employment", [item["criterion_id"] for item in excluded])
        self.assertNotIn("就业前景好", response["answer"])
```

- [ ] **Step 2: 运行失败或通过测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_external_knowledge_preference_is_not_ranked_without_reviewed_evidence
```

Expected after Task 6: PASS. If it fails because answer mentions unsupported claim, update `_semantic_recommendation_answer` to list excluded criteria as not executed rather than positive claims.

- [ ] **Step 3: 更新 README**

In `README.md`, update the semantic capability section to state:

```markdown
推荐请求先返回 verified SQL 候选集。只有存在 verified RankingPlan 时，系统才把候选集排序为推荐；否则回答会明确称为“候选列表”。LLM 可以提出 RankingPlan 和 rationale，但不能直接排序、不能新增候选 item，也不能引用 EvidencePack 之外的就业、城市发展、学校氛围等结论。
```

- [ ] **Step 4: 更新 API contract**

In `docs/api_contract.md`, add to EvidencePack section:

```markdown
`evidence_pack.ranking` 固定包含 `status`、`verified_ranking_plan`、`excluded_criteria` 和 `criterion_evidence`。`status=candidate_list_only` 表示没有 verified RankingPlan，前端不得把结果标题写成推荐排序。`excluded_criteria` 必须展示给用户，尤其是需要外部知识库、缺字段或 unsupported operation 的偏好。
```

- [ ] **Step 5: 更新 methodology report**

In `docs/methodology_report.md`, add:

```markdown
RankingPlan 是 LLM 生成的可验证计划，不是 recommendation function。系统只执行通用 operation：`text_match`、`equals_preferred_value`、`in_preferred_set`、`numeric_distance_to_user_value`、`numeric_higher_is_better`、`numeric_lower_is_better`、`boolean_preferred_value`、`missing_value_penalty`。所有自然语言说服力来自系统生成的 `criterion_evidence`，不是自由 CoT。
```

- [ ] **Step 6: 运行文档和回归测试**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow tests.test_generic_ranking tests.test_ranking_plan_verifier tests.test_evidence_requirements tests.test_llm_semantic_candidates
git diff --check
```

Expected: PASS and no whitespace errors.

- [ ] **Step 7: Commit**

```bash
git add README.md docs/api_contract.md docs/methodology_report.md tests/test_uploaded_dataset_flow.py
git commit -m "docs: define evidence based ranking semantics"
```

## Task 9: 最终验证

**Files:**
- No new files.

- [ ] **Step 1: 运行完整单元测试**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected:

```text
OK (expected failures=1)
```

- [ ] **Step 2: 运行 whitespace 检查**

Run:

```bash
git diff --check
```

Expected: exit code 0.

- [ ] **Step 3: 检查工作区**

Run:

```bash
git status --short --branch
```

Expected: clean working tree on the feature branch after all commits.

- [ ] **Step 4: 手工 smoke：candidate list vs ranked**

Run the uploaded admissions probe without ranking plan:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx --query "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
```

Expected:

```text
status ok
query_type recommendation
evidence_pack.ranking.status candidate_list_only
```

Run a focused unit-level smoke with injected ranking plan:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_semantic_recommendation_with_ranking_plan_records_criterion_evidence
```

Expected: PASS.

- [ ] **Step 5: 最终提交检查**

Run:

```bash
git log --oneline -8
```

Expected: recent commits include:

```text
feat: enrich semantic field profiles
feat: propose llm semantic mapping candidates
feat: classify evidence requirements
feat: verify generic ranking plans
feat: add generic ranking engine
feat: rank semantic candidates with verified plans
feat: expose semantic mapping candidates
docs: define evidence based ranking semantics
```
