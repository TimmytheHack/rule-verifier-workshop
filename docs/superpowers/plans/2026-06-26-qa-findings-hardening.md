# QA Findings 加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 2026-06-26 真实前后端联调发现的问题收敛成可验证修复：内置 admissions 的 `深圳大学` 不再误落到城市筛选，uploaded admissions 的 `llm_semantic` 查询必须合并 UI 硬条件，前端状态必须只展示真实可操作的确认项，并补上防止运行产物落后的 release 校验。

**Architecture:** 不改变现有执行边界。后端继续由 LLM 提出 `SemanticIntent` / `RankingPlan`，系统通过 evidence gate、grounder、verifier、SQL builder 和 DuckDB 执行；前端只展示 API 输出和本地状态归一化结果。此次修复把“已审查 evidence 能否执行”和“用户界面是否可操作”分开处理。

**Tech Stack:** Python `unittest`、FastAPI `TestClient`、DuckDB warehouse、`SchemaValueIndex`、Vue 3、Element Plus、Node.js `node --test`、Vite。

---

## Findings 输入

1. P1：内置 admissions live `outputs/data/schema_value_index.json` 只有 10 个字段，没有 `university_name`。单测仓库临时 build 有 27 个字段，所以测试通过，但运行时 `我想进深圳大学...` 会执行 `城市 in_contains 深圳`，返回香港中文大学(深圳)、哈尔滨工业大学(深圳) 等。
2. P1：uploaded admissions `llm_semantic` 路径中，UI 已提交 `source_province`、`subject_type`、`reselected_subjects`、`user_rank`，但 `SemanticIntent.user_context` 和 preflight recognized facts 只可靠包含 rank。后续 semantic recommendation 仍发出 `subject_type_not_provided` / `subject_requirement_not_provided`。
3. P2：主查询页显示 `待确认`，但候选项缺少系统生成的 `candidate_id`，用户没有可执行确认动作；证据调试页和主查询页的确认语义不一致。
4. P2：`not_executed_preferences` 在主查询说明中会重复展示同一条偏好，例如“中外合作未执行”出现两次。
5. P3：启用 LLM 后，`模型用量` 中 `抽取调用` 可能为空表格；用户无法判断是未调用、未返回 usage，还是只发生了 answer generation。
6. QA 限制：当前 in-app Browser 工具未暴露 file chooser / `setInputFiles`，真实浏览器上传只能通过 API 流程覆盖；移动 viewport 调整在本次工具运行中超时，需补可重复的人工/脚本检查记录。

---

## 文件结构

- Modify: `outputs/data/schema_value_index.json`
  - 重新由 `scripts/build_data_warehouse.py` 生成，必须包含 `university_name`、`group_code`、`major_code` 等 live Workbench 需要的已审查字段。
- Modify: `outputs/data/ingestion_summary.json`
  - 同步记录新的 field profiles 和 fingerprint。
- Modify: `scripts/validate_release_package.py`
  - 增加 built-in admissions schema/value index 静态校验，防止提交旧 index。
- Modify: `tests/test_data_warehouse.py`
  - 临时仓库构建测试覆盖 `university_name` value index。
- Create: `tests/test_builtin_value_index_artifact.py`
  - 直接读取 tracked `outputs/data/schema_value_index.json`，校验 live artifact 与文档承诺一致。
- Modify: `tests/test_workbench_value_entity_linking.py`
  - 增加使用默认 live artifact 的回归，避免只测 patched 临时 warehouse。
- Modify: `src/api/workbench.py`
  - 增加 semantic intent 的 hard filter merge helper，并在 LLM semantic planner output / supplied semantic intent 进入 gate 前调用。
- Modify: `src/api/workbench_preflight.py`
  - `recognized_facts` 从 `hard_filters` 完整提取生源地、科类、再选科目、排位；preflight planner trace 使用 merge 后的 intent。
- Modify: `tests/test_uploaded_dataset_flow.py`
  - 覆盖 uploaded admissions preflight 和 query 合并 UI 硬条件。
- Modify: `tests/test_tool_server_endpoints.py`
  - 覆盖 HTTP preflight/query contract 中 hard filters 不被 LLM 空值覆盖。
- Modify: `frontend/src/utils/workbenchState.js`
  - 增加候选确认和未执行偏好的归一化工具。
- Modify: `frontend/src/utils/workbenchState.test.js`
  - 覆盖 warning-only candidates、去重未执行偏好和 quick stats 输入。
- Modify: `frontend/src/utils/workbenchRunBar.js`
  - `needs_confirmation` 只有存在可确认 `candidate_id` 时才显示“待确认”。
- Modify: `frontend/src/utils/workbenchRunBar.test.js`
  - 覆盖 `needs_confirmation` 但没有 confirmable candidate 的显示。
- Modify: `frontend/src/App.vue`
  - quick stats 使用归一化后的 confirmable/warning-only/unused counts。
- Modify: `frontend/src/components/CandidateRerunPanel.vue`
  - 区分“可确认条件”和“仅提示，不能确认”。
- Modify: `frontend/src/components/BeginnerDecisionPanel.vue`
  - “还要你确认”只显示可确认项；缺少 `candidate_id` 的项进入提示/未参与区域。
- Modify: `frontend/src/components/TokenUsagePanel.vue`
  - 为每个调用段落显示“未调用 / 未返回用量 / 已返回用量”，不展示空表格。
- Modify: `frontend/src/components/workspaces/QueryWorkspace.vue`
  - 传入 run summary 所需的 selected options 和归一化状态。
- Modify: `README.md`
  - 更新 live schema/value index artifact 要求、preflight hard filters 合并说明和 LLM usage 读法。
- Modify: `docs/api_contract.md`
  - 明确 `/workbench/preflight` recognized facts 来源和 query 合并硬条件规则。
- Modify: `docs/methodology_report.md`
  - 记录 value entity linker 依赖 tracked artifact 完整性，以及 uploaded hard filters 不可被 LLM 空值覆盖。
- Modify: `frontend/README.md`
  - 记录主查询确认状态展示规则和模型用量解释。
- Modify: `docs/troubleshooting.md`
  - 增加 built-in value index 旧产物导致实体链接失效的排查步骤。

---

## Task 1: 固化 live value index artifact 问题

**Files:**
- Modify: `tests/test_data_warehouse.py`
- Create: `tests/test_builtin_value_index_artifact.py`
- Modify: `tests/test_workbench_value_entity_linking.py`
- Modify: `scripts/validate_release_package.py`

- [ ] **Step 1: 扩展临时仓库 build 测试**

在 `tests/test_data_warehouse.py` 的 sample dataframe 中增加源列：

```python
{
    "院校名称": "深圳大学",
    "院校专业组代码": "10590101",
    "专业代码": "080901",
    "专业全称": "计算机科学与技术",
}
```

并在断言区增加：

```python
self.assertIn("university_name", index_payload["fields"])
self.assertTrue(index_payload["fields"]["university_name"]["active"])
self.assertTrue(index_payload["fields"]["university_name"]["lookup_complete"])
self.assertIn("深圳大学", index_payload["fields"]["university_name"]["lookup_values"])
```

运行：

```bash
.venv/bin/python -m unittest tests.test_data_warehouse
```

Expected: pass。

- [ ] **Step 2: 新增 tracked artifact 回归测试**

Create `tests/test_builtin_value_index_artifact.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "outputs/data/schema_value_index.json"


class BuiltInValueIndexArtifactTest(unittest.TestCase):
    def test_tracked_admissions_value_index_contains_entity_fields(self) -> None:
        payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        fields = payload["fields"]

        for field_id in ["university_name", "city", "major_name", "group_code"]:
            with self.subTest(field_id=field_id):
                self.assertIn(field_id, fields)
                self.assertIs(fields[field_id].get("active"), True)
                self.assertTrue(fields[field_id].get("lookup_values"))

        self.assertIn("深圳大学", fields["university_name"]["lookup_values"])
        self.assertIn("深圳", fields["city"]["lookup_values"])


if __name__ == "__main__":
    unittest.main()
```

运行：

```bash
.venv/bin/python -m unittest tests.test_builtin_value_index_artifact
```

Expected before artifact regeneration: fail on missing `university_name`。Expected after regeneration: pass。

- [ ] **Step 3: 增加 live Workbench 回归**

在 `tests/test_workbench_value_entity_linking.py` 新增一个不用 `run_workbench_with_test_warehouse` patch 的测试：

```python
def test_live_builtin_artifact_links_shenzhen_university(self) -> None:
    response = run_workbench(
        WorkbenchConfig(
            user_input="我想进深圳大学，目前排位15000，帮我看看有什么专业可以选",
            extractor="regex",
        )
    )

    assert_workbench_contract(self, response)
    self.assertIn(("院校名称", "eq", "深圳大学"), _filter_tuples(response))
    self.assertNotIn(("城市", "in_contains", ["深圳"]), _filter_tuples(response))
```

需要把 `run_workbench` import 进该文件：

```python
from src.api.workbench import WorkbenchConfig, run_workbench
```

运行：

```bash
.venv/bin/python -m unittest tests.test_workbench_value_entity_linking
```

Expected after artifact regeneration: pass。

- [ ] **Step 4: release check 校验 built-in index**

在 `scripts/validate_release_package.py` 增加常量：

```python
BUILTIN_VALUE_INDEX_PATH = ROOT_DIR / "outputs/data/schema_value_index.json"
REQUIRED_BUILTIN_VALUE_FIELDS = {
    "university_name": "深圳大学",
    "city": "深圳",
    "major_name": None,
    "group_code": None,
}
```

在 `validate_release_package()` 中追加：

```python
checks.append(_check_builtin_value_index())
```

新增 helper：

```python
def _check_builtin_value_index() -> ReleaseCheck:
    try:
        payload = json.loads(BUILTIN_VALUE_INDEX_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ReleaseCheck(
            "builtin_value_index",
            "fail",
            "内置 admissions schema/value index 不存在。",
        )
    except json.JSONDecodeError as exc:
        return ReleaseCheck(
            "builtin_value_index",
            "fail",
            "内置 admissions schema/value index 不是合法 JSON。",
            {"line": exc.lineno, "column": exc.colno},
        )

    fields = payload.get("fields") or {}
    missing: list[str] = []
    inactive: list[str] = []
    missing_values: list[dict[str, str]] = []
    for field_id, required_value in REQUIRED_BUILTIN_VALUE_FIELDS.items():
        field = fields.get(field_id)
        if not field:
            missing.append(field_id)
            continue
        if field.get("active") is not True:
            inactive.append(field_id)
        values = field.get("lookup_values") or []
        if required_value and required_value not in values:
            missing_values.append({"field_id": field_id, "value": required_value})

    ok = not (missing or inactive or missing_values)
    return ReleaseCheck(
        "builtin_value_index",
        "pass" if ok else "fail",
        "内置 admissions schema/value index 包含实体链接所需字段。"
        if ok
        else "内置 admissions schema/value index 缺少实体链接所需字段或值。",
        {
            "missing": missing,
            "inactive": inactive,
            "missing_values": missing_values,
        },
    )
```

运行：

```bash
.venv/bin/python scripts/validate_release_package.py --json-only
```

Expected before artifact regeneration: `builtin_value_index` fail。Expected after regeneration: pass。

---

## Task 2: 重新生成内置 admissions 数据产物

**Files:**
- Modify: `outputs/data/schema_value_index.json`
- Modify: `outputs/data/ingestion_summary.json`

- [ ] **Step 1: 重建 tracked data artifact**

运行：

```bash
.venv/bin/python scripts/build_data_warehouse.py
```

Expected output:

- JSON summary 打印成功。
- `outputs/data/schema_value_index.json` 包含 27 个字段左右。
- `fields.university_name.active == true`。
- `fields.university_name.lookup_values` 包含 `深圳大学`。

- [ ] **Step 2: 检查不要提交 DuckDB**

运行：

```bash
git status --short
```

Expected:

- `outputs/data/schema_value_index.json` modified。
- `outputs/data/ingestion_summary.json` modified。
- 不应出现 `outputs/data/guangdong_admissions.duckdb` staged 或 tracked 变更。

- [ ] **Step 3: 验证 live prompt**

运行：

```bash
.venv/bin/python -m unittest tests.test_builtin_value_index_artifact tests.test_workbench_value_entity_linking
```

Expected: pass。

---

## Task 3: uploaded llm_semantic 合并 UI 硬条件

**Files:**
- Modify: `src/api/workbench.py`
- Modify: `src/api/workbench_preflight.py`
- Modify: `tests/test_uploaded_dataset_flow.py`
- Modify: `tests/test_tool_server_endpoints.py`

- [ ] **Step 1: 写 query 级失败测试**

在 `tests/test_uploaded_dataset_flow.py` 新增测试，fake LLM 返回缺失 subject 的 `SemanticIntent`，但 query request 带硬条件：

```python
def test_uploaded_semantic_query_merges_hard_filters_into_intent_context(self) -> None:
    query = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
    fake_intent = _semantic_recommendation_intent()
    fake_intent["user_context"] = {
        "user_rank": None,
        "user_score": None,
        "source_province": None,
        "subject_type": None,
        "reselected_subjects": [],
    }
    fake_client = FakeSemanticIntentClient(
        [
            fake_intent,
            _evidence_requirements_for_basic_recommendation(),
            {"criteria": []},
        ]
    )

    with TemporaryDirectory() as directory:
        service, dataset_id = _queryable_uploaded_admissions(Path(directory), use_excel=False)
        with patch("src.api.workbench.deepseek_slot_adapter_enabled", return_value=True):
            with patch("src.api.workbench._interactive_deepseek_client", return_value=fake_client):
                response = service.query(
                    dataset_id,
                    user_input=query,
                    hard_filters={
                        "source_province": "广东",
                        "subject_type": "物理",
                        "reselected_subjects": ["化学", "生物"],
                        "user_rank": 15000,
                    },
                    soft_preferences={"prompt": query},
                    planner_mode="llm_semantic",
                    domain_name="admissions",
                )

    context = response["evidence_pack"]["semantic_intent"]["user_context"]
    self.assertEqual(context["source_province"], "广东")
    self.assertEqual(context["subject_type"], "物理")
    self.assertEqual(context["reselected_subjects"], ["化学", "生物"])
    self.assertEqual(context["user_rank"], 15000)
    warning_codes = {warning["code"] for warning in response["warnings"]}
    self.assertNotIn("subject_type_not_provided", warning_codes)
    self.assertNotIn("subject_requirement_not_provided", warning_codes)
```

运行：

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_uploaded_semantic_query_merges_hard_filters_into_intent_context
```

Expected before fix: fail。

- [ ] **Step 2: 写 preflight 级失败测试**

在 `tests/test_uploaded_dataset_flow.py` 的 preflight tests 附近新增：

```python
def test_uploaded_admissions_preflight_recognizes_structured_hard_filters(self) -> None:
    query = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
    fake_intent = _semantic_recommendation_intent()
    fake_intent["user_context"] = {
        "user_rank": None,
        "user_score": None,
        "source_province": None,
        "subject_type": None,
        "reselected_subjects": [],
    }
    fake_client = FakeSemanticIntentClient([fake_intent, _evidence_requirements_for_basic_recommendation()])

    with TemporaryDirectory() as directory:
        service, dataset_id = _queryable_uploaded_admissions(Path(directory), use_excel=False)
        with patch("src.api.workbench.deepseek_slot_adapter_enabled", return_value=True):
            with patch("src.api.workbench._interactive_deepseek_client", return_value=fake_client):
                response = service.preflight(
                    dataset_id,
                    user_input=query,
                    hard_filters={
                        "source_province": "广东",
                        "subject_type": "物理",
                        "reselected_subjects": ["化学", "生物"],
                        "user_rank": 15000,
                    },
                    soft_preferences={"prompt": query},
                    planner_mode="llm_semantic",
                    domain_name="admissions",
                )

    facts = {item["source"]: item for item in response["recognized_facts"]}
    self.assertEqual(facts["hard_filters.source_province"]["value"], "广东")
    self.assertEqual(facts["hard_filters.subject_type"]["value"], "物理")
    self.assertEqual(facts["hard_filters.reselected_subjects"]["value"], ["化学", "生物"])
    self.assertEqual(
        response["planner"]["semantic_intent"]["user_context"]["subject_type"],
        "物理",
    )
```

运行：

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_uploaded_admissions_preflight_recognizes_structured_hard_filters
```

Expected before fix: fail。

- [ ] **Step 3: 实现 intent merge helper**

在 `src/api/workbench.py` 中新增 helper，放在 semantic planner helper 附近：

```python
def _semantic_intent_with_hard_context(
    intent: SemanticIntent,
    config: WorkbenchConfig,
) -> SemanticIntent:
    hard = _execution_safe_structured_preferences(config.hard_filters)
    if not hard:
        return intent
    context = intent.user_context.model_dump()
    source_province = _clean_text(hard.get("source_province"))
    subject_type = _clean_text(hard.get("subject_type"))
    reselected_subjects = _clean_list(hard.get("reselected_subjects"))
    user_rank = _optional_int(hard.get("user_rank"))
    user_score = _optional_int(hard.get("user_score") or hard.get("score"))

    if source_province:
        context["source_province"] = source_province
    if subject_type:
        context["subject_type"] = subject_type
    if reselected_subjects:
        context["reselected_subjects"] = reselected_subjects
    if user_rank:
        context["user_rank"] = user_rank
    if user_score and not context.get("user_rank"):
        context["user_score"] = user_score

    return intent.model_copy(update={"user_context": context})
```

Then call it in `_semantic_planner_attempt()` after extraction:

```python
intent = _semantic_intent_with_hard_context(extraction.intent, config)
```

Use `intent` for `SemanticPlannerAttempt.intent`, planner `semantic_intent_query_type`, and later traces.

Also call it in `_supplied_semantic_intent_attempt()`:

```python
intent = _semantic_intent_with_hard_context(intent, config)
```

Keep this helper limited to `SemanticIntent.user_context`; do not append new preferences, do not generate SQL, and do not mark vague preferences executable.

- [ ] **Step 4: 扩展 preflight recognized facts**

Replace `_recognized_facts_from_inputs()` in `src/api/workbench_preflight.py` with a loop:

```python
def _recognized_facts_from_inputs(
    config: WorkbenchPreflightConfig,
) -> list[dict[str, Any]]:
    hard = config.hard_filters or {}
    fields = [
        ("user_rank", "全省排位"),
        ("source_province", "生源地"),
        ("subject_type", "科类"),
        ("reselected_subjects", "再选科目"),
    ]
    facts: list[dict[str, Any]] = []
    for field, label in fields:
        value = hard.get(field)
        if value in (None, "", []):
            continue
        facts.append(
            {
                "fact_id": confirmation_id(preflight_id(config), field, "fact"),
                "label": label,
                "value": value,
                "source": f"hard_filters.{field}",
                "executable": True,
            }
        )
    return facts
```

Because `_semantic_planner_attempt()` now returns merged intent, `response["planner"]["semantic_intent"]` and `_recognized_facts_from_intent()` will both see merged context. If this duplicates facts, add a local `_dedupe_facts()` helper keyed by `(label, value, source)` and prefer `hard_filters.*` source over `llm_semantic_intent.user_context`.

- [ ] **Step 5: HTTP endpoint regression**

In `tests/test_tool_server_endpoints.py::test_workbench_preflight_endpoint_returns_contract`, add assertions:

```python
facts = {item["source"]: item for item in payload["recognized_facts"]}
self.assertEqual(facts["hard_filters.subject_type"]["value"], "物理")
self.assertEqual(facts["hard_filters.reselected_subjects"]["value"], ["化学", "生物"])
```

In `test_workbench_query_accepts_current_preflight_reference`, after `assert_workbench_contract`, add:

```python
context = payload["evidence_pack"]["semantic_intent"]["user_context"]
self.assertEqual(context["subject_type"], "物理")
self.assertEqual(context["reselected_subjects"], ["化学", "生物"])
```

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow tests.test_tool_server_endpoints
```

Expected: pass。

---

## Task 4: 前端确认状态和重复未执行偏好归一化

**Files:**
- Modify: `frontend/src/utils/workbenchState.js`
- Modify: `frontend/src/utils/workbenchState.test.js`
- Modify: `frontend/src/utils/workbenchRunBar.js`
- Modify: `frontend/src/utils/workbenchRunBar.test.js`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/CandidateRerunPanel.vue`
- Modify: `frontend/src/components/BeginnerDecisionPanel.vue`

- [ ] **Step 1: 增加 frontend state helpers**

In `frontend/src/utils/workbenchState.js` add:

```js
export function candidateConfirmationSummary(runData) {
  const split = splitCandidateConfirmationState(runData);
  return {
    confirmableCount: split.confirmable.length,
    warningOnlyCount: split.blocked.length,
    hasConfirmable: split.confirmable.length > 0,
    hasWarningOnly: split.blocked.length > 0,
  };
}

function unusedPreferenceKey(item) {
  return [
    item?.id,
    item?.field_id,
    item?.source_text,
    item?.preference,
    item?.reason,
    item?.match_type,
  ].filter(Boolean).join('|');
}

export function uniqueUnusedPreferences(runData) {
  const items = [
    ...(Array.isArray(runData?.unexecuted_preferences) ? runData.unexecuted_preferences : []),
    ...(Array.isArray(runData?.not_executed_preferences) ? runData.not_executed_preferences : []),
    ...(Array.isArray(runData?.no_schema_field_preferences) ? runData.no_schema_field_preferences : []),
  ];
  const seen = new Set();
  return items.filter((item, index) => {
    const key = unusedPreferenceKey(item) || `unused-${index}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
```

- [ ] **Step 2: 写 helper 测试**

In `frontend/src/utils/workbenchState.test.js` add:

```js
import {
  candidateConfirmationSummary,
  uniqueUnusedPreferences,
} from './workbenchState.js';

test('candidateConfirmationSummary separates actionable and warning-only candidates', () => {
  const summary = candidateConfirmationSummary({
    candidates_to_confirm: [
      { candidate_id: 'cand_city', preference: '珠三角' },
      { preference: '中外合作', reason: '缺少字段' },
    ],
  });

  assert.deepEqual(summary, {
    confirmableCount: 1,
    warningOnlyCount: 1,
    hasConfirmable: true,
    hasWarningOnly: true,
  });
});

test('uniqueUnusedPreferences deduplicates repeated not executed preferences', () => {
  const unused = uniqueUnusedPreferences({
    not_executed_preferences: [
      { field_id: 'cooperation_type', source_text: '中外合作', reason: '缺少合作办学类型字段' },
      { field_id: 'cooperation_type', source_text: '中外合作', reason: '缺少合作办学类型字段' },
    ],
  });

  assert.equal(unused.length, 1);
});
```

Run:

```bash
cd frontend && npm run test:unit -- src/utils/workbenchState.test.js
```

Expected: pass after implementation。

- [ ] **Step 3: 修正 run bar status**

Update `frontend/src/utils/workbenchRunBar.js`:

```js
import { candidateConfirmationSummary } from './workbenchState.js';
```

Inside `normalizeRunBarStatus`, before `statusLabels` returns:

```js
if (runData.status === 'needs_confirmation') {
  const summary = candidateConfirmationSummary(runData);
  if (summary.hasConfirmable) {
    return { type: 'warning', label: '待确认' };
  }
  if (summary.hasWarningOnly) {
    return { type: 'info', label: '有提示' };
  }
  return { type: 'success', label: '已完成' };
}
```

Update `frontend/src/utils/workbenchRunBar.test.js` expected old test or add:

```js
test('normalizeRunBarStatus does not show actionable pending when only warning-only candidates exist', () => {
  assert.deepEqual(normalizeRunBarStatus({
    runData: {
      status: 'needs_confirmation',
      result_count: 14,
      candidates_to_confirm: [{ preference: '缺少 id' }],
    },
  }), { type: 'info', label: '有提示' });
});
```

Run:

```bash
cd frontend && npm run test:unit -- src/utils/workbenchRunBar.test.js
```

Expected: pass。

- [ ] **Step 4: quick stats 使用归一化数量**

In `frontend/src/App.vue` import helpers:

```js
import {
  candidateConfirmationSummary,
  uniqueUnusedPreferences,
} from './utils/workbenchState';
```

Change `quickStats`:

```js
const confirmation = candidateConfirmationSummary(data);
const unused = uniqueUnusedPreferences(data);
return [
  ...
  { label: '可确认', value: confirmation.confirmableCount, tone: 'needs_confirmation' },
  { label: '仅提示', value: confirmation.warningOnlyCount, tone: 'info' },
  { label: '未参与', value: unused.length, tone: 'blocked' },
];
```

- [ ] **Step 5: 主面板只把可确认项放在“还要你确认”**

In `frontend/src/components/BeginnerDecisionPanel.vue`:

- Import `splitCandidateConfirmationState` and `uniqueUnusedPreferences`。
- `confirmItems` should be `splitCandidateConfirmationState(props.runData).confirmable`。
- Add `warningOnlyCandidates` computed from `.blocked`。
- `unusedItems` should include `uniqueUnusedPreferences(props.runData)` plus `warningOnlyCandidates` only if they are not already represented by unused preferences。
- Empty state should check `unusedItems.length` rather than only `runData.not_executed_preferences.length`。

Expected visible behavior:

- 有 `candidate_id`：显示在“还要你确认”。
- 无 `candidate_id`：不显示为可确认，显示为“仅提示”或“没有参与筛选”。

- [ ] **Step 6: CandidateRerunPanel copy**

In `frontend/src/components/CandidateRerunPanel.vue`:

- Header `h2` becomes conditional:

```vue
<h2>{{ selectableCandidates.length ? '可确认条件' : '仅提示' }}</h2>
```

- Header copy when no selectable candidates:

```js
const panelCopy = computed(() => {
  if (selectableCandidates.value.length) {
    return props.canConfirm ? '只提交后端生成的 candidate_id。' : props.disabledReason;
  }
  return '这些条件没有系统生成的 candidate_id，不会被前端提交确认。';
});
```

Use `panelCopy` in template。

- [ ] **Step 7: frontend unit and build**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: both pass。

---

## Task 5: LLM 用量展示可解释

**Files:**
- Modify: `frontend/src/components/TokenUsagePanel.vue`
- Modify: `frontend/src/utils/workbenchState.test.js` or create `frontend/src/utils/tokenUsage.test.js` if helper is extracted.
- Modify: `frontend/README.md`

- [ ] **Step 1: 提取 usage section state**

Prefer extracting pure helper to `frontend/src/utils/workbenchState.js` or a new `frontend/src/utils/tokenUsage.js`:

```js
export function tokenUsageSectionState(tokenUsage, key) {
  const usage = tokenUsage?.[key];
  if (!usage) return { status: 'not_returned', label: '未返回用量' };
  const hasPositiveValue = Object.values(usage).some((value) => Number(value) > 0);
  return hasPositiveValue
    ? { status: 'has_usage', label: '已返回用量' }
    : { status: 'zero_usage', label: '未发生调用' };
}
```

Write tests:

```js
test('tokenUsageSectionState distinguishes missing section from zero usage', () => {
  assert.equal(tokenUsageSectionState(null, 'extractor').label, '未返回用量');
  assert.equal(tokenUsageSectionState({ extractor: { total_tokens: 0 } }, 'extractor').label, '未发生调用');
  assert.equal(tokenUsageSectionState({ extractor: { total_tokens: 7 } }, 'extractor').label, '已返回用量');
});
```

- [ ] **Step 2: TokenUsagePanel 不再渲染空 dl**

Update each section in `TokenUsagePanel.vue`:

- Section header includes a small `el-tag` from `tokenUsageSectionState(tokenUsage, section[0])`。
- If usage missing, show `el-empty` or `p` copy: `本段没有返回 token usage。`
- If usage exists but all zero, show `本段未发生模型调用。`
- Only render `dl` when `status === 'has_usage'`。

Keep all visible copy Chinese。

- [ ] **Step 3: README 说明**

In `frontend/README.md`, add:

```md
模型用量按 `extractor`、`generator` 和 `total` 分段展示。某一段显示“未返回用量”表示后端响应没有该段 usage；显示“未发生调用”表示该段明确为 0；只有“已返回用量”才代表实际模型调用并返回 token 统计。
```

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: pass。

---

## Task 6: 文档同步和排障指南

**Files:**
- Modify: `README.md`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`
- Modify: `docs/troubleshooting.md`
- Modify: `frontend/README.md`

- [ ] **Step 1: README 更新 live artifact 要求**

In `README.md` around data warehouse / value entity linker sections, add:

```md
内置 admissions 的 value entity linker 依赖 tracked `outputs/data/schema_value_index.json`。该文件必须由当前 schema 和源 Excel 重建，至少包含 `university_name`、`city`、`major_name`、`group_code` 等已审查字段；如果它缺少 `university_name`，`深圳大学` 这类完整院校实体会退化成城市子串，必须先运行 `.venv/bin/python scripts/build_data_warehouse.py` 并通过 release check。
```

- [ ] **Step 2: API contract 更新 hard filters 合并规则**

In `docs/api_contract.md` preflight section, add:

```md
`hard_filters.source_province`、`hard_filters.subject_type`、`hard_filters.reselected_subjects` 和 `hard_filters.user_rank` 是用户在 UI 中明确提交的结构化事实。uploaded admissions 的 `llm_semantic` planner 即使返回空 `user_context`，Workbench 也必须在 evidence gate 前把这些字段合并进 `SemanticIntent.user_context`。LLM 不能用空值覆盖 UI 硬条件。
```

- [ ] **Step 3: methodology 更新**

In `docs/methodology_report.md` value entity linker paragraph, append:

```md
为避免“单测临时 warehouse 通过但 live artifact 落后”，release check 还会检查 tracked `outputs/data/schema_value_index.json` 是否包含实体链接必须字段和值，例如 `university_name` 中的 `深圳大学`。
```

In uploaded admissions section, append:

```md
uploaded admissions 的 LLM semantic path 会在 evidence gate 前把 UI hard filters 合并回 `SemanticIntent.user_context`，因此科类、再选科目、生源地和排位不会因为 LLM 抽取为空而丢失。
```

- [ ] **Step 4: troubleshooting 更新**

In `docs/troubleshooting.md`, add a symptom:

```md
## “深圳大学”被当成“深圳的大学”

检查 `outputs/data/schema_value_index.json` 是否包含 `fields.university_name.lookup_values`，并确认其中有 `深圳大学`。如果缺失，运行：

```bash
.venv/bin/python scripts/build_data_warehouse.py
.venv/bin/python scripts/validate_release_package.py --json-only
```

不要通过新增城市或学校名称 hardcode 修复；应重建 reviewed schema/value index。
```

- [ ] **Step 5: 文档搜索**

Run:

```bash
rg -n "深圳大学|schema_value_index|hard_filters|模型用量|candidate_id" README.md docs frontend/README.md
```

Expected: no stale text claiming UI can confirm candidates without `candidate_id`; no text implying LLM can override hard filters。

---

## Task 7: 端到端验证和真实浏览器 QA

**Files:**
- No mandatory source changes unless verification finds new bugs.

- [ ] **Step 1: Backend focused tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_builtin_value_index_artifact \
  tests.test_data_warehouse \
  tests.test_workbench_value_entity_linking \
  tests.test_uploaded_dataset_flow \
  tests.test_tool_server_endpoints
```

Expected: pass。

- [ ] **Step 2: Full backend tests**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: pass。

- [ ] **Step 3: Frontend tests and build**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: pass。

- [ ] **Step 4: Release check**

Run:

```bash
.venv/bin/python scripts/validate_release_package.py --json-only
```

Expected:

- Top-level `status` is `pass`。
- Check `builtin_value_index` is `pass`。

- [ ] **Step 5: Start services for manual QA**

Use dev auth token map without printing secrets:

```bash
AUTH_TOKENS_JSON='{"operator-token":{"actor_id":"operator","permission_scopes":["read_only","query","confirm","dataset_write","review_admin","warehouse_admin","diagnostics"]},"agent-token":{"actor_id":"agent","permission_scopes":["read_only","query","confirm"]}}' \
ENABLE_LLM=true \
.venv/bin/python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8001 --log-level info
```

In another shell:

```bash
cd frontend && npm run dev
```

Expected: backend `http://127.0.0.1:8001/healthz` OK, frontend `http://127.0.0.1:5173/` loads。

- [ ] **Step 6: Browser scenarios**

Use in-app browser or Playwright-equivalent operations:

1. Built-in prompt: `我想进深圳大学，目前排位15000，帮我看看有什么专业可以选`
   - Expected: evidence executed filter contains `院校名称 = 深圳大学`。
   - Expected: no `城市 in_contains 深圳` executed filter for this prompt。
   - Expected: top results all have `university_name === "深圳大学"`。
2. Built-in prompt: `我想去深圳的大学，目前排位15000，帮我看看有什么专业可以选`
   - Expected: executed filter contains `城市 in_contains 深圳`。
   - Expected: no `院校名称 = 深圳大学` hard filter。
3. Built-in prompt: `我想找深圳大学附近的学校，目前排位15000`
   - Expected: no city/university SQL filter; evidence records boundary not executed。
4. Uploaded admissions API flow using `sample_data/admissions_minimal.csv`
   - Upload, generate `admissions_schema_v1`, approve, build warehouse, preflight, query。
   - Expected: preflight recognized facts include `hard_filters.subject_type` and `hard_filters.reselected_subjects`。
   - Expected: query warnings do not include missing subject warnings when hard filters are provided。
5. Frontend candidate display:
   - Run a case with warning-only candidates.
   - Expected: run bar says `有提示` or completed state, not actionable `待确认` unless a `candidate_id` exists。
   - Expected: no confirm button is shown for missing `candidate_id` items。
6. Token usage display:
   - Enable LLM extractor/generator.
   - Expected: each section shows `已返回用量` / `未返回用量` / `未发生调用` explicitly。

- [ ] **Step 7: Capture QA notes**

If browser upload still cannot be exercised via the current tool, record in final verification:

```text
Browser tool limitation: current in-app Browser automation did not expose file chooser / setInputFiles, so upload UI was verified through backend API flow and static UI state, not a real file chooser interaction.
```

If mobile viewport tool still times out, record:

```text
Browser tool limitation: mobile viewport reset timed out; frontend unit/build passed, but live mobile screenshot was not captured in this run.
```

---

## Final Verification Commands

Run all before completion:

```bash
.venv/bin/python -m unittest discover -s tests
cd frontend && npm run test:unit
cd frontend && npm run build
.venv/bin/python scripts/validate_release_package.py --json-only
```

Expected:

- Python tests pass。
- Frontend unit tests pass。
- Frontend build pass。
- Release package validation pass and includes `builtin_value_index: pass`。
- Browser QA scenarios above match expected evidence and UI states。

---

## Commit Scope

Stage only files changed by this quest:

```bash
git add \
  outputs/data/schema_value_index.json \
  outputs/data/ingestion_summary.json \
  scripts/validate_release_package.py \
  tests/test_data_warehouse.py \
  tests/test_builtin_value_index_artifact.py \
  tests/test_workbench_value_entity_linking.py \
  src/api/workbench.py \
  src/api/workbench_preflight.py \
  tests/test_uploaded_dataset_flow.py \
  tests/test_tool_server_endpoints.py \
  frontend/src/utils/workbenchState.js \
  frontend/src/utils/workbenchState.test.js \
  frontend/src/utils/workbenchRunBar.js \
  frontend/src/utils/workbenchRunBar.test.js \
  frontend/src/App.vue \
  frontend/src/components/CandidateRerunPanel.vue \
  frontend/src/components/BeginnerDecisionPanel.vue \
  frontend/src/components/TokenUsagePanel.vue \
  frontend/src/components/workspaces/QueryWorkspace.vue \
  README.md \
  docs/api_contract.md \
  docs/methodology_report.md \
  docs/troubleshooting.md \
  frontend/README.md
```

Suggested commit message:

```text
fix: harden qa findings for admissions workbench
```

Do not stage:

- `.env`
- `.venv`
- `outputs/data/guangdong_admissions.duckdb`
- temporary screenshots
- local browser cache or Playwright traces unless deliberately added as reviewed evidence.
