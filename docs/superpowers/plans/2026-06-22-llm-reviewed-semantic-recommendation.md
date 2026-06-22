# LLM Reviewed Semantic Recommendation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 uploaded data 的查询/推荐链路升级为 schema-aware LLM planning + verified query execution + evidence-bounded LLM reranking/answering，并先在 uploaded admissions recommendation 上落地。

**Architecture:** 上传数据先生成 `DatasetCapabilityGraph`、reviewed semantic mapping 和可选查询选项；DeepSeek 只读取 schema/capability 摘要和用户句子，输出候选 `SemanticIntent` / `QueryAST`，不输出 SQL。系统把候选意图拆成可执行 deterministic filters 与不可执行偏好，验证后用 DuckDB 召回 bounded candidate rows；如果请求需要推荐，DeepSeek 只能在候选 `row_id` 内 rerank，`RerankValidator` 校验后生成 EvidencePack，最终 AnswerGenerator 只能基于 EvidencePack 回答。

**Tech Stack:** Python `unittest`、DuckDB、Pandas/OpenPyXL、Pydantic v2、现有 `DeepSeekClient`、`DatasetService`、`DomainConfig`、`ReviewedMappingRegistry`、`QueryAST`、`SemanticQueryVerifier`、`SemanticSQLBuilder`、`EvidencePack`、Workbench contract。

---

## 范围检查

本计划实现通用 workflow 的 admissions 垂直切片：任意上传表先生成 schema/capability，uploaded admissions 的自然语言推荐走 LLM candidate intent、verified SQL、bounded rerank 和 evidence-only answer。其他领域复用同一接口，但不在本计划内完成领域 recipe。

必须完成：

- 上传后的 profile/capability 输出能说明当前表有哪些 deterministic fields、allowed ops、query options 和 unsupported fields，供 UI 生成用户可选项，也供 LLM prompt 使用。
- 原句 `我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐` 能被 DeepSeek-backed intent extractor 解析出 `user_rank=15000`、专业偏好、广东省内偏好和境外不可执行偏好。
- uploaded admissions 数据集使用 reviewed semantic mapping 生成 verified `QueryAST` 并执行 SQL 召回候选，不再因为旧 planner 的 `group_score/group_rank` 字段歧义阻塞。
- `不想去国外` 在没有 reviewed `school_country_or_region` 字段时进入 `not_executed_preferences`，不阻塞可执行的专业和省份筛选。
- `假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐` 继续返回 `needs_confirmation`，不执行 SQL。
- 推荐排序不靠 hardcoded school list 或 LLM 编答案；SQL 先召回 bounded candidates，LLM reranker 只能返回候选集内的 `row_id` 排序和 evidence-compatible reason codes。
- `RerankValidator` 必须拒绝候选集外 row、错误 bucket、超出每档数量、引用缺失字段的理由；失败时 fallback 到 deterministic rank-distance order。
- `列出冲稳保的次序，以及每个专业的最低录取排名` 从每档只取一条升级为可返回多条，并修复全局 `LIMIT 100` 截断保档的问题。
- 所有回答只引用 `EvidencePack` / bounded candidate rows / validated rerank，不读取 raw Excel 编答案。

不完成：

- 不引入向量知识库。
- 不允许 raw SQL、LLM SQL 或 LLM 直接答案进入执行路径。
- 不用单元测试调用真实 DeepSeek API。
- 不提交 `.env`、上传 Excel、DuckDB、`/tmp` probe 产物。

## 文件结构

- Create: `src/semantic/intent_models.py`
  - 定义 LLM 候选意图的数据合同：`SemanticIntent`、`SemanticPreference`、`SemanticUserContext`、`IntentExtractionResult`。
- Create: `src/semantic/query_options.py`
  - 从 `ReviewedMappingRegistry` 和 capability graph 生成 UI/LLM 可见的 deterministic query options、required context 和 unsupported fields。
- Create: `src/semantic/llm_intent_extractor.py`
  - 包装现有 `DeepSeekClient`，生成 schema-aware prompt，返回 normalized `SemanticIntent`；测试使用 fake client。
- Create: `src/semantic/preference_grounder.py`
  - 把 `SemanticPreference` 转成可执行 filter candidates、not-executed preferences 和 confirmation issues；缺字段偏好不进入 executable `QueryAST`。
- Create: `src/semantic/evidence_bounded_reranker.py`
  - DeepSeek 只接收 bounded candidates 和 allowed reason codes，只能返回候选 `row_id` 顺序。
- Create: `src/semantic/rerank_validator.py`
  - 校验 LLM rerank 输出是否只引用候选集、bucket 正确、数量合法、reason codes 不越界；失败返回 deterministic fallback。
- Create: `src/semantic/admissions_recommendation.py`
  - 新 semantic recommendation orchestrator：rank 必需；先执行 verified SQL 召回候选 rows，再调用可选 reranker、validator，输出冲稳保 sections、selection evidence、EvidencePack 字段和 Workbench rows。
- Modify: `src/semantic/sql_builder.py`
  - 支持 verified `contains_any`，用参数化 `STRPOS(..., ?) > 0` OR 表达式。
- Modify: `src/semantic/query_verifier.py`
  - 保持 missing field 为 error；由 `PreferenceGrounder` 负责不把不可执行偏好放进 QueryAST。
- Modify: `src/semantic/admissions_major_rank.py`
  - 去掉全局 `LIMIT 100` 截断；每档可返回多条；execution summary 记录 bucket candidate counts 和 selected counts。
- Modify: `src/api/workbench.py`
  - uploaded admissions recommendation 优先走 semantic planner；legacy planner 仍用于内置旧 schema 和非 semantic 数据。
- Modify: `domains/admissions/semantic_capabilities.json`
  - 增加 `semantic_recommendation` recipe；登记 `school_country_or_region`、`cooperation_type` 等缺字段语义的 unsupported reason。
- Modify: `tests/test_uploaded_dataset_flow.py`
  - 把 uploaded admissions recommendation 验收切到 semantic path。
- Create: `tests/test_semantic_llm_intent_extractor.py`
  - 用 fake DeepSeek client 验证 `排位是15000`、分数无位次、广东省内、境外偏好抽取。
- Create: `tests/test_semantic_preference_grounder.py`
  - 验证 reviewed 字段进入 executable filters；缺字段进入 not-executed。
- Create: `tests/test_semantic_admissions_recommendation.py`
  - 直接用 `SemanticIntent` 验证 planner 行为，不依赖 live LLM。
- Modify: `tests/test_semantic_sql_builder.py`
  - 增加 `contains_any` 参数化 SQL 测试。
- Modify: `tests/test_semantic_admissions_major_rank.py`
  - 增加每档多条和保档不被截断测试。
- Modify: `scripts/run_semantic_capability_probe.py`
  - 增加 `--live-llm` 和 `--query` 支持 recommendation smoke；默认仍不强制 live LLM。
- Modify: `README.md`、`docs/api_contract.md`、`docs/methodology_report.md`
  - 说明 uploaded admissions recommendation 已使用 LLM candidate intent + reviewed semantic execution；说明 score-only 拒答和 no-schema preference 行为。

## Task 0: Capability-Derived Query Options

**Files:**
- Create: `src/semantic/query_options.py`
- Modify: `src/api/dataset_service.py`
- Test: `tests/test_semantic_query_options.py`

- [ ] **Step 1: Write the failing query-options test**

Create `tests/test_semantic_query_options.py`:

```python
from __future__ import annotations

import unittest

from src.semantic.query_options import SemanticQueryOptionsBuilder
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry


class SemanticQueryOptionsBuilderTest(unittest.TestCase):
    def test_builds_options_from_reviewed_mapping(self) -> None:
        registry = ReviewedMappingRegistry(
            active_fields={
                "major_name": ReviewedFieldMapping(
                    field_id="major_name",
                    source_column="专业",
                    field_type="string",
                    allowed_ops=("contains_any", "contains"),
                    required_for=("filter", "display"),
                ),
                "school_province": ReviewedFieldMapping(
                    field_id="school_province",
                    source_column="学校所在",
                    field_type="enum_or_category",
                    allowed_ops=("in", "eq"),
                    required_for=("filter", "display"),
                ),
                "major_min_rank": ReviewedFieldMapping(
                    field_id="major_min_rank",
                    source_column="最低位次",
                    field_type="number",
                    allowed_ops=("between", "sort"),
                    required_for=("rank_analysis", "display"),
                ),
            },
            unsupported_fields={
                "school_country_or_region": "当前数据缺少境外办学字段，不能执行该排除条件。"
            },
        )

        options = SemanticQueryOptionsBuilder(registry).build()

        self.assertEqual(options["required_user_context"], ["user_rank"])
        self.assertIn("semantic_recommendation", options["query_types"])
        self.assertEqual(
            options["filters"]["major_name"]["source_column"],
            "专业",
        )
        self.assertEqual(
            options["unsupported_fields"]["school_country_or_region"],
            "当前数据缺少境外办学字段，不能执行该排除条件。",
        )
```

- [ ] **Step 2: Run the failing query-options test**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_query_options
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.semantic.query_options'`.

- [ ] **Step 3: Implement query options builder**

Create `src/semantic/query_options.py`:

```python
from __future__ import annotations

from typing import Any

from src.semantic.reviewed_mapping import ReviewedMappingRegistry


class SemanticQueryOptionsBuilder:
    """从 reviewed mapping 生成 UI 和 LLM 可见的查询能力摘要。"""

    def __init__(self, registry: ReviewedMappingRegistry) -> None:
        self.registry = registry

    def build(self) -> dict[str, Any]:
        fields = {item["field_id"]: item for item in self.registry.active_field_dicts()}
        filters = {
            field_id: {
                "source_column": item["source_column"],
                "allowed_ops": item["allowed_ops"],
                "field_type": item["field_type"],
            }
            for field_id, item in fields.items()
            if any(op in item["allowed_ops"] for op in ["eq", "in", "contains", "contains_any", "between"])
        }
        query_types: list[str] = []
        if "major_name" in fields and (
            "major_min_rank" in fields or "group_min_rank" in fields
        ):
            query_types.append("semantic_recommendation")
        if "major_min_rank" in fields:
            query_types.append("admissions_major_rank")
        return {
            "query_types": query_types,
            "required_user_context": ["user_rank"] if query_types else [],
            "filters": filters,
            "sort_fields": {
                field_id: item
                for field_id, item in fields.items()
                if "sort" in item["allowed_ops"]
            },
            "unsupported_fields": {
                field_id: self.registry.unsupported_reason(field_id)
                for field_id in self.registry.unsupported_field_ids()
            },
        }
```

- [ ] **Step 4: Expose options in dataset profile**

In `src/api/dataset_service.py`, import `SemanticQueryOptionsBuilder` and add the options where profile currently includes `capability_graph`. Use this code shape after `registry = ReviewedMappingRegistry.from_domain(...)` is available or after building the registry in the same block:

```python
profile["semantic_query_options"] = SemanticQueryOptionsBuilder(registry).build()
```

If `profile()` does not currently create a registry, create one from the generated domain config and capability graph:

```python
graph = DatasetCapabilityGraph.from_dataset(dataset)
registry = ReviewedMappingRegistry.from_domain(domain_config, graph)
profile["semantic_query_options"] = SemanticQueryOptionsBuilder(registry).build()
```

- [ ] **Step 5: Run query-options tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_query_options tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/semantic/query_options.py src/api/dataset_service.py tests/test_semantic_query_options.py
git commit -m "feat: expose semantic query options"
```

## Task 1: Semantic Intent Contract

**Files:**
- Create: `src/semantic/intent_models.py`
- Modify: `src/semantic/__init__.py`
- Test: `tests/test_semantic_llm_intent_extractor.py`

- [ ] **Step 1: Write the failing model test**

Add this file:

```python
from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.semantic.intent_models import (
    IntentExtractionResult,
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)


class SemanticIntentModelTest(unittest.TestCase):
    def test_intent_model_accepts_recommendation_rank_and_preferences(self) -> None:
        intent = SemanticIntent(
            query_type="semantic_recommendation",
            user_context=SemanticUserContext(user_rank=15000, subject_type=None),
            preferences=[
                SemanticPreference(
                    source_text="人工智能，计算机",
                    semantic="major_name",
                    op="contains_any",
                    value=["人工智能", "计算机"],
                ),
                SemanticPreference(
                    source_text="想留在广东省",
                    semantic="school_province",
                    op="in",
                    value=["广东"],
                ),
                SemanticPreference(
                    source_text="不想去国外",
                    semantic="school_country_or_region",
                    op="not_in",
                    value=["国外", "境外", "海外"],
                ),
            ],
        )

        self.assertEqual(intent.user_context.user_rank, 15000)
        self.assertEqual(intent.preferences[0].semantic, "major_name")
        self.assertEqual(intent.preferences[0].value, ["人工智能", "计算机"])

    def test_intent_model_rejects_raw_sql_anywhere(self) -> None:
        with self.assertRaises(ValidationError):
            SemanticPreference(
                source_text="坏输入",
                semantic="major_name",
                op="contains",
                value={"raw_sql": "DROP TABLE admissions"},
            )

    def test_extraction_result_records_llm_usage(self) -> None:
        result = IntentExtractionResult(
            intent=SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_rank=15000),
                preferences=[],
            ),
            provider="deepseek",
            raw_payload={"query_type": "semantic_recommendation"},
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.usage["total_tokens"], 15)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the failing model test**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_llm_intent_extractor.SemanticIntentModelTest
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.semantic.intent_models'`.

- [ ] **Step 3: Implement intent models**

Create `src/semantic/intent_models.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.semantic.query_ast import _reject_raw_sql_key


QueryType = Literal[
    "semantic_recommendation",
    "admissions_major_rank",
    "group_detail_report",
    "unknown",
]


class SemanticUserContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_rank: int | None = None
    user_score: int | None = None
    source_province: str | None = None
    subject_type: str | None = None
    reselected_subjects: list[str] = Field(default_factory=list)

    @field_validator("user_rank", "user_score")
    @classmethod
    def _positive_number(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("数值必须为正整数。")
        return value

    @field_validator("reselected_subjects")
    @classmethod
    def _clean_subjects(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in output:
                output.append(text)
        return output[:2]


class SemanticPreference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_text: str
    semantic: str
    op: str
    value: Any
    confidence: float = 1.0
    reason: str | None = None

    @field_validator("source_text", "semantic", "op")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("文本字段不能为空。")
        return text

    @field_validator("value")
    @classmethod
    def _reject_raw_sql(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "semantic preference value")


class SemanticIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_type: QueryType
    user_context: SemanticUserContext = Field(default_factory=SemanticUserContext)
    preferences: list[SemanticPreference] = Field(default_factory=list)
    requested_output: list[str] = Field(default_factory=list)
    source_language: str = "zh-CN"

    @field_validator("requested_output")
    @classmethod
    def _clean_requested_output(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in output:
                output.append(text)
        return output


class IntentExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: SemanticIntent
    provider: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("raw_payload", "warnings")
    @classmethod
    def _reject_raw_sql_records(cls, value: Any) -> Any:
        return _reject_raw_sql_key(value, "intent extraction record")
```

Update `src/semantic/__init__.py` exports:

```python
from src.semantic.intent_models import (
    IntentExtractionResult,
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)

__all__ = [
    "IntentExtractionResult",
    "SemanticIntent",
    "SemanticPreference",
    "SemanticUserContext",
]
```

If `src/semantic/__init__.py` already exports other names, append these imports and names without removing the existing exports.

- [ ] **Step 4: Run the model test**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_llm_intent_extractor.SemanticIntentModelTest
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/intent_models.py src/semantic/__init__.py tests/test_semantic_llm_intent_extractor.py
git commit -m "feat: add semantic intent contract"
```

## Task 2: DeepSeek Semantic Intent Extractor

**Files:**
- Create: `src/semantic/llm_intent_extractor.py`
- Modify: `src/semantic/__init__.py`
- Test: `tests/test_semantic_llm_intent_extractor.py`

- [ ] **Step 1: Add failing extractor tests**

Append these tests to `tests/test_semantic_llm_intent_extractor.py`:

```python
from src.semantic.llm_intent_extractor import DeepSeekSemanticIntentExtractor


class FakeDeepSeekClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, str]] = []

    def chat_json(self, system_prompt: str, user_prompt: str):
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt}
        )

        class Response:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload
                self.usage = {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                }

        return Response(self.payload)


class DeepSeekSemanticIntentExtractorTest(unittest.TestCase):
    def test_extracts_rank_with_copula_and_preferences(self) -> None:
        payload = {
            "query_type": "semantic_recommendation",
            "user_context": {
                "user_rank": 15000,
                "user_score": None,
                "source_province": "广东",
                "subject_type": None,
                "reselected_subjects": [],
            },
            "preferences": [
                {
                    "source_text": "人工智能，计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                    "reason": "用户明确专业方向。",
                },
                {
                    "source_text": "想留在广东省",
                    "semantic": "school_province",
                    "op": "in",
                    "value": ["广东"],
                    "reason": "用户明确院校所在地。",
                },
                {
                    "source_text": "不想去国外",
                    "semantic": "school_country_or_region",
                    "op": "not_in",
                    "value": ["国外", "境外", "海外"],
                    "reason": "需要专门字段才能执行。",
                },
            ],
            "requested_output": ["recommendations", "risk_buckets"],
        }
        extractor = DeepSeekSemanticIntentExtractor(
            client=FakeDeepSeekClient(payload)
        )

        result = extractor.extract(
            "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐",
            schema_context=[
                {
                    "field_id": "major_name",
                    "source_column": "专业",
                    "allowed_ops": ["contains_any"],
                }
            ],
        )

        self.assertEqual(result.intent.query_type, "semantic_recommendation")
        self.assertEqual(result.intent.user_context.user_rank, 15000)
        self.assertEqual(
            [item.semantic for item in result.intent.preferences],
            ["major_name", "school_province", "school_country_or_region"],
        )
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.usage["total_tokens"], 18)
        prompt = extractor.client.calls[0]["user_prompt"]
        self.assertIn("字段摘要", prompt)
        self.assertNotIn("SELECT *", prompt)

    def test_score_only_intent_preserves_missing_rank(self) -> None:
        payload = {
            "query_type": "semantic_recommendation",
            "user_context": {
                "user_rank": None,
                "user_score": 630,
                "source_province": "广东",
                "subject_type": None,
                "reselected_subjects": [],
            },
            "preferences": [
                {
                    "source_text": "人工智能，计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                }
            ],
            "requested_output": ["recommendations"],
        }
        extractor = DeepSeekSemanticIntentExtractor(
            client=FakeDeepSeekClient(payload)
        )

        result = extractor.extract(
            "假设我今年的高考分数是630分，想读人工智能，计算机，请给出推荐",
            schema_context=[],
        )

        self.assertIsNone(result.intent.user_context.user_rank)
        self.assertEqual(result.intent.user_context.user_score, 630)
```

- [ ] **Step 2: Run extractor tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_llm_intent_extractor
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.semantic.llm_intent_extractor'`.

- [ ] **Step 3: Implement DeepSeek semantic intent extractor**

Create `src/semantic/llm_intent_extractor.py`:

```python
from __future__ import annotations

import json
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient
from src.semantic.intent_models import (
    IntentExtractionResult,
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)


class JSONChatClient(Protocol):
    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """返回带 payload 和 usage 的 JSON 响应。"""


class DeepSeekSemanticIntentExtractor:
    """DeepSeek 只提出语义意图候选，不判断可执行性。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def extract(
        self,
        text: str,
        *,
        schema_context: list[dict[str, Any]],
        hard_context: dict[str, Any] | None = None,
    ) -> IntentExtractionResult:
        response = self.client.chat_json(
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(
                text=text,
                schema_context=schema_context,
                hard_context=hard_context or {},
            ),
        )
        payload = _normalize_payload(response.payload, original_text=text)
        return IntentExtractionResult(
            intent=SemanticIntent.model_validate(payload),
            provider="deepseek",
            raw_payload=payload,
            usage=dict(getattr(response, "usage", {}) or {}),
        )


def _system_prompt() -> str:
    return (
        "你是招生数据系统的语义意图抽取器。"
        "你只能提出候选 SemanticIntent，不能生成 SQL，不能声称已执行，"
        "不能根据常识补表格数据。只返回 JSON object。"
    )


def _user_prompt(
    *,
    text: str,
    schema_context: list[dict[str, Any]],
    hard_context: dict[str, Any],
) -> str:
    schema_json = json.dumps(schema_context, ensure_ascii=False)
    hard_json = json.dumps(hard_context, ensure_ascii=False)
    return (
        "请把用户输入转换为 SemanticIntent JSON。"
        "字段摘要只包含 reviewed semantic field、source_column、allowed_ops 和 unsupported_reason。"
        "如果用户说“排位是15000”“位次是15000”“省排15000”，user_context.user_rank=15000。"
        "如果用户只有分数没有位次，保留 user_score，user_rank=null。"
        "如果用户说想读人工智能、计算机，生成 semantic=major_name, op=contains_any。"
        "如果用户说留在广东省、省内、不出省，生成 semantic=school_province, op=in, value=[\"广东\"]。"
        "如果用户说不想去国外、不出国，生成 semantic=school_country_or_region, op=not_in。"
        "不要把 unsupported preference 改写成别的字段。"
        "JSON schema："
        "{"
        "\"query_type\":\"semantic_recommendation|admissions_major_rank|group_detail_report|unknown\","
        "\"user_context\":{\"user_rank\":number|null,\"user_score\":number|null,"
        "\"source_province\":string|null,\"subject_type\":string|null,"
        "\"reselected_subjects\":[string]},"
        "\"preferences\":[{\"source_text\":string,\"semantic\":string,"
        "\"op\":string,\"value\":any,\"reason\":string|null}],"
        "\"requested_output\":[string]"
        "}。"
        f"字段摘要：{schema_json}。"
        f"硬信息：{hard_json}。"
        f"用户输入：{text}"
    )


def _normalize_payload(payload: dict[str, Any], *, original_text: str) -> dict[str, Any]:
    user_context = dict(payload.get("user_context") or {})
    preferences = list(payload.get("preferences") or [])
    if _has_rank_text(original_text) and user_context.get("user_rank") is None:
        parsed = _parse_rank_text(original_text)
        if parsed is not None:
            user_context["user_rank"] = parsed
    if user_context.get("source_province") and "广东" in str(
        user_context["source_province"]
    ):
        user_context["source_province"] = "广东"
    if user_context.get("subject_type") and "物理" in str(
        user_context["subject_type"]
    ):
        user_context["subject_type"] = "物理"
    elif user_context.get("subject_type") and "历史" in str(
        user_context["subject_type"]
    ):
        user_context["subject_type"] = "历史"
    return {
        "query_type": payload.get("query_type") or "unknown",
        "user_context": user_context,
        "preferences": preferences,
        "requested_output": list(payload.get("requested_output") or []),
        "source_language": "zh-CN",
    }


def _has_rank_text(text: str) -> bool:
    return any(token in text for token in ["排位", "位次", "排名", "省排", "全省"])


def _parse_rank_text(text: str) -> int | None:
    import re

    match = re.search(
        r"(?:排位|位次|排名|省排|省排名|全省)\s*(?:是|为|约|大概|大约|差不多)?\s*"
        r"(\d{1,3}(?:[,，]\d{3})+|\d+(?:\.\d+)?)\s*(万|w|W|名|左右)?",
        text,
    )
    if not match:
        return None
    number = match.group(1).replace(",", "").replace("，", "")
    value = float(number)
    unit = match.group(2)
    if unit in {"万", "w", "W"}:
        value *= 10000
    return int(value)
```

Update `src/semantic/__init__.py`:

```python
from src.semantic.llm_intent_extractor import DeepSeekSemanticIntentExtractor

__all__.append("DeepSeekSemanticIntentExtractor")
```

- [ ] **Step 4: Run extractor tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_llm_intent_extractor
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/llm_intent_extractor.py src/semantic/__init__.py tests/test_semantic_llm_intent_extractor.py
git commit -m "feat: extract semantic intents with deepseek"
```

## Task 3: Preference Grounding And contains_any SQL

**Files:**
- Create: `src/semantic/preference_grounder.py`
- Modify: `src/semantic/sql_builder.py`
- Test: `tests/test_semantic_preference_grounder.py`
- Test: `tests/test_semantic_sql_builder.py`

- [ ] **Step 1: Write failing grounding tests**

Create `tests/test_semantic_preference_grounder.py`:

```python
from __future__ import annotations

import unittest

from src.semantic.intent_models import SemanticPreference
from src.semantic.preference_grounder import PreferenceGrounder
from src.semantic.reviewed_mapping import ReviewedFieldMapping, ReviewedMappingRegistry


def _registry() -> ReviewedMappingRegistry:
    return ReviewedMappingRegistry(
        active_fields={
            "major_name": ReviewedFieldMapping(
                field_id="major_name",
                source_column="专业",
                field_type="string",
                allowed_ops=("contains_any", "contains", "eq"),
                required_for=("filter", "display"),
            ),
            "school_province": ReviewedFieldMapping(
                field_id="school_province",
                source_column="学校所在",
                field_type="enum_or_category",
                allowed_ops=("in", "eq"),
                required_for=("filter", "display"),
            ),
        },
        unsupported_fields={
            "school_country_or_region": "当前数据缺少境外办学字段，不能执行该排除条件。"
        },
    )


class PreferenceGrounderTest(unittest.TestCase):
    def test_splits_executable_and_missing_schema_preferences(self) -> None:
        preferences = [
            SemanticPreference(
                source_text="人工智能，计算机",
                semantic="major_name",
                op="contains_any",
                value=["人工智能", "计算机"],
            ),
            SemanticPreference(
                source_text="想留在广东省",
                semantic="school_province",
                op="in",
                value=["广东"],
            ),
            SemanticPreference(
                source_text="不想去国外",
                semantic="school_country_or_region",
                op="not_in",
                value=["国外", "境外", "海外"],
            ),
        ]

        result = PreferenceGrounder(_registry()).ground(preferences)

        self.assertEqual(
            [item["field_id"] for item in result.filters],
            ["major_name", "school_province"],
        )
        self.assertEqual(result.filters[0]["op"], "contains_any")
        self.assertEqual(result.not_executed_preferences[0]["source_text"], "不想去国外")
        self.assertEqual(
            result.not_executed_preferences[0]["match_type"],
            "no_schema_field",
        )
        self.assertFalse(result.not_executed_preferences[0]["executable"])

    def test_unsupported_op_is_not_executed(self) -> None:
        result = PreferenceGrounder(_registry()).ground(
            [
                SemanticPreference(
                    source_text="专业排除计算机",
                    semantic="major_name",
                    op="not_in",
                    value=["计算机"],
                )
            ]
        )

        self.assertEqual(result.filters, [])
        self.assertEqual(
            result.not_executed_preferences[0]["match_type"],
            "unsupported_op",
        )


if __name__ == "__main__":
    unittest.main()
```

Append this test to `tests/test_semantic_sql_builder.py`:

```python
    def test_contains_any_builds_parameterized_or_expression(self) -> None:
        plan = VerifiedQueryPlan(
            intent="semantic_recommendation",
            table_name="admissions",
            select_columns=[{"field_id": "major_name", "source_column": "专业"}],
            filters=[
                {
                    "field_id": "major_name",
                    "source_column": "专业",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                }
            ],
            sort=[],
            limit=30,
            answerable_intents=[],
            unanswerable_intents=[],
        )

        built = SemanticSQLBuilder().build(plan)

        self.assertIn('STRPOS(CAST("专业" AS VARCHAR), ?) > 0', built.sql)
        self.assertIn(" OR ", built.sql)
        self.assertEqual(built.params, ["人工智能", "计算机", 30])
```

- [ ] **Step 2: Run failing grounding and SQL tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_preference_grounder tests.test_semantic_sql_builder
```

Expected: FAIL with missing `preference_grounder` and unsupported SQL op `contains_any`.

- [ ] **Step 3: Implement PreferenceGrounder and contains_any**

Create `src/semantic/preference_grounder.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.semantic.intent_models import SemanticPreference
from src.semantic.reviewed_mapping import ReviewedMappingRegistry


@dataclass(frozen=True)
class GroundedPreferences:
    filters: list[dict[str, Any]] = field(default_factory=list)
    not_executed_preferences: list[dict[str, Any]] = field(default_factory=list)
    answerable_intents: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)


class PreferenceGrounder:
    """把 LLM 候选偏好约束到 reviewed mapping。"""

    def __init__(self, registry: ReviewedMappingRegistry) -> None:
        self.registry = registry

    def ground(self, preferences: list[SemanticPreference]) -> GroundedPreferences:
        filters: list[dict[str, Any]] = []
        not_executed: list[dict[str, Any]] = []
        answerable: list[dict[str, Any]] = []
        unanswerable: list[dict[str, Any]] = []
        for preference in preferences:
            field_id = preference.semantic
            if not self.registry.has_field(field_id):
                reason = (
                    self.registry.unsupported_reason(field_id)
                    or f"字段 {field_id} 未通过 review，不能执行。"
                )
                record = _not_executed(preference, "no_schema_field", reason)
                not_executed.append(record)
                unanswerable.append(
                    {
                        "field_id": field_id,
                        "source_text": preference.source_text,
                        "reason": "missing_field",
                        "message": reason,
                    }
                )
                continue
            if not self.registry.has_op(field_id, preference.op):
                reason = f"字段 {field_id} 不支持操作 {preference.op}。"
                record = _not_executed(preference, "unsupported_op", reason)
                not_executed.append(record)
                unanswerable.append(
                    {
                        "field_id": field_id,
                        "op": preference.op,
                        "source_text": preference.source_text,
                        "reason": "unsupported_op",
                        "message": reason,
                    }
                )
                continue
            filters.append(
                {
                    "field_id": field_id,
                    "op": preference.op,
                    "value": preference.value,
                    "source_text": preference.source_text,
                }
            )
            answerable.append(
                {
                    "field_id": field_id,
                    "op": preference.op,
                    "source_text": preference.source_text,
                    "reason": "grounded_preference",
                    "capability": "filter",
                }
            )
        return GroundedPreferences(
            filters=filters,
            not_executed_preferences=not_executed,
            answerable_intents=answerable,
            unanswerable_intents=unanswerable,
        )


def _not_executed(
    preference: SemanticPreference,
    match_type: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "source_text": preference.source_text,
        "field_id": preference.semantic,
        "field": "无可执行字段",
        "match_type": match_type,
        "operator": preference.op,
        "value": preference.value,
        "executable": False,
        "reason": reason,
    }
```

Modify `src/semantic/sql_builder.py` in `_build_filter_expression`:

```python
        if op == "contains_any":
            values = _require_non_empty_values(value, op)
            expressions = []
            for item in values:
                params.append(item)
                expressions.append(f"STRPOS(CAST({column} AS VARCHAR), ?) > 0")
            return "(" + " OR ".join(expressions) + ")"
```

Place this block after the existing `contains` block and before `between`.

- [ ] **Step 4: Run grounding and SQL tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_preference_grounder tests.test_semantic_sql_builder
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/preference_grounder.py src/semantic/sql_builder.py tests/test_semantic_preference_grounder.py tests/test_semantic_sql_builder.py
git commit -m "feat: ground semantic preferences"
```

## Task 4: Semantic Admissions Recommendation Planner

**Files:**
- Create: `src/semantic/admissions_recommendation.py`
- Modify: `domains/admissions/semantic_capabilities.json`
- Test: `tests/test_semantic_admissions_recommendation.py`

- [ ] **Step 1: Add failing planner tests**

Create `tests/test_semantic_admissions_recommendation.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.generate_domain_pack import load_source_dataset
from src.adapters.data_warehouse import build_structured_store_from_dataset
from src.domains import DomainConfig
from src.semantic.admissions_recommendation import SemanticAdmissionsRecommendationPlanner
from src.semantic.intent_models import (
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)
from tests.semantic_test_utils import write_new_admissions_excel


class SemanticAdmissionsRecommendationPlannerTest(unittest.TestCase):
    def test_rank_major_and_school_province_query_executes(self) -> None:
        with TemporaryDirectory() as directory:
            planner = _planner(Path(directory))
            intent = SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_rank=15000),
                preferences=[
                    SemanticPreference(
                        source_text="人工智能，计算机",
                        semantic="major_name",
                        op="contains_any",
                        value=["人工智能", "计算机"],
                    ),
                    SemanticPreference(
                        source_text="想留在广东省",
                        semantic="school_province",
                        op="in",
                        value=["广东"],
                    ),
                    SemanticPreference(
                        source_text="不想去国外",
                        semantic="school_country_or_region",
                        op="not_in",
                        value=["国外", "境外", "海外"],
                    ),
                ],
            )

            result = planner.run(intent)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.query_type, "semantic_recommendation")
        self.assertTrue(result.rows)
        self.assertEqual(result.execution_summary["basis"], "major_min_rank")
        self.assertIn("STRPOS", result.execution_summary["sql"])
        self.assertEqual(
            result.not_executed_preferences[0]["field_id"],
            "school_country_or_region",
        )
        self.assertEqual(
            result.execution_summary["verified_query_plan"]["intent"],
            "semantic_recommendation",
        )

    def test_score_without_rank_does_not_execute_sql(self) -> None:
        with TemporaryDirectory() as directory:
            planner = _planner(Path(directory))
            intent = SemanticIntent(
                query_type="semantic_recommendation",
                user_context=SemanticUserContext(user_score=630),
                preferences=[
                    SemanticPreference(
                        source_text="人工智能，计算机",
                        semantic="major_name",
                        op="contains_any",
                        value=["人工智能", "计算机"],
                    )
                ],
            )

            result = planner.run(intent)

        self.assertEqual(result.status, "needs_confirmation")
        self.assertEqual(result.rows, [])
        self.assertEqual(result.execution_summary["sql"], "")
        self.assertEqual(result.warnings[0]["code"], "score_without_rank")


def _planner(root: Path) -> SemanticAdmissionsRecommendationPlanner:
    source = write_new_admissions_excel(root / "new_admissions.xlsx")
    dataset = load_source_dataset(source)
    database_path = root / "admissions.duckdb"
    domain_config = DomainConfig.load("admissions")
    build_structured_store_from_dataset(
        dataset=dataset,
        database_path=database_path,
        schema_path=domain_config.schema_path,
        domain_config=domain_config,
        source_path=dataset.workbook_path,
    )
    return SemanticAdmissionsRecommendationPlanner(
        domain_config=domain_config,
        database_path=database_path,
        table_name=domain_config.table_name,
    )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing planner tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_recommendation
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.semantic.admissions_recommendation'`.

- [ ] **Step 3: Add semantic recommendation recipe and unsupported mappings**

Modify `domains/admissions/semantic_capabilities.json`:

```json
    "school_country_or_region": {
      "source_columns": ["境外办学地区", "国家地区"],
      "field_type": "enum_or_category",
      "allowed_ops": ["not_in", "in", "eq"],
      "required_for": ["filter"],
      "confidence": 1.0,
      "unsupported_reason": "当前数据缺少境外办学字段，不能执行该排除条件。",
      "reason": "境外办学偏好需要专门字段，不能由院校名称或备注推断。"
    },
    "cooperation_type": {
      "source_columns": ["合作办学类型", "合作类型"],
      "field_type": "enum_or_category",
      "allowed_ops": ["not_in", "in", "eq"],
      "required_for": ["filter"],
      "confidence": 1.0,
      "unsupported_reason": "当前数据缺少合作办学类型字段，不能执行该排除条件。",
      "reason": "合作办学偏好需要专门字段，不能只靠自由文本推断。"
    }
```

Add this recipe under `query_recipes`:

```json
    "semantic_recommendation": {
      "description": "基于用户排位、专业关键词和 reviewed 字段生成招生推荐。",
      "required_fields": [
        "year",
        "university_name",
        "group_code",
        "major_name",
        "major_code",
        "school_province",
        "major_min_rank",
        "major_min_score"
      ],
      "optional_fields": [
        "subject_type",
        "subject_requirement",
        "major_notes",
        "school_ownership",
        "school_is_985",
        "school_is_211",
        "plan_count",
        "tuition_yuan_per_year",
        "city",
        "group_min_rank",
        "school_country_or_region",
        "cooperation_type"
      ],
      "rank_basis_preference": ["group_min_rank", "major_min_rank"],
      "rank_window": {"reach_max_abs": 8000, "safety_min": 30000},
      "default_limit": 50
    }
```

Keep valid JSON commas when inserting these blocks.

- [ ] **Step 4: Implement planner**

Create `src/semantic/admissions_recommendation.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from src.adapters.data_warehouse import load_structured_dataset
from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.intent_models import SemanticIntent
from src.semantic.preference_grounder import PreferenceGrounder
from src.semantic.query_ast import QueryAST
from src.semantic.query_verifier import SemanticQueryVerifier
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.sql_builder import SemanticSQLBuilder


QUERY_TYPE = "semantic_recommendation"
DISPLAY_FIELDS = [
    "year",
    "university_name",
    "group_code",
    "major_name",
    "major_code",
    "major_min_score",
    "major_min_rank",
    "school_province",
    "plan_count",
    "city",
    "tuition_yuan_per_year",
    "group_min_rank",
]


@dataclass(frozen=True)
class SemanticAdmissionsRecommendationResult:
    query_type: str
    status: str
    rows: list[dict[str, Any]]
    result_sections: dict[str, dict[str, Any]]
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]
    not_executed_preferences: list[dict[str, Any]]
    execution_summary: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)


class SemanticAdmissionsRecommendationPlanner:
    """执行 reviewed semantic admissions recommendation。"""

    def __init__(
        self,
        *,
        domain_config: DomainConfig,
        database_path: str | Path,
        table_name: str,
    ) -> None:
        self.domain_config = domain_config
        self.database_path = Path(database_path)
        self.table_name = table_name

    def run(self, intent: SemanticIntent) -> SemanticAdmissionsRecommendationResult:
        if intent.query_type != QUERY_TYPE:
            return _blocked("unsupported_intent", "当前 planner 只处理 semantic_recommendation。")
        rank = intent.user_context.user_rank
        if not rank:
            code = "score_without_rank" if intent.user_context.user_score else "missing_rank"
            message = (
                "只提供分数没有位次；请补充广东省排位，系统不会仅凭分数执行推荐。"
                if code == "score_without_rank"
                else "缺少广东省排位/位次；请补充位次后再执行推荐。"
            )
            return SemanticAdmissionsRecommendationResult(
                query_type=QUERY_TYPE,
                status="needs_confirmation",
                rows=[],
                result_sections=_empty_sections(),
                answerable_intents=[],
                unanswerable_intents=[
                    {"field_id": "user_rank", "reason": code, "message": message}
                ],
                not_executed_preferences=[],
                execution_summary=_empty_execution_summary(rank=None),
                warnings=[{"code": code, "severity": "error", "message": message}],
            )

        dataset = load_structured_dataset(
            self.database_path,
            required_columns=[],
            table_name=self.table_name,
        )
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(self.domain_config, graph)
        basis = _rank_basis(registry)
        if basis is None:
            return _blocked("missing_rank_basis", "当前数据缺少可审核的位次字段。")

        grounding = PreferenceGrounder(registry).ground(intent.preferences)
        ast = _query_ast(
            rank=rank,
            registry=registry,
            basis=basis,
            grounded_filters=grounding.filters,
        )
        verification = SemanticQueryVerifier(
            registry,
            table_name=self.table_name,
        ).verify(ast)
        if not verification.ok:
            return SemanticAdmissionsRecommendationResult(
                query_type=QUERY_TYPE,
                status="blocked",
                rows=[],
                result_sections=_empty_sections(),
                answerable_intents=[
                    *grounding.answerable_intents,
                    *verification.answerable_intents,
                ],
                unanswerable_intents=[
                    *grounding.unanswerable_intents,
                    *verification.unanswerable_intents,
                ],
                not_executed_preferences=grounding.not_executed_preferences,
                execution_summary={
                    **_empty_execution_summary(rank=rank),
                    "verification_issues": [
                        issue.to_dict() for issue in verification.issues
                    ],
                    "verified_query_plan": verification.plan.model_dump(),
                },
                warnings=[
                    {
                        "code": "semantic_recommendation_not_verified",
                        "severity": "error",
                        "message": "候选推荐计划未通过 reviewed semantic 校验。",
                    }
                ],
            )
        built = SemanticSQLBuilder().build(verification.plan)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            raw_rows = connection.execute(built.sql, built.params).fetchdf().to_dict(
                "records"
            )
        rows = [_project_row(row, rank, basis) for row in raw_rows]
        sections = _section_rows(rows)
        return SemanticAdmissionsRecommendationResult(
            query_type=QUERY_TYPE,
            status="ok" if rows else "no_results",
            rows=rows,
            result_sections=sections,
            answerable_intents=[
                *grounding.answerable_intents,
                *verification.answerable_intents,
                {"intent": "rank_recommendation", "answerable": True, "basis": basis},
            ],
            unanswerable_intents=grounding.unanswerable_intents,
            not_executed_preferences=grounding.not_executed_preferences,
            execution_summary={
                "executor": "duckdb",
                "query_type": QUERY_TYPE,
                "sql": built.sql,
                "params": built.params,
                "input_row_count": graph.row_count,
                "filtered_row_count": len(rows),
                "rank": rank,
                "basis": basis,
                "bucket_counts": {
                    key: len(value["items"]) for key, value in sections.items()
                },
                "verified_query_plan": verification.plan.model_dump(),
            },
        )


def _query_ast(
    *,
    rank: int,
    registry: ReviewedMappingRegistry,
    basis: str,
    grounded_filters: list[dict[str, Any]],
) -> QueryAST:
    recipe = {
        "intent": QUERY_TYPE,
        "select": [field for field in DISPLAY_FIELDS if registry.has_field(field)],
        "filters": [
            {"field_id": "year", "op": "eq", "value": 2025},
            {
                "field_id": basis,
                "op": "between",
                "value": [max(1, rank - 8000), rank + 30000],
            },
            *[
                {
                    "field_id": item["field_id"],
                    "op": item["op"],
                    "value": item["value"],
                }
                for item in grounded_filters
            ],
        ],
        "sort": [{"field_id": basis, "direction": "asc"}],
        "limit": 50,
        "requested_output": ["recommendations", "risk_buckets"],
        "source": "llm_candidate_verified",
    }
    return QueryAST.from_candidate(recipe)


def _rank_basis(registry: ReviewedMappingRegistry) -> str | None:
    for field_id in ["group_min_rank", "major_min_rank"]:
        if registry.has_field(field_id) and registry.has_op(field_id, "between"):
            return field_id
    return None


def _project_row(row: dict[str, Any], rank: int, basis: str) -> dict[str, Any]:
    rank_value = _int_or_none(row.get(basis))
    margin = rank_value - rank if rank_value is not None else None
    return {
        "院校名称": row.get("university_name"),
        "专业组": row.get("group_code"),
        "专业代码": row.get("major_code"),
        "专业": row.get("major_name"),
        "最低分": _int_or_none(row.get("major_min_score")),
        "最低录取排名": rank_value,
        "相对用户排名": margin,
        "学校所在": row.get("school_province"),
        "城市": row.get("city"),
        "学费": _int_or_none(row.get("tuition_yuan_per_year")),
        "专业组最低位次": _int_or_none(row.get("group_min_rank")),
        "录取人数": _int_or_none(row.get("plan_count")),
        "档位": _section_key(margin),
    }


def _section_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sections = _empty_sections()
    section_key_by_label = {"冲": "reach", "稳": "match", "保": "safety"}
    for row in rows:
        key = section_key_by_label.get(str(row.get("档位") or ""))
        if key in sections:
            sections[key]["items"].append(row)
    return sections


def _section_key(margin: int | None) -> str:
    if margin is None:
        return "稳"
    if margin < 0:
        return "冲"
    if margin <= 15000:
        return "稳"
    return "保"


def _empty_sections() -> dict[str, dict[str, Any]]:
    return {
        "reach": {"label": "冲", "items": []},
        "match": {"label": "稳", "items": []},
        "safety": {"label": "保", "items": []},
    }


def _blocked(code: str, message: str) -> SemanticAdmissionsRecommendationResult:
    return SemanticAdmissionsRecommendationResult(
        query_type=QUERY_TYPE,
        status="blocked",
        rows=[],
        result_sections=_empty_sections(),
        answerable_intents=[],
        unanswerable_intents=[{"reason": code, "message": message}],
        not_executed_preferences=[],
        execution_summary=_empty_execution_summary(rank=None),
        warnings=[{"code": code, "severity": "error", "message": message}],
    )


def _empty_execution_summary(rank: int | None) -> dict[str, Any]:
    return {
        "executor": None,
        "query_type": QUERY_TYPE,
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
        "rank": rank,
        "basis": None,
        "verified_query_plan": None,
    }


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value).replace(",", "").replace("，", ""))
    except ValueError:
        return None
    return int(parsed) if math.isfinite(parsed) else None
```

- [ ] **Step 5: Run planner tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_recommendation
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/semantic/admissions_recommendation.py domains/admissions/semantic_capabilities.json tests/test_semantic_admissions_recommendation.py
git commit -m "feat: execute semantic admissions recommendations"
```

## Task 5: Evidence-Bounded Reranker And Validator

**Files:**
- Create: `src/semantic/evidence_bounded_reranker.py`
- Create: `src/semantic/rerank_validator.py`
- Modify: `src/semantic/admissions_recommendation.py`
- Test: `tests/test_semantic_reranker.py`
- Test: `tests/test_semantic_admissions_recommendation.py`

- [ ] **Step 1: Write failing reranker and validator tests**

Create `tests/test_semantic_reranker.py`:

```python
from __future__ import annotations

import unittest

from src.semantic.evidence_bounded_reranker import EvidenceBoundedReranker
from src.semantic.rerank_validator import RerankValidator


class FakeDeepSeekClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, str]] = []

    def chat_json(self, system_prompt: str, user_prompt: str):
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})

        class Response:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload
                self.usage = {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "total_tokens": 30,
                }

        return Response(self.payload)


CANDIDATES = [
    {
        "row_id": "r_001",
        "档位": "稳",
        "院校名称": "深圳大学",
        "专业": "计算机科学与技术",
        "最低录取排名": 15020,
        "相对用户排名": 20,
        "deterministic_evidence": ["bucket_match", "major_match", "rank_near"],
    },
    {
        "row_id": "r_002",
        "档位": "保",
        "院校名称": "广东工业大学",
        "专业": "人工智能",
        "最低录取排名": 21000,
        "相对用户排名": 6000,
        "deterministic_evidence": ["bucket_safety", "major_match"],
    },
]


class EvidenceBoundedRerankerTest(unittest.TestCase):
    def test_reranker_only_returns_row_id_selections(self) -> None:
        client = FakeDeepSeekClient(
            {
                "selected": [
                    {
                        "row_id": "r_002",
                        "bucket": "保",
                        "reason_codes": ["major_match"],
                        "reason": "专业命中人工智能。",
                    },
                    {
                        "row_id": "r_001",
                        "bucket": "稳",
                        "reason_codes": ["major_match", "rank_near"],
                        "reason": "专业命中计算机且位次接近。",
                    },
                ],
                "not_used_preferences": [
                    {
                        "source_text": "不想去国外",
                        "reason": "候选数据没有境外办学字段，不能执行。",
                    }
                ],
            }
        )
        reranker = EvidenceBoundedReranker(client=client)

        result = reranker.rerank(
            user_request="我的排位是15000，想读人工智能，计算机",
            candidates=CANDIDATES,
            not_executed_preferences=[],
            limits={"冲": 10, "稳": 13, "保": 10},
        )

        self.assertEqual([item["row_id"] for item in result.selected], ["r_002", "r_001"])
        self.assertIn("候选", client.calls[0]["user_prompt"])
        self.assertNotIn("raw_excel", client.calls[0]["user_prompt"])

    def test_validator_rejects_external_row_id_and_bad_reason_code(self) -> None:
        validator = RerankValidator(allowed_reason_codes={"major_match", "rank_near"})
        validated = validator.validate(
            candidates=CANDIDATES,
            proposed=[
                {
                    "row_id": "r_999",
                    "bucket": "稳",
                    "reason_codes": ["major_match"],
                    "reason": "不存在的行。",
                },
                {
                    "row_id": "r_001",
                    "bucket": "稳",
                    "reason_codes": ["invented_school_tier"],
                    "reason": "引用了未提供字段。",
                },
            ],
            limits={"冲": 10, "稳": 13, "保": 10},
        )

        self.assertFalse(validated.ok)
        self.assertEqual([item["row_id"] for item in validated.selected], ["r_001", "r_002"])
        self.assertEqual(validated.fallback_reason, "invalid_rerank_output")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run failing reranker tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_reranker
```

Expected: FAIL with missing `evidence_bounded_reranker` and `rerank_validator`.

- [ ] **Step 3: Implement evidence-bounded reranker**

Create `src/semantic/evidence_bounded_reranker.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.extractors.deepseek_extractor import DeepSeekClient


class JSONChatClient(Protocol):
    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        """返回 JSON payload 和 usage。"""


@dataclass(frozen=True)
class RerankResult:
    selected: list[dict[str, Any]]
    not_used_preferences: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


class EvidenceBoundedReranker:
    """LLM 只能在 bounded candidates 内选择 row_id。"""

    def __init__(self, client: JSONChatClient | None = None) -> None:
        self.client = client or DeepSeekClient()

    def rerank(
        self,
        *,
        user_request: str,
        candidates: list[dict[str, Any]],
        not_executed_preferences: list[dict[str, Any]],
        limits: dict[str, int],
    ) -> RerankResult:
        response = self.client.chat_json(
            system_prompt=(
                "你是证据受限的招生推荐 reranker。只能从候选 row_id 中选择，"
                "不能新增学校、专业、分数、位次或筛选条件。只返回 JSON。"
            ),
            user_prompt=(
                "请按用户偏好在候选内排序。"
                "禁止引用候选字段之外的信息，禁止声称未执行偏好已执行。"
                "输出 JSON：{\"selected\":[{\"row_id\":string,\"bucket\":string,"
                "\"reason_codes\":[string],\"reason\":string}],"
                "\"not_used_preferences\":[{\"source_text\":string,\"reason\":string}]}。"
                f"每档数量限制：{json.dumps(limits, ensure_ascii=False)}。"
                f"未执行偏好：{json.dumps(not_executed_preferences, ensure_ascii=False)}。"
                f"候选：{json.dumps(_compact_candidates(candidates), ensure_ascii=False)}。"
                f"用户输入：{user_request}"
            ),
        )
        payload = dict(response.payload)
        return RerankResult(
            selected=[
                item for item in payload.get("selected") or [] if isinstance(item, dict)
            ],
            not_used_preferences=[
                item
                for item in payload.get("not_used_preferences") or []
                if isinstance(item, dict)
            ],
            usage=dict(getattr(response, "usage", {}) or {}),
            raw_payload=payload,
        )


def _compact_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = [
        "row_id",
        "档位",
        "院校名称",
        "专业组",
        "专业",
        "最低录取排名",
        "相对用户排名",
        "学校所在",
        "城市",
        "录取人数",
        "deterministic_evidence",
    ]
    return [{key: row.get(key) for key in allowed if key in row} for row in candidates]
```

- [ ] **Step 4: Implement rerank validator**

Create `src/semantic/rerank_validator.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidatedRerank:
    ok: bool
    selected: list[dict[str, Any]]
    rejected: list[dict[str, Any]] = field(default_factory=list)
    fallback_reason: str | None = None


class RerankValidator:
    def __init__(self, allowed_reason_codes: set[str] | None = None) -> None:
        self.allowed_reason_codes = allowed_reason_codes or {
            "major_match",
            "rank_near",
            "bucket_reach",
            "bucket_match",
            "bucket_safety",
            "location_match",
            "available_school_tag",
        }

    def validate(
        self,
        *,
        candidates: list[dict[str, Any]],
        proposed: list[dict[str, Any]],
        limits: dict[str, int],
    ) -> ValidatedRerank:
        by_id = {str(row.get("row_id")): row for row in candidates}
        selected: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        counts = {label: 0 for label in limits}
        seen: set[str] = set()
        for item in proposed:
            row_id = str(item.get("row_id") or "")
            if row_id not in by_id or row_id in seen:
                rejected.append({"row_id": row_id, "reason": "unknown_or_duplicate_row"})
                continue
            candidate = by_id[row_id]
            bucket = str(item.get("bucket") or "")
            if bucket != str(candidate.get("档位") or ""):
                rejected.append({"row_id": row_id, "reason": "bucket_mismatch"})
                continue
            if counts.get(bucket, 0) >= limits.get(bucket, 0):
                rejected.append({"row_id": row_id, "reason": "bucket_limit_exceeded"})
                continue
            reason_codes = [str(code) for code in item.get("reason_codes") or []]
            if any(code not in self.allowed_reason_codes for code in reason_codes):
                rejected.append({"row_id": row_id, "reason": "unsupported_reason_code"})
                continue
            output = dict(candidate)
            output["rerank_reason"] = item.get("reason")
            output["rerank_reason_codes"] = reason_codes
            selected.append(output)
            seen.add(row_id)
            counts[bucket] = counts.get(bucket, 0) + 1
        if rejected:
            return ValidatedRerank(
                ok=False,
                selected=_deterministic_fallback(candidates, limits),
                rejected=rejected,
                fallback_reason="invalid_rerank_output",
            )
        return ValidatedRerank(ok=True, selected=selected, rejected=[])


def _deterministic_fallback(
    candidates: list[dict[str, Any]],
    limits: dict[str, int],
) -> list[dict[str, Any]]:
    counts = {label: 0 for label in limits}
    output: list[dict[str, Any]] = []
    sorted_candidates = sorted(
        candidates,
        key=lambda row: (
            abs(int(row.get("相对用户排名") or 0)),
            int(row.get("最低录取排名") or 0),
            str(row.get("院校名称") or ""),
            str(row.get("专业") or ""),
        ),
    )
    for row in sorted_candidates:
        bucket = str(row.get("档位") or "")
        if counts.get(bucket, 0) >= limits.get(bucket, 0):
            continue
        output.append(dict(row))
        counts[bucket] = counts.get(bucket, 0) + 1
    return output
```

- [ ] **Step 5: Wire reranker into admissions recommendation**

In `src/semantic/admissions_recommendation.py`, after SQL candidates are projected but before `result_sections` are created:

```python
        candidates = [
            {
                **row,
                "row_id": f"r_{index:03d}",
                "deterministic_evidence": _deterministic_evidence(row),
            }
            for index, row in enumerate(rows, start=1)
        ]
        rerank = EvidenceBoundedReranker().rerank(
            user_request=intent.model_dump_json(),
            candidates=candidates,
            not_executed_preferences=grounding.not_executed_preferences,
            limits={"冲": 10, "稳": 13, "保": 10},
        )
        validated = RerankValidator().validate(
            candidates=candidates,
            proposed=rerank.selected,
            limits={"冲": 10, "稳": 13, "保": 10},
        )
        rows = validated.selected
```

Add this helper in the same file:

```python
def _deterministic_evidence(row: dict[str, Any]) -> list[str]:
    evidence = []
    bucket = row.get("档位")
    if bucket == "冲":
        evidence.append("bucket_reach")
    elif bucket == "稳":
        evidence.append("bucket_match")
    elif bucket == "保":
        evidence.append("bucket_safety")
    if row.get("专业"):
        evidence.append("major_match")
    if row.get("相对用户排名") is not None:
        evidence.append("rank_near")
    if row.get("学校所在"):
        evidence.append("location_match")
    return evidence
```

Add these imports:

```python
from src.semantic.evidence_bounded_reranker import EvidenceBoundedReranker
from src.semantic.rerank_validator import RerankValidator
```

Add these keys to `execution_summary`:

```python
                "candidate_row_count": len(candidates),
                "rerank": {
                    "used": True,
                    "valid": validated.ok,
                    "fallback_reason": validated.fallback_reason,
                    "rejected": validated.rejected,
                    "usage": rerank.usage,
                },
```

- [ ] **Step 6: Run reranker tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_reranker tests.test_semantic_admissions_recommendation
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/semantic/evidence_bounded_reranker.py src/semantic/rerank_validator.py src/semantic/admissions_recommendation.py tests/test_semantic_reranker.py tests/test_semantic_admissions_recommendation.py
git commit -m "feat: add evidence bounded reranking"
```

## Task 6: Workbench Uploaded Admissions Integration

**Files:**
- Modify: `src/api/workbench.py`
- Modify: `tests/test_uploaded_dataset_flow.py`
- Modify: `tests/workbench_contract_utils.py` only if contract helper needs a new required evidence field

- [ ] **Step 1: Add failing uploaded flow tests**

In `tests/test_uploaded_dataset_flow.py`, add a test to `UploadedSemanticAdmissionsFlowTest`:

```python
    def test_uploaded_new_admissions_recommendation_uses_semantic_path(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        payload = {
            "query_type": "semantic_recommendation",
            "user_context": {
                "user_rank": 15000,
                "user_score": None,
                "source_province": "广东",
                "subject_type": None,
                "reselected_subjects": [],
            },
            "preferences": [
                {
                    "source_text": "人工智能，计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                },
                {
                    "source_text": "想留在广东省",
                    "semantic": "school_province",
                    "op": "in",
                    "value": ["广东"],
                },
                {
                    "source_text": "不想去国外",
                    "semantic": "school_country_or_region",
                    "op": "not_in",
                    "value": ["国外", "境外", "海外"],
                },
            ],
            "requested_output": ["recommendations"],
        }
        with TemporaryDirectory() as directory:
            source = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_new_admissions_recommendation",
            )
            service.generate_domain_pack(
                "ds_new_admissions_recommendation",
                domain_name="admissions",
                base_domain="admissions",
            )
            self.assertTrue(service.approve_domain("ds_new_admissions_recommendation")["ok"])
            service.build_warehouse("ds_new_admissions_recommendation")
            with patch(
                "src.semantic.llm_intent_extractor.DeepSeekClient"
            ) as client_class:
                client = client_class.return_value

                class Response:
                    def __init__(self) -> None:
                        self.payload = payload
                        self.usage = {
                            "prompt_tokens": 10,
                            "completion_tokens": 10,
                            "total_tokens": 20,
                        }

                client.chat_json.return_value = Response()
                response = service.query(
                    "ds_new_admissions_recommendation",
                    user_input=query,
                    soft_preferences={"prompt": query},
                )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "semantic_recommendation")
        self.assertTrue(response["top_results"])
        self.assertEqual(
            response["evidence_pack"]["not_executed_preferences"][0]["field_id"],
            "school_country_or_region",
        )
        self.assertEqual(
            response["evidence_pack"]["execution_summary"]["basis"],
            "major_min_rank",
        )
```

Add score-only test:

```python
    def test_uploaded_new_admissions_score_only_recommendation_needs_rank(self) -> None:
        query = "假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        payload = {
            "query_type": "semantic_recommendation",
            "user_context": {
                "user_rank": None,
                "user_score": 630,
                "source_province": "广东",
                "subject_type": None,
                "reselected_subjects": [],
            },
            "preferences": [
                {
                    "source_text": "人工智能，计算机",
                    "semantic": "major_name",
                    "op": "contains_any",
                    "value": ["人工智能", "计算机"],
                }
            ],
            "requested_output": ["recommendations"],
        }
        with TemporaryDirectory() as directory:
            source = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_new_admissions_score_only",
            )
            service.generate_domain_pack(
                "ds_new_admissions_score_only",
                domain_name="admissions",
                base_domain="admissions",
            )
            self.assertTrue(service.approve_domain("ds_new_admissions_score_only")["ok"])
            service.build_warehouse("ds_new_admissions_score_only")
            with patch(
                "src.semantic.llm_intent_extractor.DeepSeekClient"
            ) as client_class:
                client = client_class.return_value

                class Response:
                    def __init__(self) -> None:
                        self.payload = payload
                        self.usage = {
                            "prompt_tokens": 10,
                            "completion_tokens": 10,
                            "total_tokens": 20,
                        }

                client.chat_json.return_value = Response()
                response = service.query(
                    "ds_new_admissions_score_only",
                    user_input=query,
                    soft_preferences={"prompt": query},
                )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "needs_confirmation")
        self.assertEqual(response["query_type"], "semantic_recommendation")
        self.assertEqual(response["top_results"], [])
        self.assertIn("score_without_rank", [item["code"] for item in response["warnings"]])
        self.assertEqual(
            response["evidence_pack"]["execution_summary"]["sql"],
            "",
        )
```

- [ ] **Step 2: Run uploaded semantic tests to verify failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: FAIL because Workbench still routes generic recommendation to legacy planner.

- [ ] **Step 3: Implement Workbench semantic recommendation route**

In `src/api/workbench.py`, import:

```python
from src.semantic.admissions_recommendation import (
    SemanticAdmissionsRecommendationPlanner,
)
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.llm_intent_extractor import DeepSeekSemanticIntentExtractor
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
```

Add a helper near the existing semantic major rank helpers:

```python
def _maybe_run_semantic_recommendation(
    *,
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    database_path: Path,
    warehouse_audit: dict[str, Any],
) -> dict[str, Any] | None:
    prompt = _compose_user_request(config)
    if "推荐" not in prompt:
        return None
    if not domain_config.semantic_capabilities:
        return None
    schema_context = _semantic_schema_context(domain_config, database_path)
    extraction = DeepSeekSemanticIntentExtractor().extract(
        prompt,
        schema_context=schema_context,
        hard_context={
            "hard_filters": dict(config.hard_filters or {}),
            "soft_preferences": dict(config.soft_preferences or {}),
        },
    )
    if extraction.intent.query_type != "semantic_recommendation":
        return None
    result = SemanticAdmissionsRecommendationPlanner(
        domain_config=domain_config,
        database_path=database_path,
        table_name=domain_config.table_name,
    ).run(extraction.intent)
    return _semantic_recommendation_response(
        result,
        extraction_result=extraction,
        warehouse_audit=warehouse_audit,
        domain_config=domain_config,
        config=config,
    )
```

Add schema context helper:

```python
def _semantic_schema_context(
    domain_config: DomainConfig,
    database_path: Path,
) -> list[dict[str, Any]]:
    dataset = load_structured_dataset(
        database_path,
        required_columns=[],
        table_name=domain_config.table_name,
    )
    graph = DatasetCapabilityGraph.from_dataset(dataset)
    registry = ReviewedMappingRegistry.from_domain(domain_config, graph)
    return registry.active_field_dicts() + [
        {
            "field_id": field_id,
            "active": False,
            "unsupported_reason": registry.unsupported_reason(field_id),
        }
        for field_id in registry.unsupported_field_ids()
    ]
```

Add response helper:

```python
def _semantic_recommendation_response(
    result: Any,
    *,
    extraction_result: Any,
    warehouse_audit: dict[str, Any],
    domain_config: DomainConfig,
    config: WorkbenchConfig,
) -> dict[str, Any]:
    rows = result.rows
    items = _semantic_items(rows)
    top_results = _semantic_top_results(rows)
    evidence_pack = {
        "user_request": _compose_user_request(config),
        "query_type": result.query_type,
        "executed_rules": [],
        "candidate_confirmations": [],
        "answerable_intents": result.answerable_intents,
        "unanswerable_intents": result.unanswerable_intents,
        "not_executed_preferences": result.not_executed_preferences,
        "result_count": len(rows),
        "top_k_results": top_results,
        "result_sections": result.result_sections,
        "execution_summary": result.execution_summary,
        "llm_candidate_intent": extraction_result.intent.model_dump(),
        "llm_usage": extraction_result.usage,
    }
    answer = _semantic_recommendation_answer(result)
    legacy_payload = {
        "mode": "api",
        "status": result.status,
        "query_type": result.query_type,
        "user_input": _compose_user_request(config),
        "data_warehouse": warehouse_audit,
        "hard_filters": _display_hard_filters_for_domain(config, domain_config),
        "soft_preferences": _display_soft_preferences_for_domain(
            config,
            domain_config,
        ),
        "selected_options": _selected_options(config),
        "extracted_preferences": [],
        "extracted_slots": extraction_result.intent.model_dump(),
        "attribute_grounding": {"summary": {}, "attributes": []},
        "confirmation_candidates": [],
        "confirmation_state": _display_confirmation_state(
            {"no_schema_field_preferences": result.not_executed_preferences}
        ),
        "proposed_rules": [],
        "deterministic_rules": [],
        "candidate_rules": [],
        "not_executed_preferences": result.not_executed_preferences,
        "simulated_confirmations": {},
        "executable_rules": [],
        "execution": result.execution_summary,
        "result_count": len(rows),
        "items": items,
        "top_results": top_results,
        "result_sections": result.result_sections,
        "trace": {},
        "evidence_pack": evidence_pack,
        "natural_language_report": {
            "title": "Semantic recommendation 结果",
            "summary": answer,
            "full_text": answer,
            "result_count_text": f"当前返回 {len(rows)} 条结果。",
            "executed_rules": [],
            "attribute_explanations": [],
            "top_results": top_results,
            "warnings": result.warnings,
            "disclaimer": "只执行已审查语义字段；缺字段偏好不会被暗示为已执行。",
        },
        "token_usage": {
            "extractor": extraction_result.usage,
            "generator": None,
            "total": extraction_result.usage,
        },
    }
    response = WorkbenchResponse(
        schema_version=WORKBENCH_SCHEMA_VERSION,
        domain=domain_config.domain_id,
        domain_version=domain_config.domain_version,
        domain_pack_status=domain_config.pack_status,
        status=result.status,
        query_type=result.query_type,
        query=_contract_query(config),
        answer=answer,
        items=items,
        top_results=top_results,
        result_sections=result.result_sections,
        result_count=len(rows),
        executed_filters=[],
        candidates_to_confirm=[],
        confirmed_rules=[],
        unconfirmed_candidates=[],
        unexecuted_preferences=result.not_executed_preferences,
        no_schema_field_preferences=result.not_executed_preferences,
        rejected_confirmations=[],
        warnings=_contract_warnings(
            result.warnings,
            status=result.status,
            confirmation_state=legacy_payload["confirmation_state"],
        ),
        evidence_pack=evidence_pack,
        debug_trace={
            "execution": result.execution_summary,
            "data_warehouse": warehouse_audit,
            "llm_candidate_intent": extraction_result.intent.model_dump(),
        },
    ).to_dict()
    return {**legacy_payload, **response}
```

Add answer helper:

```python
def _semantic_recommendation_answer(result: Any) -> str:
    if result.status == "needs_confirmation":
        warning = result.warnings[0] if result.warnings else {}
        return warning.get("message") or "请先补充广东省排位/位次。"
    if result.status == "blocked":
        warning = result.warnings[0] if result.warnings else {}
        return warning.get("message") or "当前请求未通过语义能力校验，未执行 SQL。"
    lines = [
        "本次由 LLM 生成候选语义意图，系统仅执行 reviewed mapping 校验通过的字段。",
        f"位次依据：{result.execution_summary.get('basis')}。",
    ]
    if result.not_executed_preferences:
        labels = "、".join(
            str(item.get("source_text") or item.get("field_id"))
            for item in result.not_executed_preferences
        )
        lines.append(f"未执行偏好：{labels}。")
    for section_key in ["reach", "match", "safety"]:
        section = result.result_sections.get(section_key) or {}
        label = section.get("label") or section_key
        for row in section.get("items") or []:
            lines.append(
                f"{label}：{row.get('院校名称')} {row.get('专业组')} "
                f"{row.get('专业')}，最低录取排名 {row.get('最低录取排名')}。"
            )
    return "\n".join(lines)
```

Insert semantic recommendation before the legacy `AdmissionsQueryPlanner` route in the uploaded admissions branch:

```python
    semantic_recommendation = _maybe_run_semantic_recommendation(
        config=config,
        domain_config=domain_config,
        database_path=database_path,
        warehouse_audit=warehouse_audit,
    )
    if semantic_recommendation is not None:
        return semantic_recommendation
```

- [ ] **Step 4: Run uploaded semantic tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 5: Run API contract tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py tests/workbench_contract_utils.py
git commit -m "feat: route uploaded recommendations through semantic planner"
```

## Task 7: Expand Major Rank Output And Avoid Bucket Truncation

**Files:**
- Modify: `src/semantic/admissions_major_rank.py`
- Modify: `tests/test_semantic_admissions_major_rank.py`
- Modify: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: Add failing multi-row bucket tests**

In `tests/test_semantic_admissions_major_rank.py`, add:

```python
    def test_major_rank_plan_returns_multiple_rows_per_bucket(self) -> None:
        result = self._run(
            "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
        )

        labels = [row["档位"] for row in result.rows]
        self.assertGreaterEqual(labels.count("冲"), 2)
        self.assertGreaterEqual(labels.count("稳"), 2)
        self.assertGreaterEqual(labels.count("保"), 1)
        self.assertEqual(
            result.execution_summary["bucket_selected_counts"]["冲"],
            labels.count("冲"),
        )

    def test_major_rank_plan_does_not_limit_before_safety_bucket(self) -> None:
        result = self._run(
            "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
        )

        safety_rows = [row for row in result.rows if row["档位"] == "保"]
        self.assertTrue(safety_rows)
        self.assertGreaterEqual(
            result.execution_summary["bucket_candidate_counts"]["保"],
            len(safety_rows),
        )
```

If the current fixture only has one row per bucket, extend `tests/semantic_test_utils.py` fixture with two extra compatible rows:

```python
{
    "年份": 2025,
    "院校名称": "暨南大学",
    "院校代码": "10559",
    "科类": "物理类",
    "批次": "本科批",
    "专业": "软件工程",
    "专业代码": "002",
    "所属专业组": "（222）",
    "专业备注": "",
    "选科要求": "首选物理，再选化学",
    "录取人数": 20,
    "最低分数": 616,
    "最低位次": 16212,
    "学校所在": "广东",
    "学校性质": "公办",
    "是否985": "否",
    "是否211": "是",
}
```

- [ ] **Step 2: Run failing major rank tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_major_rank
```

Expected: FAIL because `_bucket_rows` currently selects one row per bucket.

- [ ] **Step 3: Implement per-bucket selection**

Modify `src/semantic/admissions_major_rank.py`:

```python
BUCKET_LIMITS = {"冲": 12, "稳": 12, "保": 12}
```

Change `_query_ast` limit from `100` to:

```python
            "limit": 1000,
```

Pydantic currently clamps `QueryAST.limit` to 100. Add `fetch_limit` handling inside `AdmissionsMajorRankPlanner.run` after SQL build:

```python
        built = SemanticSQLBuilder().build(verification.plan)
        sql = built.sql
        params = list(built.params)
        if params:
            params[-1] = 1000
```

Replace `_bucket_rows` with:

```python
def _bucket_rows(
    raw_rows: list[dict[str, Any]],
    rank: int,
    capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    special_terms = [str(term) for term in capabilities.get("special_limit_terms") or []]
    normal_rows = [
        row for row in raw_rows if not _has_special_limit(row, special_terms)
    ]
    buckets = [
        ("冲", rank - 1500, rank - 1),
        ("稳", rank, rank + 3000),
        ("保", rank + 3001, rank + 9000),
    ]
    output: list[dict[str, Any]] = []
    for label, lower, upper in buckets:
        candidates = [
            row
            for row in normal_rows
            if _rank_in_bucket(row.get("major_min_rank"), lower, upper)
        ]
        candidates.sort(
            key=lambda row: (
                abs(int(row["major_min_rank"]) - rank),
                int(row["major_min_rank"]),
                str(row.get("university_name") or ""),
                str(row.get("major_name") or ""),
            )
        )
        for selected in candidates[: BUCKET_LIMITS[label]]:
            output.append(_project_row(label, selected, rank))
    return output
```

Add summary counts before returning:

```python
        bucket_candidate_counts = _bucket_candidate_counts(
            subject_rows,
            rank,
            self.domain_config.semantic_capabilities,
        )
        bucket_selected_counts = {
            label: sum(1 for row in rows if row["档位"] == label)
            for label in ["冲", "稳", "保"]
        }
```

Add helper:

```python
def _bucket_candidate_counts(
    raw_rows: list[dict[str, Any]],
    rank: int,
    capabilities: dict[str, Any],
) -> dict[str, int]:
    special_terms = [str(term) for term in capabilities.get("special_limit_terms") or []]
    normal_rows = [
        row for row in raw_rows if not _has_special_limit(row, special_terms)
    ]
    ranges = {
        "冲": (rank - 1500, rank - 1),
        "稳": (rank, rank + 3000),
        "保": (rank + 3001, rank + 9000),
    }
    return {
        label: sum(
            1
            for row in normal_rows
            if _rank_in_bucket(row.get("major_min_rank"), lower, upper)
        )
        for label, (lower, upper) in ranges.items()
    }
```

Include these keys in `execution_summary`:

```python
                "bucket_candidate_counts": bucket_candidate_counts,
                "bucket_selected_counts": bucket_selected_counts,
                "sql_fetch_limit": params[-1] if params else None,
```

- [ ] **Step 4: Run major rank tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_major_rank tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/admissions_major_rank.py tests/test_semantic_admissions_major_rank.py tests/test_uploaded_dataset_flow.py tests/semantic_test_utils.py
git commit -m "feat: return multi-row major rank buckets"
```

## Task 8: Probe Script And Live DeepSeek Smoke

**Files:**
- Modify: `scripts/run_semantic_capability_probe.py`
- Test: manual command with local `.env`

- [ ] **Step 1: Add CLI options**

Modify `_arg_parser()`:

```python
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="使用 .env 中的 DeepSeek key 跑语义 intent extractor smoke。",
    )
    parser.add_argument(
        "--keep-root",
        action="store_true",
        help="保留 root 目录用于手工检查；默认由调用者决定是否清理。",
    )
```

The script already accepts `--query`; keep that behavior.

- [ ] **Step 2: Add compact output mode for recommendation**

Inside `run_probe()`, include `query_type`, `status`, `answer`, `top_results`, and compact evidence only. Keep upload/build summaries, but do not print full `field_profiles`.

Use this code shape:

```python
    evidence = response.get("evidence_pack") or {}
    summary = evidence.get("execution_summary") or {}
    return 0, {
        "upload": {
            "dataset_id": upload.get("dataset_id"),
            "row_count": upload.get("row_count"),
            "column_count": upload.get("column_count"),
            "source_fingerprint": upload.get("source_fingerprint"),
        },
        "build": {
            "status": build.get("status"),
            "warehouse_database_path": build.get("warehouse_database_path"),
        },
        "status": response.get("status"),
        "query_type": response.get("query_type"),
        "answer": response.get("answer"),
        "top_results": response.get("top_results", []),
        "evidence_pack": {
            "answerable_intents": evidence.get("answerable_intents", []),
            "unanswerable_intents": evidence.get("unanswerable_intents", []),
            "not_executed_preferences": evidence.get("not_executed_preferences", []),
            "execution_summary": {
                "executor": summary.get("executor"),
                "query_type": summary.get("query_type"),
                "sql": summary.get("sql"),
                "params": summary.get("params"),
                "filtered_row_count": summary.get("filtered_row_count"),
                "rank": summary.get("rank"),
                "basis": summary.get("basis"),
                "bucket_counts": summary.get("bucket_counts"),
                "candidate_row_count": summary.get("candidate_row_count"),
                "rerank": summary.get("rerank"),
            },
        },
    }
```

- [ ] **Step 3: Run non-live probe**

Run:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py \
  "/Users/tz/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/4c3344e6e0eb93b6117c7beb32e4cc5f/Message/MessageTemp/852a31997f8ce6410ad61299d5b75338/File/22-25年全国高校在广东的专业录取分数.xlsx" \
  --dataset-id ds_latest_admissions_probe \
  --root /tmp/szu_semantic_probe \
  --query "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
```

Expected: JSON with `status: ok`, `query_type: admissions_major_rank`, and at least one `保` item if source data has safety candidates.

- [ ] **Step 4: Run live LLM recommendation probe**

Do not print `.env`. Run:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py \
  "/Users/tz/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/4c3344e6e0eb93b6117c7beb32e4cc5f/Message/MessageTemp/852a31997f8ce6410ad61299d5b75338/File/22-25年全国高校在广东的专业录取分数.xlsx" \
  --dataset-id ds_latest_admissions_live_llm \
  --root /tmp/szu_semantic_probe_live \
  --query "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐" \
  --live-llm
```

Expected: JSON with `query_type: semantic_recommendation`, `status: ok`, `execution_summary.executor: duckdb`, `execution_summary.basis: major_min_rank`, `execution_summary.rerank.valid: true`, bounded `top_results`, and `not_executed_preferences` containing `school_country_or_region`.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_semantic_capability_probe.py
git commit -m "chore: add semantic recommendation probe output"
```

## Task 9: Docs, Regression Suite, And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`
- Test: full repository test suite

- [ ] **Step 1: Update README behavior summary**

Add this Chinese paragraph near the uploaded admissions semantic capability section:

```markdown
uploaded admissions 的普通推荐请求会先由 DeepSeek 生成候选 `SemanticIntent`，再由 reviewed semantic mapping 校验字段和操作。用户说“我的排位是15000，想读人工智能、计算机，想留在广东省”时，系统可以执行 `major_name contains_any`、`school_province in` 和位次窗口；用户说“不想去国外”但当前表没有境外办学字段时，该偏好进入 `not_executed_preferences`，不会被暗示为已执行。推荐排序采用 evidence-bounded reranker：LLM 只能在 SQL 召回的候选 `row_id` 中排序，validator 会拒绝候选集外结果或 unsupported reason。只有分数没有位次时继续返回 `needs_confirmation`，不执行推荐 SQL。
```

- [ ] **Step 2: Update API contract**

In `docs/api_contract.md`, add this contract note under `POST /workbench/query`:

```markdown
当 uploaded admissions 数据集具备 `semantic_capabilities.json` 且 LLM 候选意图为 `semantic_recommendation` 时，Workbench 返回同一个 `WorkbenchResponse` contract，但 `evidence_pack.execution_summary.query_type` 为 `semantic_recommendation`。`evidence_pack.llm_candidate_intent` 保存 LLM 候选结构；`not_executed_preferences` 保存缺字段或不支持操作的偏好。LLM 候选不包含 SQL，SQL 只来自 verified `QueryAST`。如果启用 rerank，`execution_summary.rerank` 必须记录候选数量、LLM usage、validator 结果、fallback reason 和 rejected selections。
```

- [ ] **Step 3: Update methodology report**

In `docs/methodology_report.md`, add this method note:

```markdown
本阶段将 LLM 从 answer 层前移到 candidate intent 和 bounded rerank 层：LLM 读取 reviewed schema 摘要并输出 `SemanticIntent`，但不执行、不确认字段、不生成 SQL。`PreferenceGrounder` 会把缺字段偏好保留下来，`SemanticQueryVerifier` 只验证可执行 filters，`SemanticSQLBuilder` 生成参数化 SQL。推荐场景下，LLM reranker 只接收 bounded candidate rows 并返回 row_id 排序；`RerankValidator` 校验后才进入 EvidencePack，最终回答只使用 EvidencePack。
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_semantic_query_options \
  tests.test_semantic_llm_intent_extractor \
  tests.test_semantic_preference_grounder \
  tests.test_semantic_reranker \
  tests.test_semantic_admissions_recommendation \
  tests.test_semantic_sql_builder \
  tests.test_semantic_admissions_major_rank \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest \
  tests.test_workbench_api_contract
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: `OK` with the repository's existing expected failures only.

- [ ] **Step 6: Run syntax and diff checks**

Run:

```bash
.venv/bin/python -m py_compile \
  src/semantic/intent_models.py \
  src/semantic/query_options.py \
  src/semantic/llm_intent_extractor.py \
  src/semantic/preference_grounder.py \
  src/semantic/evidence_bounded_reranker.py \
  src/semantic/rerank_validator.py \
  src/semantic/admissions_recommendation.py \
  src/semantic/sql_builder.py \
  src/semantic/admissions_major_rank.py \
  src/api/workbench.py
git diff --check
git status --short
```

Expected: py_compile exits 0, `git diff --check` exits 0, and `git status --short` only shows files intentionally changed by this plan before the final commit.

- [ ] **Step 7: Commit docs and final verification**

```bash
git add README.md docs/api_contract.md docs/methodology_report.md
git commit -m "docs: describe llm semantic recommendation flow"
```

If any code files changed during final fixes, include them in the same commit only when they are directly required by the verification fixes.

## Self-Review

- Spec coverage: the plan covers upload-derived schema/query options, LLM candidate intent extraction, reviewed mapping grounding, verified SQL execution, bounded candidate retrieval, evidence-bounded reranking, EvidencePack-only answering, exact `排位是15000` recommendation prompt, score-only refusal, no-schema `不想去国外`, and multi-row major-rank bucket output.
- Placeholder scan: the plan does not contain unresolved placeholder work, empty “add tests” instructions, or any executable path for raw SQL. Every task has concrete files, commands, expected outcomes, and code blocks for changed behavior.
- Type consistency: `SemanticQueryOptionsBuilder` is introduced before prompt usage; `SemanticIntent` and `SemanticPreference` are introduced in Task 1, consumed by the extractor in Task 2, consumed by `PreferenceGrounder` in Task 3, and consumed by `SemanticAdmissionsRecommendationPlanner` in Task 4. Rerank output types are introduced before Workbench integration. `contains_any` is added to SQL builder before the planner uses it.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-22-llm-reviewed-semantic-recommendation.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
