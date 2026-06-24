# Evidence Requirement Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 uploaded admissions 的 LLM semantic recommendation 链路中强制接入 `EvidenceRequirementClassifier`，把需要 reviewed KB、reviewed ranking policy、用户边界或 unsupported 的 preference 分流到 evidence，不让它们进入 SQL filter、RankingPlan prompt 或 final answer claim。

**Architecture:** 新增 `src/semantic/evidence_requirement_gate.py` 作为 runtime gate：它只过滤 `SemanticIntent.preferences` 并产出 evidence annotations，不构造 SQL、不替代 verifier。Workbench 在 `DeepSeekSemanticIntentExtractor` 成功产出 `semantic_recommendation` 后调用 gate，再把 filtered intent 传给 `PreferenceGrounder`、`SemanticQueryVerifier` 和现有 RankingPlan generation。当前 `DeepSeekRankingPlanGenerator` 尚不消费 DuckDB candidate rows；本计划先保证 ranking prompt 只看 gate 后 intent，candidate-aware ranking generation 作为后续独立重构。

**Tech Stack:** Python `unittest`、Pydantic v2、现有 `DeepSeekClient` / fake client、`SemanticIntent`、`EvidenceRequirementResult`、`SemanticAdmissionsRecommendationPlanner`、`WorkbenchResponse`、DuckDB uploaded admissions fixture。

---

## File Structure

- Modify `src/semantic/evidence_requirements.py`
  - 让 classifier 支持 Workbench fake client 使用的 `messages=[...]` 调用形态。
  - 保留现有 `system_prompt` / `user_prompt` client 支持。
- Create `src/semantic/evidence_requirement_gate.py`
  - 定义 `EvidenceRequirementGate`、`EvidenceRequirementGateResult`、preference matching 和 not-executed evidence 生成。
  - 不依赖 Workbench，便于单测。
- Modify `src/semantic/__init__.py`
  - 导出 gate 类型。
- Modify `src/semantic/admissions_recommendation.py`
  - 接收 gate 预先排除的 `not_executed_preferences` 和 `unanswerable_intents`。
  - 合并进 result、execution_summary 和 warnings。
- Modify `src/api/workbench.py`
  - 在 LLM semantic recommendation intent 后调用 gate。
  - 把 filtered intent 传入 recommendation planner 和 RankingPlan generator。
  - 记录 `EvidencePack.planner.evidence_requirements` 和 token usage。
  - 分类失败时，`llm_semantic` 返回 blocked，`auto` 走 legacy fallback。
- Modify `tests/test_evidence_requirements.py`
  - 覆盖 messages-style client。
- Create `tests/test_evidence_requirement_gate.py`
  - 覆盖 filtering、匹配、unmatched requirement 保守行为和 metadata。
- Modify `tests/test_semantic_admissions_recommendation.py`
  - 覆盖 planner 合并 gate 预排除 evidence。
- Modify `tests/test_uploaded_dataset_flow.py`
  - 覆盖 runtime gate、RankingPlan prompt 过滤、适用范围排除项、失败 fallback、SQL payload redaction。
- Modify `README.md`、`docs/api_contract.md`、`docs/methodology_report.md`
  - 用中文同步描述 gate 行为和限制。

## Task 1: Classifier Client Adapter

**Files:**
- Modify: `src/semantic/evidence_requirements.py`
- Test: `tests/test_evidence_requirements.py`

- [ ] **Step 1: Write the failing test**

Append this test method inside `EvidenceRequirementTest` in `tests/test_evidence_requirements.py`:

```python
    def test_messages_style_client_response_is_supported(self) -> None:
        class _MessagesClient:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def chat_json(
                self,
                messages: list[dict[str, object]],
                temperature: float = 0.0,
            ) -> dict[str, object]:
                self.calls.append(
                    {"messages": messages, "temperature": temperature}
                )
                return {
                    "requirements": [
                        {
                            "source_text": "想读计算机",
                            "requirement_type": "table_field",
                            "candidate_semantic": "major_name",
                            "rationale": "需要专业字段。",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 3,
                        "total_tokens": 8,
                    },
                }

        client = _MessagesClient()
        result = DeepSeekEvidenceRequirementClassifier(client).classify(
            text="想读计算机",
            schema_context=[{"field_id": "major_name"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["temperature"], 0.0)
        self.assertEqual(
            result.requirements[0].candidate_semantic,
            "major_name",
        )
        self.assertEqual(result.usage["total_tokens"], 8)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_evidence_requirements.EvidenceRequirementTest.test_messages_style_client_response_is_supported
```

Expected before implementation: FAIL with `TypeError` mentioning `system_prompt` or `user_prompt` because the classifier calls the fake client with the wrong signature.

- [ ] **Step 3: Implement the client adapter**

In `src/semantic/evidence_requirements.py`, add `inspect` import and replace the direct `self.client.chat_json(...)` call in `classify()` with `_chat_json(...)` plus `_response_payload_and_usage(...)`.

Use this code:

```python
import inspect
```

```python
        response = _chat_json(
            self.client,
            _system_prompt(),
            _user_prompt(
                text=text,
                schema_context=schema_context,
                query_options=query_options,
            ),
        )
        payload, usage = _response_payload_and_usage(response)
```

Add these helpers near `_usage_dict`:

```python
def _chat_json(client: JSONChatClient, system_prompt: str, user_prompt: str) -> Any:
    signature = inspect.signature(client.chat_json)
    if (
        "messages" in signature.parameters
        and "system_prompt" not in signature.parameters
    ):
        return client.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
    return client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)


def _response_payload_and_usage(response: Any) -> tuple[Any, Any]:
    if isinstance(response, dict):
        usage = response.get("usage") or {}
        payload = {str(key): value for key, value in response.items() if key != "usage"}
        return payload, usage
    return getattr(response, "payload", {}), getattr(response, "usage", {})
```

- [ ] **Step 4: Run the focused classifier tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_evidence_requirements
```

Expected after implementation: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/evidence_requirements.py tests/test_evidence_requirements.py
git commit -m "feat: adapt evidence classifier client calls"
```

## Task 2: Evidence Requirement Gate Unit

**Files:**
- Create: `src/semantic/evidence_requirement_gate.py`
- Modify: `src/semantic/__init__.py`
- Test: `tests/test_evidence_requirement_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evidence_requirement_gate.py`:

```python
from __future__ import annotations

import unittest
from typing import Any

from src.semantic.evidence_requirement_gate import EvidenceRequirementGate
from src.semantic.evidence_requirements import (
    EvidenceRequirement,
    EvidenceRequirementResult,
)
from src.semantic.intent_models import (
    SemanticIntent,
    SemanticPreference,
    SemanticUserContext,
)


class _FakeClassifier:
    def __init__(self, result: EvidenceRequirementResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def classify(
        self,
        *,
        text: str,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementResult:
        self.calls.append(
            {
                "text": text,
                "schema_context": schema_context,
                "query_options": query_options,
            }
        )
        return self.result


class EvidenceRequirementGateTest(unittest.TestCase):
    def test_filters_non_table_field_preferences(self) -> None:
        intent = _intent(
            [
                _pref("想读人工智能，计算机", "major_name"),
                _pref("想留在广东省", "school_province"),
                _pref("好就业", "employment_outlook"),
                _pref("学校好一点", "school_quality"),
                _pref("稳一点", "risk_preference"),
            ]
        )
        classifier = _FakeClassifier(
            EvidenceRequirementResult(
                requirements=[
                    _requirement("想读人工智能，计算机", "table_field", "major_name"),
                    _requirement("想留在广东省", "table_field", "school_province"),
                    _requirement(
                        "好就业",
                        "knowledge_base_or_reviewed_field",
                        "employment_outlook",
                    ),
                    _requirement(
                        "学校好一点",
                        "reviewed_ranking_policy",
                        "school_quality",
                    ),
                    _requirement("稳一点", "user_boundary", "risk_preference"),
                ],
                usage={"total_tokens": 13},
            )
        )

        result = EvidenceRequirementGate(classifier).apply(
            text="我的排位15000，想读人工智能，计算机，好就业，学校好一点，稳一点",
            intent=intent,
            schema_context=[{"field_id": "major_name"}],
            query_options={"query_types": ["semantic_recommendation"]},
        )

        self.assertEqual(len(classifier.calls), 1)
        self.assertEqual(
            [preference.semantic for preference in result.filtered_intent.preferences],
            ["major_name", "school_province"],
        )
        self.assertEqual(
            [item["source_text"] for item in result.excluded_preferences],
            ["好就业", "学校好一点", "稳一点"],
        )
        self.assertEqual(
            [item["requirement_type"] for item in result.excluded_preferences],
            [
                "knowledge_base_or_reviewed_field",
                "reviewed_ranking_policy",
                "user_boundary",
            ],
        )
        self.assertEqual(
            result.planner["excluded_preferences"][0]["executable"],
            False,
        )
        self.assertEqual(result.planner["token_usage"]["total_tokens"], 13)

    def test_unmatched_requirement_does_not_delete_preference(self) -> None:
        intent = _intent([_pref("想读人工智能，计算机", "major_name")])
        classifier = _FakeClassifier(
            EvidenceRequirementResult(
                requirements=[
                    _requirement(
                        "好就业",
                        "knowledge_base_or_reviewed_field",
                        "employment_outlook",
                    )
                ]
            )
        )

        result = EvidenceRequirementGate(classifier).apply(
            text="想读人工智能，计算机，好就业",
            intent=intent,
            schema_context=[],
            query_options={},
        )

        self.assertEqual(
            [preference.semantic for preference in result.filtered_intent.preferences],
            ["major_name"],
        )
        self.assertEqual(result.excluded_preferences, [])
        self.assertEqual(
            result.planner["requirements"][0]["requirement_type"],
            "knowledge_base_or_reviewed_field",
        )

    def test_rejected_requirements_are_preserved_in_planner_trace(self) -> None:
        classifier = _FakeClassifier(
            EvidenceRequirementResult(
                requirements=[],
                rejected_requirements=[
                    {
                        "requirement": {"source_text": "按 SQL 排序"},
                        "reason": "raw_sql_forbidden",
                    }
                ],
            )
        )

        result = EvidenceRequirementGate(classifier).apply(
            text="按 SQL 排序",
            intent=_intent([]),
            schema_context=[],
            query_options={},
        )

        self.assertEqual(result.planner["status"], "classified")
        self.assertEqual(
            result.planner["rejected_requirements"][0]["reason"],
            "raw_sql_forbidden",
        )


def _intent(preferences: list[SemanticPreference]) -> SemanticIntent:
    return SemanticIntent(
        query_type="semantic_recommendation",
        user_context=SemanticUserContext(user_rank=15000),
        preferences=preferences,
        requested_output=["recommendation_sections"],
    )


def _pref(source_text: str, semantic: str) -> SemanticPreference:
    return SemanticPreference(
        source_text=source_text,
        semantic=semantic,
        op="contains_any",
        value=[source_text],
    )


def _requirement(
    source_text: str,
    requirement_type: str,
    candidate_semantic: str,
) -> EvidenceRequirement:
    return EvidenceRequirement.model_validate(
        {
            "source_text": source_text,
            "requirement_type": requirement_type,
            "candidate_semantic": candidate_semantic,
            "rationale": f"{source_text} 需要 {requirement_type} 证据。",
        }
    )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/python -m unittest tests.test_evidence_requirement_gate
```

Expected before implementation: FAIL with `ModuleNotFoundError` for `src.semantic.evidence_requirement_gate`.

- [ ] **Step 3: Implement the gate**

Create `src/semantic/evidence_requirement_gate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.semantic.evidence_requirements import (
    DeepSeekEvidenceRequirementClassifier,
    EvidenceRequirement,
    EvidenceRequirementResult,
)
from src.semantic.intent_models import SemanticIntent, SemanticPreference


NON_EXECUTABLE_REQUIREMENT_TYPES = {
    "knowledge_base_or_reviewed_field",
    "reviewed_ranking_policy",
    "user_boundary",
    "unsupported",
}


class EvidenceRequirementClassifierProtocol(Protocol):
    def classify(
        self,
        *,
        text: str,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementResult:
        """返回 evidence requirement 分类结果。"""


@dataclass(frozen=True)
class EvidenceRequirementGateResult:
    filtered_intent: SemanticIntent
    requirements: list[dict[str, Any]] = field(default_factory=list)
    excluded_preferences: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)
    rejected_requirements: list[dict[str, Any]] = field(default_factory=list)
    planner: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)


class EvidenceRequirementGate:
    """把 evidence requirement 分类结果转成可执行 preference 子集。"""

    def __init__(
        self,
        classifier: EvidenceRequirementClassifierProtocol | None = None,
    ) -> None:
        self.classifier = classifier or DeepSeekEvidenceRequirementClassifier()

    def apply(
        self,
        *,
        text: str,
        intent: SemanticIntent,
        schema_context: list[dict[str, Any]],
        query_options: dict[str, Any],
    ) -> EvidenceRequirementGateResult:
        classification = self.classifier.classify(
            text=text,
            schema_context=schema_context,
            query_options=query_options,
        )
        return apply_evidence_requirement_result(intent, classification)


def apply_evidence_requirement_result(
    intent: SemanticIntent,
    classification: EvidenceRequirementResult,
) -> EvidenceRequirementGateResult:
    requirements = [
        requirement.model_dump()
        for requirement in classification.requirements
    ]
    excluded_by_index: dict[int, dict[str, Any]] = {}
    unanswerable: list[dict[str, Any]] = []

    for requirement in classification.requirements:
        if requirement.requirement_type not in NON_EXECUTABLE_REQUIREMENT_TYPES:
            continue
        index = _matching_preference_index(requirement, intent.preferences)
        if index is None:
            continue
        preference = intent.preferences[index]
        excluded = _excluded_preference(preference, requirement)
        excluded_by_index[index] = excluded
        unanswerable.append(_unanswerable_intent(excluded))

    filtered_preferences = [
        preference
        for index, preference in enumerate(intent.preferences)
        if index not in excluded_by_index
    ]
    excluded_preferences = list(excluded_by_index.values())
    usage = dict(classification.usage or {})
    planner = {
        "status": "classified",
        "provider": "deepseek",
        "called": True,
        "fallback_used": False,
        "token_usage": usage,
        "requirements": requirements,
        "excluded_preferences": excluded_preferences,
        "rejected_requirements": list(classification.rejected_requirements),
    }
    return EvidenceRequirementGateResult(
        filtered_intent=intent.model_copy(
            update={"preferences": filtered_preferences}
        ),
        requirements=requirements,
        excluded_preferences=excluded_preferences,
        unanswerable_intents=unanswerable,
        rejected_requirements=list(classification.rejected_requirements),
        planner=planner,
        usage=usage,
    )


def _matching_preference_index(
    requirement: EvidenceRequirement,
    preferences: list[SemanticPreference],
) -> int | None:
    source = _normalized_text(requirement.source_text)
    for index, preference in enumerate(preferences):
        if _normalized_text(preference.source_text) == source:
            return index
    for index, preference in enumerate(preferences):
        preference_text = _normalized_text(preference.source_text)
        if source and preference_text and (
            source in preference_text or preference_text in source
        ):
            return index
    return None


def _excluded_preference(
    preference: SemanticPreference,
    requirement: EvidenceRequirement,
) -> dict[str, Any]:
    field_id = requirement.candidate_semantic or preference.semantic
    return {
        "source_text": preference.source_text,
        "field_id": field_id,
        "semantic": preference.semantic,
        "candidate_semantic": requirement.candidate_semantic,
        "requirement_type": requirement.requirement_type,
        "match_type": "evidence_requirement_gate",
        "executable": False,
        "reason": _reason(requirement),
    }


def _unanswerable_intent(excluded: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_id": excluded.get("field_id"),
        "intent": excluded.get("semantic"),
        "source_text": excluded.get("source_text"),
        "answerable": False,
        "reason": excluded.get("reason"),
        "requirement_type": excluded.get("requirement_type"),
    }


def _reason(requirement: EvidenceRequirement) -> str:
    if requirement.requirement_type == "knowledge_base_or_reviewed_field":
        return requirement.rationale or "需要 reviewed KB 或已审核结构化字段，当前未执行。"
    if requirement.requirement_type == "reviewed_ranking_policy":
        return requirement.rationale or "需要 reviewed ranking policy，当前未执行。"
    if requirement.requirement_type == "user_boundary":
        return requirement.rationale or "需要用户确认边界，当前未执行。"
    return requirement.rationale or "当前偏好不支持执行。"


def _normalized_text(value: str | None) -> str:
    return "".join(str(value or "").split())


__all__ = [
    "EvidenceRequirementGate",
    "EvidenceRequirementGateResult",
    "apply_evidence_requirement_result",
]
```

Modify `src/semantic/__init__.py` to export the gate:

```python
    "EvidenceRequirementGate": (
        "src.semantic.evidence_requirement_gate",
        "EvidenceRequirementGate",
    ),
    "EvidenceRequirementGateResult": (
        "src.semantic.evidence_requirement_gate",
        "EvidenceRequirementGateResult",
    ),
```

Also add both names to `__all__`.

- [ ] **Step 4: Run the gate tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_evidence_requirement_gate
```

Expected after implementation: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/evidence_requirement_gate.py src/semantic/__init__.py tests/test_evidence_requirement_gate.py
git commit -m "feat: gate semantic preferences by evidence need"
```

## Task 3: Recommendation Planner Carries Gate Evidence

**Files:**
- Modify: `src/semantic/admissions_recommendation.py`
- Test: `tests/test_semantic_admissions_recommendation.py`

- [ ] **Step 1: Write the failing planner test**

In `tests/test_semantic_admissions_recommendation.py`, add this test method to `SemanticAdmissionsRecommendationPlannerTest`:

```python
    def test_preclassified_preferences_are_preserved_as_not_executed(self) -> None:
        pre_not_executed = [
            {
                "source_text": "好就业",
                "field_id": "employment_outlook",
                "semantic": "employment_outlook",
                "requirement_type": "knowledge_base_or_reviewed_field",
                "match_type": "evidence_requirement_gate",
                "executable": False,
                "reason": "需要 reviewed KB 或就业结果字段。",
            }
        ]
        pre_unanswerable = [
            {
                "field_id": "employment_outlook",
                "intent": "employment_outlook",
                "source_text": "好就业",
                "answerable": False,
                "reason": "需要 reviewed KB 或就业结果字段。",
                "requirement_type": "knowledge_base_or_reviewed_field",
            }
        ]

        result = self._run(
            _recommendation_intent(),
            pre_not_executed_preferences=pre_not_executed,
            pre_unanswerable_intents=pre_unanswerable,
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.not_executed_preferences[0]["source_text"],
            "好就业",
        )
        self.assertEqual(
            result.unanswerable_intents[0]["requirement_type"],
            "knowledge_base_or_reviewed_field",
        )
        self.assertEqual(
            result.execution_summary["not_executed_preferences"][0]["match_type"],
            "evidence_requirement_gate",
        )
        self.assertIn("好就业", result.warnings[0]["source_text"])
```

Change the local `_run()` helper signature:

```python
        pre_not_executed_preferences=None,
        pre_unanswerable_intents=None,
```

Pass them into `SemanticAdmissionsRecommendationPlanner(...)`:

```python
                pre_not_executed_preferences=pre_not_executed_preferences,
                pre_unanswerable_intents=pre_unanswerable_intents,
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_recommendation.SemanticAdmissionsRecommendationPlannerTest.test_preclassified_preferences_are_preserved_as_not_executed
```

Expected before implementation: FAIL with `TypeError` because `SemanticAdmissionsRecommendationPlanner.__init__()` does not accept `pre_not_executed_preferences`.

- [ ] **Step 3: Implement planner evidence merging**

In `src/semantic/admissions_recommendation.py`, update the constructor:

```python
        pre_not_executed_preferences: list[dict[str, Any]] | None = None,
        pre_unanswerable_intents: list[dict[str, Any]] | None = None,
```

Set instance fields:

```python
        self.pre_not_executed_preferences = list(pre_not_executed_preferences or [])
        self.pre_unanswerable_intents = list(pre_unanswerable_intents or [])
```

At the start of `run()`, after the query type check, add:

```python
        pre_not_executed = list(self.pre_not_executed_preferences)
        pre_unanswerable = list(self.pre_unanswerable_intents)
```

Update combined evidence in every return path:

```python
combined_not_executed = [
    *pre_not_executed,
    *grounded.not_executed_preferences,
]
combined_unanswerable = [
    *pre_unanswerable,
    *grounded.unanswerable_intents,
]
```

Use `combined_not_executed` for:

```python
not_executed_preferences=combined_not_executed
"not_executed_preferences": combined_not_executed
warnings=_context_warnings(intent, combined_not_executed)
```

Use `combined_unanswerable` before verification and missing context:

```python
unanswerable_intents=[
    *combined_unanswerable,
    *_missing_context_intents(registry),
],
```

For `_rank_confirmation_result()` and `_blocked_missing_fields()`, extend the function signatures with `pre_not_executed_preferences` and `pre_unanswerable_intents`, then include those lists in the returned result. Keep existing rank warning first in the missing-rank case by appending pre-unanswerable after the `user_rank` item.

- [ ] **Step 4: Run planner tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_recommendation
```

Expected after implementation: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/admissions_recommendation.py tests/test_semantic_admissions_recommendation.py
git commit -m "feat: carry evidence gate exclusions in recommendations"
```

## Task 4: Workbench Gate Orchestration

**Files:**
- Modify: `src/api/workbench.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: Write the failing runtime test**

In `tests/test_uploaded_dataset_flow.py`, add this test to `UploadedDatasetFlowTest`:

```python
    def test_llm_semantic_recommendation_gate_filters_external_preferences(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，想留在广东省，好就业，学校好一点，请给出推荐"
        intent = _semantic_recommendation_intent()
        intent["preferences"] = [
            *intent["preferences"][:2],
            {
                "source_text": "好就业",
                "semantic": "employment_outlook",
                "op": "equals",
                "value": "好",
                "confidence": 0.9,
                "reason": "需要就业结果。",
            },
            {
                "source_text": "学校好一点",
                "semantic": "school_quality",
                "op": "rank_by",
                "value": "better",
                "confidence": 0.9,
                "reason": "需要学校质量排序政策。",
            },
        ]
        fake_client = FakeSemanticIntentClient(
            [
                intent,
                {
                    "requirements": [
                        {
                            "source_text": "想读人工智能，计算机",
                            "requirement_type": "table_field",
                            "candidate_semantic": "major_name",
                            "rationale": "需要专业字段。",
                        },
                        {
                            "source_text": "想留在广东省",
                            "requirement_type": "table_field",
                            "candidate_semantic": "school_province",
                            "rationale": "需要省份字段。",
                        },
                        {
                            "source_text": "好就业",
                            "requirement_type": "knowledge_base_or_reviewed_field",
                            "candidate_semantic": "employment_outlook",
                            "rationale": "需要 reviewed KB 或就业结果字段。",
                        },
                        {
                            "source_text": "学校好一点",
                            "requirement_type": "reviewed_ranking_policy",
                            "candidate_semantic": "school_quality",
                            "rationale": "需要 reviewed ranking policy。",
                        },
                    ]
                },
                {"criteria": []},
            ],
            usage=[
                {"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
                {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
                {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            ],
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench.deepseek_slot_adapter_enabled",
                return_value=True,
            ):
                with patch(
                    "src.api.workbench._interactive_deepseek_client",
                    return_value=fake_client,
                ):
                    response = service.query(
                        dataset_id,
                        user_input=query,
                        soft_preferences={"prompt": query},
                    )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(fake_client.calls), 3)
        gate = response["evidence_pack"]["planner"]["evidence_requirements"]
        self.assertEqual(gate["status"], "classified")
        self.assertEqual(
            [item["source_text"] for item in gate["excluded_preferences"]],
            ["好就业", "学校好一点"],
        )
        verified_plan = json.dumps(
            response["evidence_pack"]["verified_query_plan"],
            ensure_ascii=False,
        )
        self.assertIn("major_name", verified_plan)
        self.assertIn("school_province", verified_plan)
        self.assertNotIn("employment_outlook", verified_plan)
        self.assertNotIn("school_quality", verified_plan)
        self.assertEqual(
            [item["source_text"] for item in response["unexecuted_preferences"][:2]],
            ["好就业", "学校好一点"],
        )
        self.assertEqual(response["token_usage"]["extractor"]["total_tokens"], 49)
        self.assertIn("未执行偏好", response["answer"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_llm_semantic_recommendation_gate_filters_external_preferences
```

Expected before implementation: FAIL because `evidence_pack.planner.evidence_requirements` is missing and the fake client call count is not 3.

- [ ] **Step 3: Implement Workbench gate helpers**

In `src/api/workbench.py`, import:

```python
from src.semantic.evidence_requirement_gate import EvidenceRequirementGate
from src.semantic.evidence_requirements import DeepSeekEvidenceRequirementClassifier
```

Add a dataclass near `RankingPlanAttempt`:

```python
@dataclass(frozen=True)
class EvidenceRequirementGateAttempt:
    intent: SemanticIntent
    planner: dict[str, Any] | None = None
    usage: dict[str, int] | None = None
    not_executed_preferences: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)
```

Add helpers near `_semantic_ranking_plan_attempt()`:

```python
def _semantic_evidence_requirement_gate_attempt(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    intent: SemanticIntent,
    planner: dict[str, Any],
) -> EvidenceRequirementGateAttempt:
    if not _should_run_evidence_requirement_gate(config, intent, planner):
        return EvidenceRequirementGateAttempt(intent=intent)
    schema_context, query_options = _semantic_llm_context(domain_config)
    gate = EvidenceRequirementGate(
        DeepSeekEvidenceRequirementClassifier(
            _interactive_deepseek_client(config.model)
        )
    ).apply(
        text=_compose_user_request(config),
        intent=intent,
        schema_context=schema_context,
        query_options=query_options,
    )
    return EvidenceRequirementGateAttempt(
        intent=gate.filtered_intent,
        planner=gate.planner,
        usage=gate.usage,
        not_executed_preferences=gate.excluded_preferences,
        unanswerable_intents=gate.unanswerable_intents,
    )


def _should_run_evidence_requirement_gate(
    config: WorkbenchConfig,
    intent: SemanticIntent,
    planner: dict[str, Any],
) -> bool:
    return (
        bool(config.dataset_id)
        and intent.query_type == "semantic_recommendation"
        and planner.get("mode") == "llm_semantic"
        and not planner.get("fallback_used")
    )


def _with_evidence_requirement_trace(
    planner: dict[str, Any],
    gate_attempt: EvidenceRequirementGateAttempt,
) -> dict[str, Any]:
    if gate_attempt.planner is None:
        return planner
    return {
        **planner,
        "evidence_requirements": gate_attempt.planner,
    }
```

Extend `_with_planner_fallback()` with optional extra metadata:

```python
def _with_planner_fallback(
    attempt: SemanticPlannerAttempt,
    *,
    reason: str,
    **extra: Any,
) -> SemanticPlannerAttempt:
    return SemanticPlannerAttempt(
        intent=None,
        usage=attempt.usage,
        planner={
            **attempt.planner,
            **extra,
            "fallback_used": True,
            "fallback_reason": reason,
        },
    )
```

Extend `_run_semantic_intent_query()` signature:

```python
    pre_not_executed_preferences: list[dict[str, Any]] | None = None,
    pre_unanswerable_intents: list[dict[str, Any]] | None = None,
```

Pass those fields to `SemanticAdmissionsRecommendationPlanner(...)`:

```python
            pre_not_executed_preferences=pre_not_executed_preferences,
            pre_unanswerable_intents=pre_unanswerable_intents,
```

- [ ] **Step 4: Wire gate into `_run_semantic_capability_query()`**

In both places where Workbench currently has a valid semantic recommendation intent before `_semantic_ranking_plan_attempt()`, insert:

```python
            try:
                gate_attempt = _semantic_evidence_requirement_gate_attempt(
                    config,
                    domain_config,
                    planner_attempt.intent,
                    planner_attempt.planner,
                )
            except Exception as exc:  # noqa: BLE001 - gate 失败不能执行 LLM semantic SQL。
                planner_attempt = _with_planner_fallback(
                    planner_attempt,
                    reason="evidence_requirement_classification_failed",
                    evidence_requirements={
                        "status": "classification_failed",
                        "provider": "deepseek",
                        "called": True,
                        "fallback_used": True,
                        "fallback_reason": "evidence_requirement_classification_failed",
                        "error_type": type(exc).__name__,
                    },
                )
                if config.planner_mode == "llm_semantic":
                    return _semantic_planner_blocked_run(config, planner_attempt)
            else:
                gated_planner = _with_evidence_requirement_trace(
                    planner_attempt.planner,
                    gate_attempt,
                )
                ranking_attempt = _semantic_ranking_plan_attempt(
                    config,
                    domain_config,
                    gate_attempt.intent,
                    gated_planner,
                )
                semantic_result = _run_semantic_intent_query(
                    gate_attempt.intent,
                    config=config,
                    domain_config=domain_config,
                    ranking_plan=ranking_attempt.plan,
                    pre_not_executed_preferences=gate_attempt.not_executed_preferences,
                    pre_unanswerable_intents=gate_attempt.unanswerable_intents,
                )
```

Use `gated_planner` in `SemanticCapabilityRun.planner`:

```python
                    planner=_with_ranking_plan_trace(
                        gated_planner,
                        ranking_attempt,
                    ),
```

Use combined usage:

```python
                    extractor_usage=_combined_usage(
                        planner_attempt.usage,
                        gate_attempt.usage,
                        ranking_attempt.usage,
                    ),
```

Keep existing fallback behavior for unsupported semantic intents.

- [ ] **Step 5: Update existing LLM semantic recommendation tests**

In `tests/test_uploaded_dataset_flow.py`, any semantic recommendation test using `FakeSemanticIntentClient` with LLM planner now needs a classifier payload between intent and ranking plan payload.

For `test_uploaded_recommendation_query_uses_llm_semantic_planner_first`, use:

```python
fake_client = FakeSemanticIntentClient(
    [
        _semantic_recommendation_intent(),
        _evidence_requirements_for_basic_recommendation(),
        {"criteria": []},
    ]
)
```

For `test_llm_semantic_recommendation_generates_verified_ranking_plan`, change payload order to:

```python
fake_client = FakeSemanticIntentClient(
    [
        _semantic_recommendation_intent(),
        _evidence_requirements_for_basic_recommendation(),
        {
            "criteria": [
                {
                    "criterion_id": "rank_distance_to_user",
                    "source_text": "我的排位是15000",
                    "required_field": "major_min_rank",
                    "operation": "numeric_distance_to_user_value",
                    "value": 15000,
                    "priority": 1,
                    "direction": "desc",
                    "rationale": "专业最低位次越接近用户排位，候选越贴近。",
                }
            ],
            "rationale_summary": "按已审核专业最低位次与用户排位距离排序。",
        },
    ],
    usage=[
        {"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
        {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        {"prompt_tokens": 17, "completion_tokens": 11, "total_tokens": 28},
    ],
)
```

Change assertions:

```python
self.assertEqual(len(fake_client.calls), 3)
self.assertEqual(response["token_usage"]["extractor"]["total_tokens"], 70)
self.assertEqual(
    response["evidence_pack"]["planner"]["evidence_requirements"]["status"],
    "classified",
)
```

Add helper near `_semantic_recommendation_intent()`:

```python
def _evidence_requirements_for_basic_recommendation() -> dict[str, object]:
    return {
        "requirements": [
            {
                "source_text": "想读人工智能，计算机",
                "requirement_type": "table_field",
                "candidate_semantic": "major_name",
                "rationale": "需要专业字段。",
            },
            {
                "source_text": "想留在广东省",
                "requirement_type": "table_field",
                "candidate_semantic": "school_province",
                "rationale": "需要省份字段。",
            },
            {
                "source_text": "不想去国外",
                "requirement_type": "knowledge_base_or_reviewed_field",
                "candidate_semantic": "school_country_or_region",
                "rationale": "当前没有已审核境外/国家地区字段。",
            },
        ]
    }
```

- [ ] **Step 6: Run focused uploaded flow tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_llm_semantic_recommendation_gate_filters_external_preferences \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_uploaded_recommendation_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_llm_semantic_recommendation_generates_verified_ranking_plan
```

Expected after implementation: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: run evidence gate before semantic recommendations"
```

## Task 5: Scope Exemptions And Failure Semantics

**Files:**
- Modify: `src/api/workbench.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: Add failing and regression tests**

Add a fake client near `FailingSemanticIntentClient`:

```python
class FailingAfterFirstSemanticClient:
    def __init__(self, first_payload: dict[str, object], exc: Exception) -> None:
        self.first_payload = first_payload
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def chat_json(
        self,
        messages: list[dict[str, object]],
        temperature: float = 0.0,
        **kwargs: object,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                **kwargs,
            }
        )
        if len(self.calls) == 1:
            return {
                **self.first_payload,
                "usage": {
                    "prompt_tokens": 21,
                    "completion_tokens": 9,
                    "total_tokens": 30,
                },
            }
        raise self.exc
```

Add tests:

```python
    def test_evidence_gate_failure_blocks_forced_llm_semantic(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，好就业，请给出推荐"
        fake_client = FailingAfterFirstSemanticClient(
            _semantic_recommendation_intent(),
            RuntimeError("classifier unavailable"),
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench.deepseek_slot_adapter_enabled",
                return_value=True,
            ):
                with patch(
                    "src.api.workbench._interactive_deepseek_client",
                    return_value=fake_client,
                ):
                    response = service.query(
                        dataset_id,
                        user_input=query,
                        planner_mode="llm_semantic",
                        soft_preferences={"prompt": query},
                    )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "blocked")
        planner = response["evidence_pack"]["planner"]
        self.assertEqual(
            planner["fallback_reason"],
            "evidence_requirement_classification_failed",
        )
        self.assertEqual(
            planner["evidence_requirements"]["status"],
            "classification_failed",
        )
        self.assertEqual(response["debug_trace"]["execution"]["sql"], "")

    def test_evidence_gate_failure_falls_back_in_auto_mode(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，好就业，请给出推荐"
        fake_client = FailingAfterFirstSemanticClient(
            _semantic_recommendation_intent(),
            RuntimeError("classifier unavailable"),
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench.deepseek_slot_adapter_enabled",
                return_value=True,
            ):
                with patch(
                    "src.api.workbench._interactive_deepseek_client",
                    return_value=fake_client,
                ):
                    response = service.query(
                        dataset_id,
                        user_input=query,
                        soft_preferences={"prompt": query},
                    )

        assert_workbench_contract(self, response)
        planner = response["evidence_pack"]["planner"]
        self.assertEqual(planner["mode"], "legacy")
        self.assertTrue(planner["fallback_used"])
        self.assertEqual(
            planner["prior_planner"]["fallback_reason"],
            "evidence_requirement_classification_failed",
        )
        self.assertEqual(
            planner["prior_planner"]["evidence_requirements"]["status"],
            "classification_failed",
        )

    def test_admissions_major_rank_does_not_call_evidence_gate(self) -> None:
        query = "广东物化生，10000名，列出冲稳保"
        fake_client = FakeSemanticIntentClient(_major_rank_semantic_intent())
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench.deepseek_slot_adapter_enabled",
                return_value=True,
            ):
                with patch(
                    "src.api.workbench._interactive_deepseek_client",
                    return_value=fake_client,
                ):
                    response = service.query(
                        dataset_id,
                        user_input=query,
                        soft_preferences={"prompt": query},
                    )

        assert_workbench_contract(self, response)
        self.assertEqual(response["query_type"], "admissions_major_rank")
        self.assertEqual(len(fake_client.calls), 1)
        self.assertNotIn(
            "evidence_requirements",
            response["evidence_pack"]["planner"],
        )

    def test_supplied_semantic_intent_does_not_call_evidence_gate(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，请给出推荐"
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

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertNotIn(
            "evidence_requirements",
            response["evidence_pack"]["planner"],
        )
```

- [ ] **Step 2: Run tests to verify new failure tests fail before implementation**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_evidence_gate_failure_blocks_forced_llm_semantic \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_evidence_gate_failure_falls_back_in_auto_mode
```

Expected before Task 5 implementation: FAIL because classifier failure is treated like ranking generation failure or is not represented in planner metadata.

- [ ] **Step 3: Implement failure semantics**

In `_run_semantic_capability_query()`, when `_semantic_evidence_requirement_gate_attempt()` raises:

- Build planner metadata with `evidence_requirements.status="classification_failed"`.
- Use `_with_planner_fallback(..., reason="evidence_requirement_classification_failed", evidence_requirements=...)`.
- If `config.planner_mode == "llm_semantic"`, return `_semantic_planner_blocked_run(config, planner_attempt)`.
- If `config.planner_mode == "auto"`, continue to existing legacy fallback flow.

Use this metadata shape:

```python
{
    "status": "classification_failed",
    "provider": "deepseek",
    "called": True,
    "fallback_used": True,
    "fallback_reason": "evidence_requirement_classification_failed",
    "error_type": type(exc).__name__,
}
```

Do not include exception message text in public metadata.

- [ ] **Step 4: Run scope and failure tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_evidence_gate_failure_blocks_forced_llm_semantic \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_evidence_gate_failure_falls_back_in_auto_mode \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_admissions_major_rank_does_not_call_evidence_gate \
  tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_supplied_semantic_intent_does_not_call_evidence_gate
```

Expected after implementation: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py
git commit -m "fix: constrain evidence gate scope and failures"
```

## Task 6: Forbidden Payload Redaction Through Gate

**Files:**
- Modify: `tests/test_uploaded_dataset_flow.py`
- Modify: `src/api/workbench.py` only if the test exposes leakage

- [ ] **Step 1: Write the failing redaction test**

Add this test:

```python
    def test_evidence_gate_rejected_sql_payload_is_redacted(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，请给出推荐"
        fake_client = FakeSemanticIntentClient(
            [
                _semantic_recommendation_intent(),
                {
                    "requirements": [
                        {
                            "source_text": "按 SQL 排序",
                            "requirement_type": "table_field",
                            "candidate_semantic": "major_name",
                            "rationale": "x",
                            "raw_sql": "SELECT * FROM admissions",
                        }
                    ]
                },
                {"criteria": []},
            ]
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench.deepseek_slot_adapter_enabled",
                return_value=True,
            ):
                with patch(
                    "src.api.workbench._interactive_deepseek_client",
                    return_value=fake_client,
                ):
                    response = service.query(
                        dataset_id,
                        user_input=query,
                        soft_preferences={"prompt": query},
                    )

        assert_workbench_contract(self, response)
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("SELECT * FROM admissions", serialized)
        rejected = response["evidence_pack"]["planner"]["evidence_requirements"][
            "rejected_requirements"
        ]
        self.assertEqual(rejected[0]["reason"], "raw_sql_forbidden")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_evidence_gate_rejected_sql_payload_is_redacted
```

Expected before Task 4 implementation: FAIL because gate metadata is missing. If run after Task 4, expected behavior is PASS; if it fails due leakage, continue Step 3.

- [ ] **Step 3: Fix leakage if present**

If `SELECT * FROM admissions` appears in the response, sanitize gate planner metadata before attaching it to `EvidencePack` by relying on `DeepSeekEvidenceRequirementClassifier.rejected_requirements`. Do not copy raw classifier payloads anywhere in Workbench.

- [ ] **Step 4: Run the redaction test**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_evidence_gate_rejected_sql_payload_is_redacted
```

Expected after implementation: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py
git commit -m "test: verify evidence gate SQL redaction"
```

## Task 7: Documentation Sync

**Files:**
- Modify: `README.md`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`

- [ ] **Step 1: Update `README.md`**

Replace the uploaded admissions recommendation paragraph around the existing `RankingPlan` description with Chinese text containing these exact claims:

```markdown
uploaded admissions 推荐现在走 reviewed semantic 链路：DeepSeek 先提出候选 `SemanticIntent`，系统随后运行 `EvidenceRequirementClassifier`，把每个 LLM 抽取出的 preference 先分成 `table_field`、`knowledge_base_or_reviewed_field`、`reviewed_ranking_policy`、`user_boundary` 或 `unsupported`。只有 `table_field` preference 会继续进入 `PreferenceGrounder`、`SemanticQueryVerifier` 和 verified `QueryAST`；需要 reviewed KB、reviewed ranking policy、用户边界或 unsupported 的偏好会进入 `not_executed_preferences` / `unanswerable_intents`，不会进入 SQL filter、候选 `RankingPlan` prompt 或答案结论。
```

- [ ] **Step 2: Update `docs/api_contract.md`**

In the semantic recommendation section, add:

```markdown
`evidence_pack.planner.evidence_requirements` 记录 LLM semantic recommendation 的 evidence gate：`status`、`provider`、`called`、`fallback_used`、`token_usage`、`requirements`、`excluded_preferences` 和 `rejected_requirements`。该节点只说明证据需求分流，不代表字段可执行；最终可执行性仍由 `PreferenceGrounder`、`SemanticQueryVerifier` 和 `RankingVerifier` 决定。
```

- [ ] **Step 3: Update `docs/methodology_report.md`**

In the uploaded semantic flow section, update the architecture list to:

```text
DeepSeekSemanticIntentExtractor
-> EvidenceRequirementClassifier
-> PreferenceGrounder
-> SemanticQueryVerifier
-> SemanticSQLBuilder
-> DuckDBExecutor
-> RankingPlan
-> RankingVerifier
-> GenericRankingEngine
-> EvidencePack
```

Add one Chinese paragraph explaining that first-version gate only covers uploaded admissions `semantic_recommendation` on LLM semantic planner paths, not `admissions_major_rank`, legacy planner, supplied debug intent, template answer generation, raw SQL planner, reviewed KB ingestion, or ranking policy registry.

- [ ] **Step 4: Search for stale docs**

Run:

```bash
rg -n "DeepSeekSemanticIntentExtractor|RankingPlan|semantic_recommendation|EvidenceRequirementClassifier|not_executed_preferences" README.md docs -S
```

Expected: every remaining description is compatible with the gate-first behavior or explicitly describes older legacy paths.

- [ ] **Step 5: Run doc check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/api_contract.md docs/methodology_report.md
git commit -m "docs: describe evidence requirement gate"
```

## Task 8: Full Verification

**Files:**
- No new files.
- Verify all touched source, tests, and docs.

- [ ] **Step 1: Compile touched Python files**

Run:

```bash
.venv/bin/python -m py_compile \
  src/semantic/evidence_requirements.py \
  src/semantic/evidence_requirement_gate.py \
  src/semantic/admissions_recommendation.py \
  src/api/workbench.py
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run focused tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_evidence_requirements \
  tests.test_evidence_requirement_gate \
  tests.test_semantic_admissions_recommendation \
  tests.test_uploaded_dataset_flow
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: PASS.

- [ ] **Step 4: Run final diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` has no output. `git status --short` only shows files intentionally modified by the final verification task if any docs or tests were corrected after Task 7.

- [ ] **Step 5: Final commit if verification required changes**

If Step 4 shows intentional uncommitted fixes, commit them:

```bash
git add \
  src/semantic/evidence_requirements.py \
  src/semantic/evidence_requirement_gate.py \
  src/semantic/__init__.py \
  src/semantic/admissions_recommendation.py \
  src/api/workbench.py \
  tests/test_evidence_requirements.py \
  tests/test_evidence_requirement_gate.py \
  tests/test_semantic_admissions_recommendation.py \
  tests/test_uploaded_dataset_flow.py \
  README.md \
  docs/api_contract.md \
  docs/methodology_report.md
git commit -m "fix: stabilize evidence requirement gate"
```

If Step 4 shows a clean tree, do not create an empty commit.

## Self-Review Notes

- Spec coverage: Tasks 1-6 cover classifier client compatibility, gate filtering, planner evidence propagation, Workbench orchestration, scope exclusions, failure fallback, and SQL payload redaction. Task 7 covers README/API/methodology sync. Task 8 covers focused and full verification.
- Scope control: This plan does not implement reviewed KB ingestion, generic QueryAST planning, raw SQL planning, or ranking policy registry.
- Type consistency: The plan consistently uses `EvidenceRequirementGateResult.filtered_intent`, `excluded_preferences`, `unanswerable_intents`, `planner`, and `usage`; Workbench wraps gate metadata under `planner.evidence_requirements`.
