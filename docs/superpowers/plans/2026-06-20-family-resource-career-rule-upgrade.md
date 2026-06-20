# 家庭资源与就业偏好规则化升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不偏离“自然语言只能提出结构，只有 schema-grounded verified rules 才能执行”的前提下，把“家里资源”和“好就业”升级为可审查、可解释、不可静默执行的结构化规则框架。

**Architecture:** 先修复当前已确认的 `score-only recommendation` 偏差，确保只给分数时要求用户补充省排位且不执行 SQL。再新增一个 admissions 专用的 deterministic career guidance policy：它只产生 `EvidencePack` 中的非执行指导、信息需求和 no-schema 说明，不进入 `RulePromoter`、`DuckDBExecutor` 或 frontend hard filter。最后让前端展示后端返回的 guidance，不在前端生成推荐逻辑。

**Tech Stack:** Python `unittest`、DuckDB、现有 `DomainConfig` domain pack、`RegexExtractor`、可选 `DeepSeekSlotAdapter` schema guard、`EvidencePack`、`TemplateReportBuilder`、Vue/Vite、`git diff --check`。

---

## 对话结论转成工程边界

截图里的核心要求可以落成三条工程原则：

- “数字怎么处理”：分数、位次窗口、学费上限等数字必须来自用户显式输入、前端固定选项或 domain pack 固定配置；不让 LLM 生成阈值。
- “规则怎么固定”：把“家里有资源/没资源/好就业”写成 reviewed policy rules，先做 deterministic rule matching，再进入证据解释；不做切片式知识库，也不做向量检索。
- “先规则再大模型”：Extractor 和可选 DeepSeek 只能抽槽；career guidance、RuleVerifier、confirmation loop、DuckDB 执行和 EvidencePack 都保持 deterministic。LLM 只能基于 EvidencePack 解释，不能改变结果。

## 范围检查

这是一个跨后端规则、domain pack、EvidencePack、前端展示和文档的单一升级。它不应该拆成互不相干的子项目，因为所有改动都服务同一条安全链路：把就业/家庭资源偏好结构化，但不让它绕过 verifier 执行。

本计划明确不做这些事：

- 不新增就业预测、不生成完整志愿表、不按“好就业”直接排序。
- 不新增向量库或 full-table embedding。
- 不把 `employment_outlook`、家庭资源、行业前景、薪资、体制内机会等 unsupported 字段编译成 SQL。
- 不让前端从用户二次自由文本构造 hard filter。

## 文件结构

- Modify: `src/api/admissions_query_planner.py`
  - 修复只给分数时仍执行 recommendation SQL 的偏差；支持“有位次并明确要求推荐”的 rank-first planned recommendation。
- Modify: `tests/test_admissions_query_types.py`
  - 更新 recommendation 测试为 rank-first；新增 score-only 不执行 SQL 测试。
- Modify: `tests/test_security_review_regressions.py`
  - 移除 score-only expected failure，让该风险变成必须通过的回归测试。
- Modify: `tests/test_uploaded_dataset_flow.py`
  - uploaded admissions recommendation 使用带位次 query，或断言 score-only 返回 `needs_confirmation`。
- Modify: `tests/test_real_dataset_pilot.py`
  - 与 uploaded dataset 行为保持一致。
- Modify: `domains/admissions/value_aliases.json`
  - 增加 family resource、no family resource、career goal、employment preference 的 reviewed aliases。
- Modify: `domains/admissions/attribute_grounding.json`
  - 为新增 slots 配置 context-only 或 missing-schema grounding policy。
- Modify: `src/extractors/regex_extractor.py`
  - 抽取 `employment_preference_raw`、`family_resource_raw`、`career_goal_raw` 和 source spans。
- Modify: `src/extractors/llm_slot_adapter.py`
  - 允许可选 DeepSeek slot adapter 返回新增 slots，但继续禁止 executable output。
- Modify: `src/extractors/deepseek_extractor.py`
  - 更新 JSON 输出结构说明和 normalization，使 LLM 只能抽取这些 slots。
- Create: `domains/admissions/career_decision_policy.json`
  - admissions 专用 deterministic career guidance policy；不是知识库。
- Modify: `domains/admissions/domain.json`
  - 注册 `career_decision_policy` 路径。
- Modify: `src/domains/domain_config.py`
  - 增加 `career_decision_policy_path` 读取入口。
- Create: `src/reporting/career_guidance.py`
  - 从 user request 和 slots 匹配 career policy，返回 reference-only guidance。
- Modify: `src/reporting/evidence_pack.py`
  - 在 EvidencePack 中加入 `decision_guidance`，作为 AnswerGenerator 唯一可用输入的一部分。
- Modify: `src/api/workbench.py`
  - legacy verified pipeline 和 admissions planned query 都把 career guidance 放入 EvidencePack，并把 no-schema guidance 合并到未执行偏好。
- Modify: `src/reporting/template_report_builder.py`
  - 确定性报告展示“就业与家庭资源说明（不参与筛选）”。
- Modify: `src/reporting/deepseek_answer_generator.py`
  - optional LLM answer prompt 包含 `decision_guidance`，且强调它不改变 SQL 或结果。
- Create: `tests/test_career_guidance.py`
  - 验证“好就业/家里资源”只进入 guidance 和 no-schema，不进入 SQL、executed filters 或 candidate confirmation。
- Modify: `tests/test_llm_slot_adapter.py`
  - 验证 LLM slot adapter 接受新增 slots、仍拒绝 hard rules。
- Modify: `tests/test_workbench_api_contract.py`
  - 验证 `evidence_pack.decision_guidance` 存在且不改变 top-level API contract。
- Modify: `docs/api_contract.md`
  - 记录 `EvidencePack.decision_guidance` 结构和 score-only recommendation 行为。
- Modify: `docs/methodology_report.md`
  - 说明 career guidance 是非执行 policy，不是知识库，不是就业预测。
- Modify: `docs/full_project_plan.md`
  - 更新“暂不建设”和“后续研究方向”，避免继续写成完全不处理就业表达。
- Modify: `docs/real_dataset_pilot.md`
  - 更新 recommendation score/rank 规则说明。
- Modify: `frontend/src/components/BeginnerDecisionPanel.vue`
  - 展示后端 `decision_guidance.information_requests`，不生成 hard filter。
- Modify: `frontend/src/components/EvidenceReport.vue`
  - 展示 `natural_language_report` 中已有的 deterministic guidance 文本即可；若后端已有 full text，不重复推理。
- Modify: `frontend/src/mock/demo_run.json`
  - 更新 mock，使前端能看到 `decision_guidance` 示例。

## Task 1: 修复只给分数仍执行 recommendation SQL

**Files:**
- Modify: `tests/test_admissions_query_types.py`
- Modify: `tests/test_security_review_regressions.py`
- Modify: `tests/test_uploaded_dataset_flow.py`
- Modify: `tests/test_real_dataset_pilot.py`
- Modify: `src/api/admissions_query_planner.py`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`

- [ ] **Step 1: 写 rank-first recommendation 测试**

Use `apply_patch` to update `tests/test_admissions_query_types.py`.

Replace the current `RECOMMENDATION_QUERY` constant with these constants:

```python
SCORE_ONLY_RECOMMENDATION_QUERY = (
    "我今年高考分数 630，想读人工智能、计算机，不想去国外，想留在广东省"
)
RANK_RECOMMENDATION_QUERY = (
    "我今年高考分数 630，位次 9000，想读人工智能、计算机，不想去国外，想留在广东省"
)
RANK_ONLY_RECOMMENDATION_QUERY = (
    "我今年位次 9000，想读人工智能、计算机，想留在广东省，请推荐"
)
RECOMMENDATION_QUERY = RANK_RECOMMENDATION_QUERY
```

Add these test methods inside `AdmissionsQueryTypesTest`:

```python
    def test_score_only_recommendation_requires_rank_and_does_not_execute_sql(self) -> None:
        result = _run(SCORE_ONLY_RECOMMENDATION_QUERY)

        assert_workbench_contract(self, result)
        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["result_sections"], {
            "reach": {"label": "冲", "items": []},
            "match": {"label": "稳", "items": []},
            "safety": {"label": "保", "items": []},
        })
        self.assertIn("score_without_rank", _warning_codes(result))
        execution = result["evidence_pack"]["execution_summary"]
        self.assertIsNone(execution["executor"])
        self.assertEqual(execution["sql"], "")
        self.assertEqual(execution["params"], [])
        self.assertNotIn("录取概率", result["answer"])

    def test_rank_only_recommendation_query_is_detected(self) -> None:
        result = _run(RANK_ONLY_RECOMMENDATION_QUERY)

        assert_workbench_contract(self, result)
        self.assertEqual(result["query_type"], "recommendation")
        self.assertEqual(result["status"], "ok")
        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(execution["metric"], "rank_margin")
        self.assertEqual(execution["sort"], [{"field": "rank_margin", "direction": "ASC"}])
        self.assertNotIn("score_without_rank", _warning_codes(result))
```

Update `test_score_based_recommendation_returns_reach_match_safety` to expect rank wording:

```python
        self.assertIn("位次 margin", result["answer"])
        self.assertIn("历史最低分/最低位次", result["answer"])
```

Update `test_score_without_rank_adds_warning` to assert non-execution:

```python
    def test_score_without_rank_adds_warning(self) -> None:
        result = _run(SCORE_ONLY_RECOMMENDATION_QUERY)

        self.assertIn("score_without_rank", _warning_codes(result))
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertIsNone(result["evidence_pack"]["execution_summary"]["metric"])
        self.assertEqual(result["evidence_pack"]["execution_summary"]["sql"], "")
```

- [ ] **Step 2: Turn the security review expected failure into a required regression**

Use `apply_patch` to remove `@unittest.expectedFailure` above `test_score_only_query_is_blocked_from_recommendation_execution` in `tests/test_security_review_regressions.py`.

The final test method must be:

```python
    def test_score_only_query_is_blocked_from_recommendation_execution(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input="广东物理，630分，想读计算机。",
                hard_filters={"source_province": "广东", "subject_type": "物理", "user_score": 630},
                soft_preferences={"prompt": "想读计算机"},
                extractor="regex",
            )
        )

        self.assertIn(result["status"], {"blocked", "needs_confirmation"})
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["debug_trace"]["execution"]["sql"], "")
        serialized = str(result)
        self.assertNotIn("录取概率", serialized)
        self.assertNotIn("仅按分数估计风险", serialized)
```

- [ ] **Step 3: Run focused tests and confirm failure before implementation**

Run:

```bash
.venv/bin/python -m unittest tests.test_admissions_query_types tests.test_security_review_regressions
```

Expected before implementation: failures show score-only recommendation still executes SQL or returns `status="ok"`.

- [ ] **Step 4: Implement score-only non-execution guard**

Use `apply_patch` to modify `src/api/admissions_query_planner.py`.

Replace `_detect_query_type` with:

```python
    def _detect_query_type(self, config: Any, user_request: str) -> str | None:
        forced = _clean_text(config.hard_filters.get("query_type"))
        if forced in {QUERY_TYPE_GROUP_DETAIL, QUERY_TYPE_RECOMMENDATION}:
            return forced
        text = user_request
        if (
            "专业组" in text
            and any(term in text for term in ["组内", "里面", "各个专业"])
            and any(term in text for term in ["录取最高", "最高"])
        ):
            return QUERY_TYPE_GROUP_DETAIL
        if _score_from_inputs(config, text) is not None:
            return QUERY_TYPE_RECOMMENDATION
        if _rank_from_inputs(config, text) is not None and self._has_recommendation_intent(text):
            return QUERY_TYPE_RECOMMENDATION
        return None

    def _has_recommendation_intent(self, text: str) -> bool:
        terms = self.aliases.get("recommendation_terms") or []
        return any(str(term) in text for term in terms)
```

In `_recommendation`, immediately after:

```python
        inputs = self._recommendation_inputs(config, user_request, policy)
```

insert:

```python
        if inputs.score and not inputs.rank:
            return self._score_without_rank_result(inputs)
```

Add this method to `AdmissionsQueryPlanner` before `_resolve_year`:

```python
    def _score_without_rank_result(
        self,
        inputs: _RecommendationInputs,
    ) -> AdmissionsQueryResult:
        warning = next(
            (
                item
                for item in inputs.warnings
                if item.get("code") == "score_without_rank"
            ),
            _warning(
                "score_without_rank",
                "只提供分数没有位次；请补充广东省排位，系统不会仅凭分数执行推荐。",
                severity="error",
            ),
        )
        warning = {**warning, "severity": "error"}
        answer = (
            "请先补充广东省排位/位次。当前只收到分数，系统不会仅凭分数执行推荐 SQL，"
            "也不会把分数 margin 解释成录取概率。"
        )
        return AdmissionsQueryResult(
            query_type=QUERY_TYPE_RECOMMENDATION,
            status="needs_confirmation",
            rows=[],
            result_sections=_empty_recommendation_sections(),
            execution_summary=_empty_execution_summary(
                QUERY_TYPE_RECOMMENDATION,
                warnings=[warning],
            ),
            answer=answer,
            warnings=[warning],
            executed_rules=[],
            candidates_to_confirm=[],
            no_schema_field_preferences=inputs.no_schema_preferences,
            extracted_preferences=_recommendation_extracted_preferences(inputs),
            policy={},
        )
```

In `_recommendation_inputs`, replace the existing `score_without_rank` warning with:

```python
        if score and not rank:
            warnings.append(
                _warning(
                    "score_without_rank",
                    "只提供分数没有位次；请补充广东省排位，系统不会仅凭分数执行推荐。",
                    severity="error",
                )
            )
```

- [ ] **Step 5: Update uploaded and real-dataset tests**

Use `apply_patch` to change uploaded and real-like recommendation prompts from score-only to score+rank when the test expects `status="ok"`.

In `tests/test_uploaded_dataset_flow.py`, set the query used by `test_uploaded_admissions_recommendation` to:

```python
query = "我今年高考分数 630，位次 9000，想读人工智能、计算机，不想去国外，想留在广东省"
```

Then call:

```python
response = service.query(
    dataset_id,
    user_input=query,
    soft_preferences={"prompt": query},
)
```

Replace the old warning assertion with:

```python
self.assertNotIn("score_without_rank", [w["code"] for w in response["warnings"]])
```

In `tests/test_real_dataset_pilot.py`, update the equivalent recommendation query to include `位次 9000` and use the same `assertNotIn("score_without_rank", ...)` assertion for ok recommendation tests.

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_admissions_query_types tests.test_security_review_regressions tests.test_uploaded_dataset_flow tests.test_real_dataset_pilot
```

Expected: all selected tests pass.

- [ ] **Step 7: Update docs for score-only behavior**

Use `apply_patch` to update `docs/api_contract.md`, `docs/methodology_report.md`, and `docs/real_dataset_pilot.md`.

Use this wording where recommendation behavior is described:

```markdown
如果用户只有分数没有位次，`recommendation` 必须返回 `status=needs_confirmation` 和
`score_without_rank` warning，`execution_summary.sql` 为空，`result_count=0`。系统应要求用户补充广东省排位/位次，不能仅凭分数执行 SQL，也不能把分数 margin 解释成录取概率。
```

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add src/api/admissions_query_planner.py tests/test_admissions_query_types.py tests/test_security_review_regressions.py tests/test_uploaded_dataset_flow.py tests/test_real_dataset_pilot.py docs/api_contract.md docs/methodology_report.md docs/real_dataset_pilot.md
git commit -m "fix: require rank for admissions recommendation"
```

Expected: commit succeeds and contains only Task 1 files.

## Task 2: 抽取“家庭资源/就业偏好”但不执行

**Files:**
- Modify: `domains/admissions/value_aliases.json`
- Modify: `domains/admissions/attribute_grounding.json`
- Modify: `src/extractors/regex_extractor.py`
- Modify: `src/extractors/llm_slot_adapter.py`
- Modify: `src/extractors/deepseek_extractor.py`
- Create: `tests/test_career_guidance.py`
- Modify: `tests/test_llm_slot_adapter.py`

- [ ] **Step 1: Add extractor and grounding tests**

Use `apply_patch` to create `tests/test_career_guidance.py` with this initial content:

```python
from __future__ import annotations

import unittest

from src.domains import DomainConfig
from src.extractors.regex_extractor import RegexExtractor
from src.schema.attribute_grounder import AttributeGrounder
from src.schema.schema_registry import SchemaRegistry


ADMISSIONS_DOMAIN = DomainConfig.load("admissions")


class CareerGuidanceExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SchemaRegistry.from_domain(
            ADMISSIONS_DOMAIN,
            [
                "生源地",
                "科类",
                "专业名称",
                "城市",
                "学费",
                "专业组最低位次1",
                "选科要求",
            ],
        )

    def test_regex_extracts_family_resource_and_employment_slots(self) -> None:
        slots = RegexExtractor().extract("家里没有资源，想选一个好就业的专业。")

        self.assertEqual(slots["preferences"]["family_resource_raw"], "家里没有资源")
        self.assertEqual(slots["preferences"]["employment_preference_raw"], "好就业")
        self.assertIsNone(slots["preferences"]["career_goal_raw"])
        self.assertEqual(
            slots["raw_sources"]["preferences.family_resource_raw"],
            "家里没有资源",
        )
        self.assertEqual(
            slots["raw_sources"]["preferences.employment_preference_raw"],
            "好就业",
        )

    def test_family_resource_is_context_and_employment_is_no_schema(self) -> None:
        slots = RegexExtractor().extract("家里在医疗系统有资源，想选好就业专业。")

        grounding = AttributeGrounder(self.registry).ground(slots)
        by_path = {
            item["slot_path"]: item
            for item in grounding["attributes"]
        }

        self.assertEqual(
            by_path["preferences.family_resource_raw"]["status"],
            "context_only",
        )
        self.assertFalse(
            by_path["preferences.family_resource_raw"]["can_become_executable_rule"]
        )
        self.assertEqual(
            by_path["preferences.employment_preference_raw"]["status"],
            "missing_schema",
        )
        self.assertFalse(
            by_path["preferences.employment_preference_raw"]["can_become_executable_rule"]
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify missing slots**

Run:

```bash
.venv/bin/python -m unittest tests.test_career_guidance
```

Expected before implementation: fail with missing `family_resource_raw` or `employment_preference_raw`.

- [ ] **Step 3: Update admissions aliases**

Use `apply_patch` to modify `domains/admissions/value_aliases.json`.

Add these top-level arrays after `ownership_terms`:

```json
  "family_resource_terms": ["家里有资源", "家里资源", "父母资源", "亲戚资源", "行业资源", "家里在医疗系统有资源", "家里在体制内有资源"],
  "no_family_resource_terms": ["家里没有资源", "家里没资源", "没有资源", "没资源", "家里帮不上"],
  "employment_terms": ["就业前景好", "好就业", "好找工作", "就业更好", "将来好就业"],
  "career_goal_terms": ["稳定就业", "体制内", "考公", "考编", "高薪", "本地就业", "升学深造", "读研"],
```

Also add these strings to `other_vague_terms` if they are not already present:

```json
    "好找工作",
    "就业更好",
    "将来好就业",
    "稳定就业",
    "体制内",
    "考公",
    "考编",
    "高薪",
    "本地就业",
    "升学深造",
    "读研"
```

- [ ] **Step 4: Update RegexExtractor**

Use `apply_patch` to modify `src/extractors/regex_extractor.py`.

Inside `extract`, after `cooperation_preference_raw = ...`, insert:

```python
        family_resource_raw = self._family_resource_raw(text)
        employment_preference_raw = self._first_present(
            text,
            self.aliases["employment_terms"],
        )
        career_goal_raw = self._first_present(
            text,
            self.aliases["career_goal_terms"],
        )
```

In the returned `preferences` dict, after `school_ownership_preference_raw`, add:

```python
                "employment_preference_raw": employment_preference_raw,
                "family_resource_raw": family_resource_raw,
                "career_goal_raw": career_goal_raw,
```

Change the `_raw_sources` call to pass the new values:

```python
            "raw_sources": self._raw_sources(
                text=text,
                major_expansion_raw=major_expansion_raw,
                cooperation_preference_raw=cooperation_preference_raw,
                employment_preference_raw=employment_preference_raw,
                family_resource_raw=family_resource_raw,
                career_goal_raw=career_goal_raw,
                other_vague_preferences=other_vague_preferences,
            ),
```

Add this helper method after `_preferred_school_provinces`:

```python
    def _family_resource_raw(self, text: str) -> str | None:
        no_resource = self._first_present(text, self.aliases["no_family_resource_terms"])
        if no_resource:
            return no_resource
        return self._first_present(text, self.aliases["family_resource_terms"])
```

Update `_raw_sources` signature to:

```python
    def _raw_sources(
        self,
        text: str,
        major_expansion_raw: str | None,
        cooperation_preference_raw: str | None,
        employment_preference_raw: str | None,
        family_resource_raw: str | None,
        career_goal_raw: str | None,
        other_vague_preferences: list[str],
    ) -> dict[str, Any]:
```

Inside `_raw_sources`, after the cooperation block, insert:

```python
        if employment_preference_raw:
            sources["preferences.employment_preference_raw"] = employment_preference_raw
        if family_resource_raw:
            sources["preferences.family_resource_raw"] = family_resource_raw
        if career_goal_raw:
            sources["preferences.career_goal_raw"] = career_goal_raw
```

- [ ] **Step 5: Update attribute grounding policy**

Use `apply_patch` to modify `domains/admissions/attribute_grounding.json`.

Add these entries inside `slot_policies` after `preferences.school_ownership_preference_raw`:

```json
    "preferences.employment_preference_raw": {
      "field_id": "employment_outlook",
      "attribute_class": "external_info",
      "status": "missing_schema",
      "reason": "当前数据中没有已审查的就业结果字段，不能把“好就业”作为筛选条件。"
    },
    "preferences.family_resource_raw": {
      "field_id": null,
      "attribute_class": "context_only",
      "status": "context_only",
      "reason": "家庭资源只用于后续信息需求和解释，不是招生表字段，不能作为筛选条件。"
    },
    "preferences.career_goal_raw": {
      "field_id": null,
      "attribute_class": "context_only",
      "status": "context_only",
      "reason": "就业目标只用于解释和追问，不能直接作为招生表筛选条件。"
    },
```

Add these entries inside `other_vague_policies`:

```json
    "好找工作": {"field_id": "employment_outlook", "status": "missing_schema", "reason": "当前数据中没有就业结果字段。"},
    "就业更好": {"field_id": "employment_outlook", "status": "missing_schema", "reason": "当前数据中没有就业结果字段。"},
    "将来好就业": {"field_id": "employment_outlook", "status": "missing_schema", "reason": "当前数据中没有就业结果字段。"},
    "稳定就业": {"field_id": null, "status": "context_only", "reason": "稳定就业是目标偏好，需要转成明确信息需求或经审查字段后才能执行。"},
    "体制内": {"field_id": null, "status": "context_only", "reason": "体制内是就业目标，不是当前招生表字段。"},
    "考公": {"field_id": null, "status": "context_only", "reason": "考公是就业目标，不是当前招生表字段。"},
    "考编": {"field_id": null, "status": "context_only", "reason": "考编是就业目标，不是当前招生表字段。"},
    "高薪": {"field_id": "employment_outlook", "status": "missing_schema", "reason": "当前数据中没有薪资或就业结果字段。"},
    "本地就业": {"field_id": null, "status": "context_only", "reason": "本地就业需要明确城市或家庭所在地，不能直接执行。"},
    "升学深造": {"field_id": null, "status": "context_only", "reason": "升学深造是目标偏好，当前不作为招生表筛选字段。"},
    "读研": {"field_id": null, "status": "context_only", "reason": "读研是目标偏好，当前不作为招生表筛选字段。"}
```

- [ ] **Step 6: Update LLM slot adapter schema**

Use `apply_patch` to modify `src/extractors/llm_slot_adapter.py`.

Inside `SLOT_ADAPTER_SCHEMA["properties"]["preferences"]["properties"]`, after `school_ownership_preference_raw`, add:

```python
                "employment_preference_raw": {"type": ["string", "null"]},
                "family_resource_raw": {"type": ["string", "null"]},
                "career_goal_raw": {"type": ["string", "null"]},
```

Inside `_preferences`, after `school_ownership_preference_raw`, add:

```python
        "employment_preference_raw": _optional_text(
            source.get("employment_preference_raw")
        ),
        "family_resource_raw": _optional_text(
            source.get("family_resource_raw")
        ),
        "career_goal_raw": _optional_text(source.get("career_goal_raw")),
```

- [ ] **Step 7: Update DeepSeek extractor prompt and normalization**

Use `apply_patch` to modify `src/extractors/deepseek_extractor.py`.

In the JSON structure string, replace:

```python
                '"school_ownership_preference_raw": string|null, '
                '"recommendation_request_raw": string|null, "other_vague_preferences": [string]}, '
```

with:

```python
                '"school_ownership_preference_raw": string|null, '
                '"employment_preference_raw": string|null, '
                '"family_resource_raw": string|null, '
                '"career_goal_raw": string|null, '
                '"recommendation_request_raw": string|null, "other_vague_preferences": [string]}, '
```

After the ownership normalization block, add:

```python
    employment = preferences.get("employment_preference_raw")
    if employment:
        preferences["employment_preference_raw"] = str(employment)
    elif any(term in original_text for term in ["就业前景好", "好就业", "好找工作", "就业更好", "将来好就业"]):
        preferences["employment_preference_raw"] = "好就业"
    else:
        preferences["employment_preference_raw"] = None

    family_resource = preferences.get("family_resource_raw")
    if family_resource:
        preferences["family_resource_raw"] = str(family_resource)
    elif any(term in original_text for term in ["家里没有资源", "家里没资源", "没有资源", "没资源", "家里帮不上"]):
        preferences["family_resource_raw"] = "家里没有资源"
    elif any(term in original_text for term in ["家里有资源", "家里资源", "父母资源", "亲戚资源", "行业资源"]):
        preferences["family_resource_raw"] = "家里有资源"
    else:
        preferences["family_resource_raw"] = None

    career_goal = preferences.get("career_goal_raw")
    if career_goal:
        preferences["career_goal_raw"] = str(career_goal)
    else:
        preferences["career_goal_raw"] = next(
            (
                term
                for term in ["稳定就业", "体制内", "考公", "考编", "高薪", "本地就业", "升学深造", "读研"]
                if term in original_text
            ),
            None,
        )
```

- [ ] **Step 8: Update LLM adapter test**

Use `apply_patch` to modify `tests/test_llm_slot_adapter.py`.

In `test_adapter_validates_and_strips_rule_shaped_output`, add these preferences to the fake payload:

```python
                        "employment_preference_raw": "好就业",
                        "family_resource_raw": "家里没有资源",
                        "career_goal_raw": "稳定就业",
```

After the existing assertions, add:

```python
        self.assertEqual(slots["preferences"]["employment_preference_raw"], "好就业")
        self.assertEqual(slots["preferences"]["family_resource_raw"], "家里没有资源")
        self.assertEqual(slots["preferences"]["career_goal_raw"], "稳定就业")
```

- [ ] **Step 9: Run focused extractor tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_career_guidance tests.test_llm_slot_adapter tests.test_rule_verifier
```

Expected: all selected tests pass; no test calls real DeepSeek.

- [ ] **Step 10: Commit Task 2**

Run:

```bash
git add domains/admissions/value_aliases.json domains/admissions/attribute_grounding.json src/extractors/regex_extractor.py src/extractors/llm_slot_adapter.py src/extractors/deepseek_extractor.py tests/test_career_guidance.py tests/test_llm_slot_adapter.py
git commit -m "feat: extract career resource preferences safely"
```

Expected: commit succeeds and includes only Task 2 files.

## Task 3: 新增 deterministic career guidance policy

**Files:**
- Create: `domains/admissions/career_decision_policy.json`
- Modify: `domains/admissions/domain.json`
- Modify: `src/domains/domain_config.py`
- Create: `src/reporting/career_guidance.py`
- Modify: `tests/test_career_guidance.py`

- [ ] **Step 1: Add career guidance behavior tests**

Use `apply_patch` to insert these tests in `tests/test_career_guidance.py` before the final `if __name__ == "__main__":` block:

```python
from src.reporting.career_guidance import career_guidance_for_query


class CareerGuidancePolicyTest(unittest.TestCase):
    def test_no_resource_good_employment_returns_information_request_only(self) -> None:
        query = "家里没资源，不知道怎么选专业，想选好就业的。"
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        self.assertEqual(guidance["status"], "reference_only")
        self.assertEqual(guidance["execution_effect"], "does_not_change_sql_or_results")
        self.assertIn(
            "career_no_family_resource_goal",
            [item["rule_id"] for item in guidance["matched_rules"]],
        )
        self.assertIn(
            "employment_outlook",
            [item["field_id"] for item in guidance["no_schema_field_preferences"]],
        )
        self.assertTrue(
            any(
                item["question_id"] == "q_employment_goal"
                for item in guidance["information_requests"]
            )
        )

    def test_family_resource_query_asks_for_resource_details(self) -> None:
        query = "家里在医疗系统有资源，想看以后更好就业的专业。"
        slots = RegexExtractor().extract(query)

        guidance = career_guidance_for_query(query, slots, ADMISSIONS_DOMAIN)

        question_ids = {
            item["question_id"]
            for item in guidance["information_requests"]
        }
        self.assertIn("q_family_resource_industry", question_ids)
        self.assertIn("q_family_resource_city", question_ids)
        self.assertFalse(guidance["executable"])
```

- [ ] **Step 2: Run tests to verify missing module**

Run:

```bash
.venv/bin/python -m unittest tests.test_career_guidance
```

Expected before implementation: fail with `ModuleNotFoundError: No module named 'src.reporting.career_guidance'`.

- [ ] **Step 3: Create admissions career policy JSON**

Use `apply_patch` to create `domains/admissions/career_decision_policy.json` with exactly this content:

```json
{
  "description": "家庭资源与就业偏好 deterministic guidance policy。该文件不是知识库，不参与 SQL，只产生 EvidencePack 中的解释和信息需求。",
  "status": "approved",
  "execution_effect": "does_not_change_sql_or_results",
  "rules": [
    {
      "rule_id": "career_no_family_resource_goal",
      "label": "家里缺少就业资源时先明确就业目标",
      "trigger_slots": {
        "preferences.family_resource_raw": ["家里没有资源", "家里没资源", "没有资源", "没资源", "家里帮不上"]
      },
      "trigger_terms": ["好就业", "就业前景好", "好找工作", "就业更好", "将来好就业"],
      "information_requests": [
        {
          "question_id": "q_employment_goal",
          "label": "就业目标",
          "question": "请先选择更看重的就业目标：稳定就业、体制内/考公考编、高薪市场化、本地就业、升学深造。",
          "fixed_options": ["稳定就业", "体制内/考公考编", "高薪市场化", "本地就业", "升学深造"],
          "reason": "没有家庭资源时，系统不能把“好就业”直接翻译成专业筛选条件。"
        }
      ],
      "no_schema_field_preferences": [
        {
          "source_text": "好就业",
          "field_id": "employment_outlook",
          "field": "就业结果字段",
          "match_type": "no_schema_field",
          "executable": false,
          "reason": "当前数据中没有已审查就业结果字段，不能执行“好就业”筛选。"
        }
      ]
    },
    {
      "rule_id": "career_family_resource_context",
      "label": "家庭资源只能作为上下文补充",
      "trigger_slots": {
        "preferences.family_resource_raw": ["家里有资源", "家里资源", "父母资源", "亲戚资源", "行业资源", "家里在医疗系统有资源", "家里在体制内有资源"]
      },
      "trigger_terms": ["好就业", "就业前景好", "好找工作", "就业更好", "将来好就业"],
      "information_requests": [
        {
          "question_id": "q_family_resource_industry",
          "label": "资源行业",
          "question": "请说明家庭资源所在行业或单位类型，例如医疗、教育、金融、制造、互联网、体制内。",
          "fixed_options": ["医疗", "教育", "金融", "制造", "互联网", "体制内", "其他"],
          "reason": "行业资源必须先结构化，不能让系统从自由文本推断专业筛选条件。"
        },
        {
          "question_id": "q_family_resource_city",
          "label": "资源城市",
          "question": "请说明资源主要所在城市或是否必须本地就业。",
          "fixed_options": ["广州", "深圳", "佛山", "东莞", "珠海", "其他广东城市", "不限城市"],
          "reason": "城市边界明确后，仍需走 city 字段 grounding 和 confirmation。"
        }
      ],
      "no_schema_field_preferences": [
        {
          "source_text": "就业前景好",
          "field_id": "employment_outlook",
          "field": "就业结果字段",
          "match_type": "no_schema_field",
          "executable": false,
          "reason": "当前数据中没有已审查就业结果字段，家庭资源也不能替代就业数据字段。"
        }
      ]
    },
    {
      "rule_id": "career_goal_context_only",
      "label": "就业目标作为上下文保留",
      "trigger_slots": {
        "preferences.career_goal_raw": ["稳定就业", "体制内", "考公", "考编", "高薪", "本地就业", "升学深造", "读研"]
      },
      "trigger_terms": [],
      "information_requests": [
        {
          "question_id": "q_goal_to_candidate_major_set",
          "label": "专业集合确认",
          "question": "如果要把就业目标变成专业集合，必须先由 reviewed policy 给出候选专业集合，并通过 candidate_id 确认。",
          "fixed_options": ["暂不转成筛选条件"],
          "reason": "当前版本不把就业目标直接映射到专业集合。"
        }
      ],
      "no_schema_field_preferences": []
    }
  ]
}
```

- [ ] **Step 4: Register policy path in domain pack**

Use `apply_patch` to modify `domains/admissions/domain.json`.

Inside `"paths"`, after `"policy_references": "policy_references"`, add a comma to the previous line if needed and insert:

```json
    "career_decision_policy": "career_decision_policy.json"
```

- [ ] **Step 5: Add DomainConfig path helper**

Use `apply_patch` to modify `src/domains/domain_config.py`.

After `policy_references` path-related properties are not currently present; add this property after `top_result_mapping_path`:

```python
    @property
    def career_decision_policy_path(self) -> Path | None:
        paths = self.payload.get("paths") or {}
        if "career_decision_policy" not in paths:
            return None
        return self.resolve_path(paths["career_decision_policy"])
```

- [ ] **Step 6: Create deterministic guidance module**

Use `apply_patch` to create `src/reporting/career_guidance.py` with exactly this content:

```python
"""家庭资源和就业偏好的确定性解释层。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.domains import DomainConfig


EMPTY_GUIDANCE = {
    "status": "reference_only",
    "execution_effect": "does_not_change_sql_or_results",
    "executable": False,
    "matched_rules": [],
    "information_requests": [],
    "no_schema_field_preferences": [],
}


def career_guidance_for_query(
    user_request: str,
    slots: dict[str, Any] | None,
    domain_config: DomainConfig | None = None,
) -> dict[str, Any]:
    """匹配 reviewed career policy，返回不参与 SQL 的证据。"""

    domain_config = domain_config or DomainConfig.load()
    policy_path = domain_config.career_decision_policy_path
    if policy_path is None or not policy_path.exists():
        return dict(EMPTY_GUIDANCE)
    policy = _load_policy(str(policy_path))
    matched_rules = []
    information_requests = []
    no_schema_preferences = []
    for rule in policy.get("rules") or []:
        if not _rule_matches(rule, user_request, slots or {}):
            continue
        matched_rules.append(
            {
                "rule_id": rule["rule_id"],
                "label": rule["label"],
                "effect": policy.get("execution_effect", "does_not_change_sql_or_results"),
            }
        )
        information_requests.extend(
            _request_with_rule_id(rule["rule_id"], item)
            for item in rule.get("information_requests") or []
        )
        no_schema_preferences.extend(
            _preference_with_rule_id(rule["rule_id"], item)
            for item in rule.get("no_schema_field_preferences") or []
        )
    return {
        "status": "reference_only",
        "execution_effect": policy.get("execution_effect", "does_not_change_sql_or_results"),
        "executable": False,
        "matched_rules": matched_rules,
        "information_requests": _dedupe_by_key(information_requests, "question_id"),
        "no_schema_field_preferences": _dedupe_by_pair(
            no_schema_preferences,
            "field_id",
            "source_text",
        ),
    }


@lru_cache(maxsize=16)
def _load_policy(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rule_matches(
    rule: dict[str, Any],
    user_request: str,
    slots: dict[str, Any],
) -> bool:
    trigger_terms = [str(term) for term in rule.get("trigger_terms") or []]
    term_matched = not trigger_terms or any(term in user_request for term in trigger_terms)
    slot_matched = _slot_trigger_matches(rule.get("trigger_slots") or {}, slots)
    return term_matched and slot_matched


def _slot_trigger_matches(
    trigger_slots: dict[str, list[str]],
    slots: dict[str, Any],
) -> bool:
    if not trigger_slots:
        return True
    for path, expected_values in trigger_slots.items():
        value = _value_at(slots, path.split("."))
        if value is None:
            continue
        text = str(value)
        if any(str(expected) in text for expected in expected_values):
            return True
    return False


def _value_at(payload: dict[str, Any], path: list[str]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _request_with_rule_id(rule_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"rule_id": rule_id, **dict(item)}


def _preference_with_rule_id(rule_id: str, item: dict[str, Any]) -> dict[str, Any]:
    return {"rule_id": rule_id, **dict(item)}


def _dedupe_by_key(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        value = item.get(key)
        if value in seen:
            continue
        seen.add(value)
        result.append(item)
    return result


def _dedupe_by_pair(
    items: list[dict[str, Any]],
    first_key: str,
    second_key: str,
) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = (item.get(first_key), item.get(second_key))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
```

- [ ] **Step 7: Run focused guidance tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_career_guidance
```

Expected: all tests in `tests.test_career_guidance` pass.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add domains/admissions/career_decision_policy.json domains/admissions/domain.json src/domains/domain_config.py src/reporting/career_guidance.py tests/test_career_guidance.py
git commit -m "feat: add career guidance policy"
```

Expected: commit succeeds and includes only Task 3 files.

## Task 4: 接入 EvidencePack 和 WorkbenchResponse

**Files:**
- Modify: `src/reporting/evidence_pack.py`
- Modify: `src/api/workbench.py`
- Modify: `src/reporting/template_report_builder.py`
- Modify: `src/reporting/deepseek_answer_generator.py`
- Modify: `tests/test_career_guidance.py`
- Modify: `tests/test_workbench_api_contract.py`

- [ ] **Step 1: Add Workbench evidence tests**

Use `apply_patch` to insert these tests in `tests/test_career_guidance.py` before the final `if __name__ == "__main__":` block:

```python
from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse


class CareerGuidanceWorkbenchTest(unittest.TestCase):
    def test_good_employment_guidance_does_not_enter_sql(self) -> None:
        query = "广东物理，位次9000，想读计算机，家里没资源，想选好就业的专业，请推荐。"

        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=query,
                soft_preferences={"prompt": query},
                extractor="regex",
            )
        )

        guidance = result["evidence_pack"]["decision_guidance"]
        self.assertEqual(guidance["execution_effect"], "does_not_change_sql_or_results")
        self.assertFalse(guidance["executable"])
        self.assertTrue(guidance["information_requests"])
        self.assertNotIn(
            "employment_outlook",
            [item["field"] for item in result["executed_filters"]],
        )
        self.assertNotIn(
            "就业结果字段",
            str(result["evidence_pack"]["execution_summary"].get("params")),
        )
        self.assertIn("就业与家庭资源说明（不参与筛选）", result["answer"])

    def test_score_only_with_career_guidance_still_does_not_execute(self) -> None:
        query = "广东物理，630分，家里没资源，想选好就业的计算机专业。"

        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=query,
                hard_filters={"source_province": "广东", "subject_type": "物理", "user_score": 630},
                soft_preferences={"prompt": query},
                extractor="regex",
            )
        )

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["debug_trace"]["execution"]["sql"], "")
        self.assertEqual(
            result["evidence_pack"]["decision_guidance"]["execution_effect"],
            "does_not_change_sql_or_results",
        )
```

Add this assertion to a stable contract test in `tests/test_workbench_api_contract.py` after `assert_workbench_contract` runs:

```python
        self.assertIn("decision_guidance", result["evidence_pack"])
        self.assertEqual(
            result["evidence_pack"]["decision_guidance"]["execution_effect"],
            "does_not_change_sql_or_results",
        )
```

- [ ] **Step 2: Run tests to verify missing EvidencePack field**

Run:

```bash
.venv/bin/python -m unittest tests.test_career_guidance tests.test_workbench_api_contract
```

Expected before implementation: fail because `decision_guidance` is missing.

- [ ] **Step 3: Add EvidencePack field**

Use `apply_patch` to modify `src/reporting/evidence_pack.py`.

Add this dataclass field after `policy_references`:

```python
    decision_guidance: dict[str, Any] = field(default_factory=dict)
```

Add this parameter to `from_verified_pipeline` after `policy_references`:

```python
        decision_guidance: dict[str, Any] | None = None,
```

Add this argument in the `return cls(...)` call:

```python
            decision_guidance=decision_guidance or {
                "status": "reference_only",
                "execution_effect": "does_not_change_sql_or_results",
                "executable": False,
                "matched_rules": [],
                "information_requests": [],
                "no_schema_field_preferences": [],
            },
```

- [ ] **Step 4: Add Workbench helper functions**

Use `apply_patch` to modify `src/api/workbench.py`.

Add this import with reporting imports:

```python
from src.reporting.career_guidance import career_guidance_for_query
```

Add these helpers near `_planned_not_executed_preference`:

```python
def _decision_guidance_for_payload(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return career_guidance_for_query(
        _compose_user_request(config),
        slots or {},
        domain_config,
    )


def _guidance_not_executed_preferences(
    guidance: dict[str, Any],
) -> list[dict[str, Any]]:
    items = []
    for index, item in enumerate(
        guidance.get("no_schema_field_preferences") or [],
        start=1,
    ):
        source_text = str(item.get("source_text") or "就业偏好")
        reason = str(item.get("reason") or "当前数据中没有可执行字段。")
        items.append(
            {
                "id": f"career_guidance_not_exec_{index}",
                "source_text": source_text,
                "preference": source_text,
                "display": f"{source_text}未执行：{reason}",
                "reason": reason,
                "missing_field": item.get("field") or item.get("field_id") or "缺少已审查数据字段",
                "source_span": source_text,
            }
        )
    return items
```

- [ ] **Step 5: Wire guidance into legacy verified pipeline**

Use `apply_patch` to modify `_run_workbench` in `src/api/workbench.py`.

After `policy_references = _policy_references_for_config(config, domain_config)`, insert:

```python
    decision_guidance = _decision_guidance_for_payload(
        config,
        domain_config,
        slots,
    )
    guidance_not_executed = _guidance_not_executed_preferences(decision_guidance)
```

In the `EvidencePack.from_verified_pipeline(...)` call, add:

```python
        decision_guidance=decision_guidance,
```

In `legacy_payload`, change `"not_executed_preferences": ...` to:

```python
        "not_executed_preferences": (
            _not_executed_preferences(classified_rules, domain_config)
            + guidance_not_executed
        ),
```

- [ ] **Step 6: Wire guidance into admissions planned query payload**

Use `apply_patch` to modify `_planned_query_payload` in `src/api/workbench.py`.

After `policy_references = _policy_references_for_config(config, domain_config)`, insert:

```python
    decision_guidance = _decision_guidance_for_payload(
        config,
        domain_config,
        {},
    )
    guidance_not_executed = _guidance_not_executed_preferences(decision_guidance)
```

In `evidence_pack`, add:

```python
        "decision_guidance": decision_guidance,
```

Change `"not_executed_preferences": planned_result.no_schema_field_preferences,` to:

```python
        "not_executed_preferences": (
            planned_result.no_schema_field_preferences
            + guidance_not_executed
        ),
```

In `legacy_payload`, change `"not_executed_preferences": [...]` to:

```python
        "not_executed_preferences": [
            _planned_not_executed_preference(index, item)
            for index, item in enumerate(
                planned_result.no_schema_field_preferences,
                start=1,
            )
        ] + guidance_not_executed,
```

Change `no_schema_field_preferences=planned_result.no_schema_field_preferences,` in `WorkbenchResponse(...)` to:

```python
        no_schema_field_preferences=(
            planned_result.no_schema_field_preferences
            + decision_guidance.get("no_schema_field_preferences", [])
        ),
```

- [ ] **Step 7: Display guidance in TemplateReportBuilder**

Use `apply_patch` to modify `src/reporting/template_report_builder.py`.

After the `policy_references` section and before “未执行但已保留的偏好”, insert:

```python
        if evidence.get("decision_guidance", {}).get("matched_rules"):
            lines.extend(["", "就业与家庭资源说明（不参与筛选）："])
            lines.extend(
                _decision_guidance_line(item)
                for item in evidence["decision_guidance"].get("matched_rules", [])
            )
            if evidence["decision_guidance"].get("information_requests"):
                lines.extend(["", "需要补充的信息："])
                lines.extend(
                    _information_request_line(item)
                    for item in evidence["decision_guidance"]["information_requests"]
                )
```

Add these helper functions before `_not_executed_line`:

```python
def _decision_guidance_line(item: dict[str, Any]) -> str:
    return (
        f"- {item.get('label')}：该规则只进入解释证据，"
        "不改变 SQL、不改变结果数量。"
    )


def _information_request_line(item: dict[str, Any]) -> str:
    options = item.get("fixed_options") or []
    option_text = f"固定选项：{'、'.join(str(option) for option in options)}。" if options else ""
    return f"- {item.get('label')}：{item.get('question')}{option_text}"
```

- [ ] **Step 8: Keep optional DeepSeek answer evidence-only**

Use `apply_patch` to modify `src/reporting/deepseek_answer_generator.py`.

In `DeepSeekAnswerGenerator.generate`, replace this user prompt fragment:

```python
                "抽取结果、规则提议审查、已执行规则、候选偏好确认、前置结果、"
                "未执行偏好和安全警告。每条前置结果如果存在这些字段，都要写出："
```

with:

```python
                "抽取结果、规则提议审查、已执行规则、候选偏好确认、"
                "就业与家庭资源说明、前置结果、未执行偏好和安全警告。"
                "decision_guidance 只能解释和追问，不得改变 SQL、结果数或 executed_rules。"
                "每条前置结果如果存在这些字段，都要写出："
```

In `_evidence_coverage_appendix`, before this line:

```python
    lines.extend(["- 前置结果："])
```

insert:

```python
    guidance = evidence.get("decision_guidance") or {}
    if guidance.get("matched_rules"):
        lines.extend(["- 就业与家庭资源说明（不参与筛选）："])
        lines.extend(
            f"  - {item.get('label')}：不改变 SQL、不改变结果数量。"
            for item in guidance.get("matched_rules") or []
        )
        if guidance.get("information_requests"):
            lines.extend(
                f"  - 需要补充：{item.get('label')}：{item.get('question')}"
                for item in guidance["information_requests"]
            )
```

Expected behavior: DeepSeek answer generation receives guidance as evidence-only context. It still must not read raw Excel or add unsupported employment claims.

- [ ] **Step 9: Run focused Workbench tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_career_guidance tests.test_workbench_api_contract tests.test_answer_reporting
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit Task 4**

Run:

```bash
git add src/reporting/evidence_pack.py src/api/workbench.py src/reporting/template_report_builder.py src/reporting/deepseek_answer_generator.py tests/test_career_guidance.py tests/test_workbench_api_contract.py
git commit -m "feat: expose career guidance evidence"
```

Expected: commit succeeds and includes only Task 4 files.

## Task 5: 前端只展示后端 guidance

**Files:**
- Modify: `frontend/src/components/BeginnerDecisionPanel.vue`
- Modify: `frontend/src/mock/demo_run.json`
- Modify: `frontend/README.md`

- [ ] **Step 1: Add frontend display logic**

Use `apply_patch` to modify `frontend/src/components/BeginnerDecisionPanel.vue`.

After `unusedItems`, add:

```javascript
const informationRequests = computed(() => listOrEmpty(
  props.runData.evidence_pack?.decision_guidance?.information_requests,
));
```

After the “还要你确认” section and before “没有参与筛选”, add:

```vue
    <section
      v-if="informationRequests.length"
      class="beginner-section warn"
    >
      <div class="beginner-section-title">
        <el-icon><WarningFilled /></el-icon>
        <h3>还需补充信息</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="request in informationRequests"
          :key="request.question_id"
          class="beginner-row"
        >
          <strong>{{ request.label || request.question_id }}</strong>
          <p>{{ request.question }}</p>
        </article>
      </div>
    </section>
```

- [ ] **Step 2: Update frontend mock**

Run the backend demo after Tasks 1-4:

```bash
.venv/bin/python scripts/run_mvp_demo.py
```

If the script refreshes `frontend/src/mock/demo_run.json`, inspect the diff and keep only deterministic mock changes related to `decision_guidance`, score-only behavior, and updated evidence text. If it writes unrelated timestamps or large output churn, revert those unrelated generated lines manually with `apply_patch`.

Expected mock fragment under `evidence_pack`:

```json
"decision_guidance": {
  "status": "reference_only",
  "execution_effect": "does_not_change_sql_or_results",
  "executable": false,
  "matched_rules": [],
  "information_requests": [],
  "no_schema_field_preferences": []
}
```

- [ ] **Step 3: Update frontend README**

Use `apply_patch` to add this sentence to the Workbench UI section of `frontend/README.md`:

```markdown
当 `EvidencePack.decision_guidance` 包含家庭资源或就业目标信息时，前端只展示后端返回的补充问题和“不参与筛选”说明；前端不根据这些信息生成 hard filter。
```

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build exits with code 0.

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add frontend/src/components/BeginnerDecisionPanel.vue frontend/src/mock/demo_run.json frontend/README.md
git commit -m "feat: show career guidance requests"
```

Expected: commit succeeds and includes only Task 5 files.

## Task 6: 更新方法论、API 契约和评估文字

**Files:**
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`
- Modify: `docs/full_project_plan.md`
- Modify: `docs/evaluation_report.md`
- Modify: `docs/operator_feedback_template.md`
- Modify: `docs/operator_trial_checklist.md`
- Modify: `README.md`

- [ ] **Step 1: Update API contract**

Use `apply_patch` to add this section to `docs/api_contract.md` after “EvidencePack reference-only 资料”:

````markdown
## EvidencePack decision_guidance

`EvidencePack.decision_guidance` 承载家庭资源、就业目标和“好就业”等表达的 deterministic guidance。它不是 hard rule，不参与 SQL，不改变 `executed_filters`、`result_count`、`result_sections` 或 `top_results`。

固定结构：

```json
{
  "status": "reference_only",
  "execution_effect": "does_not_change_sql_or_results",
  "executable": false,
  "matched_rules": [{"rule_id": "career_no_family_resource_goal", "label": "家里缺少就业资源时先明确就业目标", "effect": "does_not_change_sql_or_results"}],
  "information_requests": [{"question_id": "q_employment_goal", "label": "就业目标", "question": "请先选择更看重的就业目标：稳定就业、体制内/考公考编、高薪市场化、本地就业、升学深造。", "fixed_options": ["稳定就业", "体制内/考公考编", "高薪市场化", "本地就业", "升学深造"], "reason": "没有家庭资源时，系统不能把“好就业”直接翻译成专业筛选条件。"}],
  "no_schema_field_preferences": [{"source_text": "好就业", "field_id": "employment_outlook", "field": "就业结果字段", "match_type": "no_schema_field", "executable": false, "reason": "当前数据中没有已审查就业结果字段，不能执行“好就业”筛选。"}]
}
```

如果后续接入 reviewed 就业数据字段，必须先更新 `domains/admissions/schema_registry.json`、value index、RuleVerifier 测试和 API snapshot，再允许任何就业相关规则进入 execution。
````

- [ ] **Step 2: Update methodology**

Use `apply_patch` to add this paragraph to `docs/methodology_report.md` in the section that says the system does not predict employment:

```markdown
本次升级后，系统可以结构化处理“家里有/没有资源”“想好就业”等表达，但处理结果是 `decision_guidance`：它只记录 fixed policy 命中的解释、需要用户补充的信息，以及当前缺少就业结果字段的 no-schema 事实。它不预测就业，不把家庭资源代理成专业排序，不改变 SQL 和结果数量。
```

- [ ] **Step 3: Update project plan**

Use `apply_patch` to modify `docs/full_project_plan.md`.

Replace the bullet:

```markdown
- 就业预测。
```

with:

```markdown
- 就业预测；当前只允许 `EvidencePack.decision_guidance` 结构化记录就业/家庭资源偏好和补充问题，不参与筛选。
```

- [ ] **Step 4: Update evaluation-facing docs**

Use `apply_patch` to add this sentence to `docs/evaluation_report.md`, `docs/operator_feedback_template.md`, and `docs/operator_trial_checklist.md` near employment or unsupported preference checks:

```markdown
“好就业/就业前景好/家里资源”可进入 `decision_guidance` 或 no-schema 说明，但不得进入 `executed_filters`、SQL params 或 recommendation bucket 依据。
```

- [ ] **Step 5: Update README**

Use `apply_patch` to add this sentence to the README section that describes Workbench boundaries:

```markdown
系统可以把家庭资源和就业目标结构化为补充问题与非执行证据，但在缺少已审查就业结果字段前，不会按“好就业”筛选或排序。
```

- [ ] **Step 6: Search for stale claims**

Run:

```bash
rg -n "(就业预测|好就业|就业前景|家里资源|score_without_rank|分数没有位次|仅凭分数|recommendation)" README.md docs frontend/src/mock sample_outputs outputs/eval
```

Expected: every hit either describes the new non-execution guidance accurately or remains a historical risk-review finding. Update any stale line that says score-only recommendation returns `ok` or implies employment preferences execute.

- [ ] **Step 7: Commit Task 6**

Run:

```bash
git add README.md docs/api_contract.md docs/methodology_report.md docs/full_project_plan.md docs/evaluation_report.md docs/operator_feedback_template.md docs/operator_trial_checklist.md
git commit -m "docs: explain career guidance boundary"
```

Expected: commit succeeds and includes only Task 6 files.

## Task 7: 全量验证和最终提交检查

**Files:**
- Read: all changed files from Tasks 1-6.

- [ ] **Step 1: Run backend test suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: all tests pass. If a failure appears in a test touched by this plan, fix it within the relevant task’s files and rerun the same command.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits with code 0.

- [ ] **Step 3: Run docs diff check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Verify no accidental execution path**

Run:

```bash
rg -n "(employment_outlook|family_resource|career_goal|decision_guidance)" src domains tests docs frontend/src README.md
```

Expected:

- `employment_outlook` appears only in grounding policy, guidance no-schema records, tests, and docs.
- No `DuckDBExecutor`, `hard_filter_rules`, `RulePromoter`, or `AdmissionsQueryPlanner._fetch_recommendation_rows` branch uses `employment_outlook`, `family_resource_raw`, or `career_goal_raw`.
- `decision_guidance` appears only in EvidencePack/report/API/frontend display paths.

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short
```

Expected: clean worktree after the task commits. If generated files changed unexpectedly, inspect them and either commit only relevant deterministic artifacts or revert unrelated generated churn with `apply_patch`.

## Self-Review

- Spec coverage: 本计划覆盖教授提出的“先规则、再匹配、不是切片知识库”“数字不让大模型处理”“最后把结构化数据给大模型解释”。Task 1 先修 rank-first domain invariant；Tasks 2-4 建 reviewed deterministic policy 和 EvidencePack；Task 5 只让前端展示 API 输出；Task 6 更新公开文档。
- 占位词扫描：本计划没有禁用占位词或空泛“添加验证”步骤；每个代码变更步骤给出具体文件、代码或断言。
- Type consistency: 新字段统一命名为 `employment_preference_raw`、`family_resource_raw`、`career_goal_raw`、`decision_guidance`；EvidencePack、Workbench、frontend 和测试使用同一字段名。
