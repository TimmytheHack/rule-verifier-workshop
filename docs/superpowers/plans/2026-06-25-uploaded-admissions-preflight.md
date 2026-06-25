# Uploaded Admissions Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 uploaded admissions 主查询增加查询前检查：先展示可执行事实、需确认边界、不可执行偏好和缺失信息，再允许正式查询。

**Architecture:** 后端新增 preflight engine 和 HTTP endpoint，只复用 LLM semantic intent、EvidenceRequirementGate、reviewed schema/value evidence，不执行 SQL、不返回结果行。HTTP 层用短期 `preflight_id` 缓存锁住输入和后端生成的确认项；正式查询只能引用当前 preflight 中的确认项。前端只在 uploaded admissions 数据源启用两阶段门禁，内置 admissions 保持现状。

**Tech Stack:** Python `unittest`、FastAPI、Pydantic、现有 `DatasetService` / `WorkbenchConfig` / semantic planner、Vue 3、Vite、Element Plus、Node `node:test`。

---

## Scope Check

本 spec 横跨后端 contract 和前端展示，但两部分必须一起交付才能形成真正的查询前门禁，因此使用一个实施计划。任务顺序保证每一步都能独立测试：先实现后端 preflight 输出，再实现 HTTP preflight 与确认验证，最后接前端。

## File Structure

- Create `src/api/workbench_preflight.py`：查询前检查核心逻辑；输入 uploaded admissions query，输出四类前端可展示条目；不执行 SQL。
- Create `src/api/preflight_store.py`：HTTP 层短期保存 `preflight_id`、输入签名和后端生成的确认项，用于正式查询前校验。
- Modify `src/api/dataset_service.py`：新增 `preflight()`，复用 uploaded dataset 的 domain path / warehouse path 解析。
- Modify `src/api/server.py`：新增 `WorkbenchPreflightRequest`、`PreflightBoundarySelection`、`POST /workbench/preflight`，并在 `/workbench/query` 验证 preflight confirmations。
- Modify `tests/test_uploaded_dataset_flow.py`：覆盖 DatasetService preflight 分类、不可执行偏好、缺失信息、非 uploaded admissions 拒绝。
- Modify `tests/test_tool_server_endpoints.py`：覆盖 HTTP preflight 权限、query 引用当前 preflight、伪造确认项拒绝、内置 admissions 不需要 preflight。
- Modify `frontend/src/utils/workbenchRequests.js`：新增 preflight 请求构造和基于 preflight 的正式查询请求构造。
- Modify `frontend/src/utils/workbenchState.js`：新增 preflight 状态、确认项拆分、是否可正式查询、输入签名检查。
- Modify `frontend/src/utils/workbenchState.test.js`：覆盖 preflight utility 行为。
- Create `frontend/src/components/PreflightPanel.vue`：展示 `查询前检查` 四类内容和受控边界确认。
- Modify `frontend/src/components/WorkbenchRunBar.vue`：主按钮支持 uploaded admissions 下的 `先做预检` / `确认后查询` 文案。
- Modify `frontend/src/App.vue`：接入 preflight 状态机，uploaded admissions 两阶段查询，输入变化清空旧 preflight。
- Modify `frontend/src/style.css`：补充 preflight 面板、执行资格条和移动端布局。
- Modify `docs/api_contract.md`、`frontend/README.md`：同步查询前检查 contract 和中文用户文案。

---

### Task 1: 后端 preflight contract 和 DatasetService 入口

**Files:**
- Create: `src/api/workbench_preflight.py`
- Modify: `src/api/dataset_service.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 写失败测试：uploaded admissions preflight 返回四类空壳 contract**

在 `tests/test_uploaded_dataset_flow.py` 的 `UploadedSemanticAdmissionsFlowTest` 中添加：

```python
    def test_uploaded_admissions_preflight_returns_contract(self) -> None:
        query = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            response = service.preflight(
                dataset_id,
                user_input=query,
                hard_filters={"user_rank": 15000},
                soft_preferences={"prompt": query},
                planner_mode="llm_semantic",
                domain_name="admissions",
            )

        self.assertEqual(response["schema_version"], "workbench_preflight.v1")
        self.assertEqual(response["dataset_id"], dataset_id)
        self.assertEqual(response["domain_name"], "admissions")
        self.assertIn(response["status"], {"ready", "needs_confirmation"})
        self.assertIn("preflight_id", response)
        self.assertIsInstance(response["recognized_facts"], list)
        self.assertIsInstance(response["boundary_confirmations"], list)
        self.assertIsInstance(response["not_executable_preferences"], list)
        self.assertIsInstance(response["missing_requirements"], list)
        self.assertIn("planner", response)
        self.assertEqual(response["result_count"], 0)
        self.assertEqual(response["items"], [])
        self.assertEqual(response["top_results"], [])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_returns_contract
```

Expected: FAIL，错误包含 `AttributeError: 'DatasetService' object has no attribute 'preflight'`。

- [ ] **Step 3: 创建 `workbench_preflight.py` 的基础 contract**

创建 `src/api/workbench_preflight.py`：

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from src.api.workbench import WorkbenchConfig
from src.domains import DomainConfig


PREFLIGHT_SCHEMA_VERSION = "workbench_preflight.v1"
PREFLIGHT_STATUS_VALUES = {"ready", "needs_confirmation", "blocked", "error"}


@dataclass(frozen=True)
class WorkbenchPreflightConfig:
    user_input: str
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    model: str = "deepseek-v4-flash"
    planner_mode: str = "llm_semantic"
    domain_name: str = "admissions"
    domain_path: str | None = None
    dataset_id: str | None = None


def run_workbench_preflight(
    config: WorkbenchPreflightConfig,
    *,
    domain_config: DomainConfig,
) -> dict[str, Any]:
    if not config.dataset_id:
        return _blocked_response(
            config,
            reason="查询前检查只支持上传表格数据源。",
        )
    if config.domain_name != "admissions" or domain_config.domain_id != "admissions":
        return _blocked_response(
            config,
            reason="查询前检查第一版只支持 uploaded admissions。",
        )
    if domain_config.pack_status != "approved":
        return _blocked_response(
            config,
            reason="上传表格尚未完成字段审查和批准。",
        )
    response = _base_response(config)
    response["recognized_facts"] = _recognized_facts_from_inputs(config)
    response["missing_requirements"] = _missing_requirements(config)
    response["status"] = (
        "needs_confirmation"
        if response["missing_requirements"] or response["boundary_confirmations"]
        else "ready"
    )
    return response


def workbench_config_from_preflight(
    config: WorkbenchPreflightConfig,
) -> WorkbenchConfig:
    return WorkbenchConfig(
        user_input=config.user_input,
        hard_filters=dict(config.hard_filters),
        soft_preferences=dict(config.soft_preferences),
        model=config.model,
        planner_mode=config.planner_mode,
        domain_name=config.domain_name,
        domain_path=config.domain_path,
        dataset_id=config.dataset_id,
    )


def preflight_input_signature(config: WorkbenchPreflightConfig) -> str:
    payload = {
        "dataset_id": config.dataset_id,
        "domain_name": config.domain_name,
        "domain_path": config.domain_path,
        "user_input": config.user_input,
        "hard_filters": config.hard_filters,
        "soft_preferences": config.soft_preferences,
        "planner_mode": config.planner_mode,
        "model": config.model,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def preflight_id(config: WorkbenchPreflightConfig) -> str:
    return f"pf_{preflight_input_signature(config)[:20]}"


def confirmation_id(preflight: str, source_text: str, kind: str) -> str:
    raw = f"{preflight}|{source_text}|{kind}"
    return f"pfc_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _base_response(config: WorkbenchPreflightConfig) -> dict[str, Any]:
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "status": "ready",
        "preflight_id": preflight_id(config),
        "input_signature": preflight_input_signature(config),
        "dataset_id": config.dataset_id,
        "domain_name": config.domain_name,
        "recognized_facts": [],
        "boundary_confirmations": [],
        "not_executable_preferences": [],
        "missing_requirements": [],
        "planner": {
            "status": "not_called",
            "semantic_intent": {},
            "evidence_requirements": {"status": "not_applicable"},
        },
        "warnings": [],
        "result_count": 0,
        "items": [],
        "top_results": [],
    }


def _blocked_response(config: WorkbenchPreflightConfig, *, reason: str) -> dict[str, Any]:
    response = _base_response(config)
    response["status"] = "blocked"
    response["missing_requirements"] = [
        {
            "requirement_id": confirmation_id(response["preflight_id"], reason, "blocked"),
            "label": "数据源状态",
            "message": reason,
            "blocking": True,
        }
    ]
    return response


def _recognized_facts_from_inputs(
    config: WorkbenchPreflightConfig,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    hard = config.hard_filters or {}
    if hard.get("user_rank"):
        facts.append(
            {
                "fact_id": confirmation_id(preflight_id(config), "user_rank", "fact"),
                "label": "全省排位",
                "source_text": str(hard["user_rank"]),
                "field": "user_rank",
                "value": hard["user_rank"],
                "message": "可以进入验证链路。",
            }
        )
    for key, label in [
        ("subject_type", "科类"),
        ("source_province", "生源地"),
        ("reselected_subjects", "再选科目"),
    ]:
        if hard.get(key):
            facts.append(
                {
                    "fact_id": confirmation_id(preflight_id(config), key, "fact"),
                    "label": label,
                    "source_text": str(hard[key]),
                    "field": key,
                    "value": hard[key],
                    "message": "可以进入验证链路。",
                }
            )
    return facts


def _missing_requirements(config: WorkbenchPreflightConfig) -> list[dict[str, Any]]:
    hard = config.hard_filters or {}
    missing: list[dict[str, Any]] = []
    if not hard.get("user_rank"):
        missing.append(_missing(config, "user_rank", "全省排位", "请补充全省排位。"))
    if not hard.get("subject_type"):
        missing.append(_missing(config, "subject_type", "科类", "请补充物理或历史科类。"))
    if not hard.get("reselected_subjects"):
        missing.append(
            _missing(config, "reselected_subjects", "再选科目", "请补充再选科目。")
        )
    return missing


def _missing(
    config: WorkbenchPreflightConfig,
    field: str,
    label: str,
    message: str,
) -> dict[str, Any]:
    return {
        "requirement_id": confirmation_id(preflight_id(config), field, "missing"),
        "field": field,
        "label": label,
        "message": message,
        "blocking": True,
    }
```

- [ ] **Step 4: 在 `DatasetService` 增加 preflight 入口**

在 `src/api/dataset_service.py` import：

```python
from src.api.workbench_preflight import WorkbenchPreflightConfig, run_workbench_preflight
```

在 `DatasetService` 中 `query()` 附近新增：

```python
    def preflight(
        self,
        dataset_id: str,
        *,
        user_input: str,
        hard_filters: dict[str, Any] | None = None,
        soft_preferences: dict[str, Any] | None = None,
        model: str = "deepseek-v4-flash",
        planner_mode: str = "llm_semantic",
        domain_name: str = "admissions",
    ) -> dict[str, Any]:
        """对 uploaded admissions 运行查询前检查，不执行 SQL。"""

        metadata = self._load_metadata(dataset_id)
        domain = self._domain_config_from_metadata(metadata)
        if domain_name != domain.domain_id:
            raise DatasetServiceError(
                code="domain_mismatch",
                message="请求 domain_name 与 uploaded domain pack 不一致。",
                status_code=400,
            )
        config = WorkbenchPreflightConfig(
            user_input=user_input,
            hard_filters=dict(hard_filters or {}),
            soft_preferences=dict(soft_preferences or {}),
            model=model,
            planner_mode=planner_mode,
            domain_name=domain_name,
            domain_path=str(metadata["domain_dir"]),
            dataset_id=dataset_id,
        )
        return run_workbench_preflight(config, domain_config=domain)
```

- [ ] **Step 5: 运行 focused test**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_returns_contract
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add src/api/workbench_preflight.py src/api/dataset_service.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: add uploaded admissions preflight contract"
```

---

### Task 2: 接入 LLM semantic intent 和 EvidenceRequirementGate，不执行 SQL

**Files:**
- Modify: `src/api/workbench_preflight.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 写失败测试：preflight 把 external evidence 偏好放入不会参与筛选**

在 `UploadedSemanticAdmissionsFlowTest` 中添加：

```python
    def test_uploaded_admissions_preflight_excludes_external_preferences(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，好就业，学校好一点，想留在广东省"
        fake_client = FakeSemanticIntentClient(
            [
                _semantic_recommendation_intent(),
                {
                    "requirements": [
                        {
                            "source_text": "想读人工智能，计算机",
                            "requirement_type": "table_field",
                            "candidate_semantic": "major_name",
                            "reason": "专业名称字段可审核。",
                        },
                        {
                            "source_text": "好就业",
                            "requirement_type": "knowledge_base_or_reviewed_field",
                            "candidate_semantic": "employment_outcome",
                            "reason": "就业需要已审核知识库或字段。",
                        },
                        {
                            "source_text": "学校好一点",
                            "requirement_type": "reviewed_ranking_policy",
                            "candidate_semantic": "school_quality",
                            "reason": "学校质量需要已审核排序策略。",
                        },
                    ]
                },
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

        self.assertEqual(response["status"], "ready")
        self.assertEqual(len(fake_client.calls), 2)
        blocked_text = [
            item["source_text"] for item in response["not_executable_preferences"]
        ]
        self.assertIn("好就业", blocked_text)
        self.assertIn("学校好一点", blocked_text)
        self.assertEqual(response["planner"]["evidence_requirements"]["status"], "classified")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn('"sql"', serialized.lower())
        self.assertEqual(response["items"], [])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_excludes_external_preferences
```

Expected: FAIL，`not_executable_preferences` 为空或 fake client 未被调用。

- [ ] **Step 3: 在 preflight engine 复用 workbench semantic planner**

修改 `src/api/workbench_preflight.py` imports：

```python
from src.api import workbench as workbench_module
from src.api.workbench import WorkbenchConfig
```

在 `run_workbench_preflight()` 的 approved uploaded admissions 分支中，在 `_base_response(config)` 后调用：

```python
    workbench_config = workbench_config_from_preflight(config)
    planner_attempt = workbench_module._semantic_planner_attempt(
        workbench_config,
        domain_config,
    )
    response["planner"] = {
        "status": planner_attempt.planner.get("status", "planned"),
        **planner_attempt.planner,
        "semantic_intent": (
            planner_attempt.intent.model_dump()
            if planner_attempt.intent is not None
            else {}
        ),
    }
    if planner_attempt.intent is not None:
        response["recognized_facts"].extend(
            _recognized_facts_from_intent(config, planner_attempt.intent.model_dump())
        )
        gate_attempt = workbench_module._semantic_evidence_requirement_gate_attempt(
            workbench_config,
            domain_config,
            planner_attempt.intent,
            planner_attempt.planner,
        )
        if gate_attempt.planner:
            response["planner"]["evidence_requirements"] = gate_attempt.planner
        response["not_executable_preferences"].extend(
            _not_executable_preferences(config, gate_attempt.not_executed_preferences)
        )
        response["boundary_confirmations"].extend(
            _boundary_confirmations(config, gate_attempt.not_executed_preferences)
        )
```

新增 helper：

```python
def _recognized_facts_from_intent(
    config: WorkbenchPreflightConfig,
    intent_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    context = intent_payload.get("user_context") or {}
    facts: list[dict[str, Any]] = []
    for field, label in [
        ("user_rank", "全省排位"),
        ("source_province", "生源地"),
        ("subject_type", "科类"),
        ("reselected_subjects", "再选科目"),
    ]:
        value = context.get(field)
        if value not in (None, "", []):
            facts.append(
                {
                    "fact_id": confirmation_id(preflight_id(config), field, "intent_fact"),
                    "label": label,
                    "source_text": str(value),
                    "field": field,
                    "value": value,
                    "message": "LLM 识别为用户事实，仍需后续 verifier 检查。",
                }
            )
    return facts


def _not_executable_preferences(
    config: WorkbenchPreflightConfig,
    preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for item in preferences:
        requirement_type = str(item.get("requirement_type") or item.get("type") or "")
        if requirement_type == "user_boundary":
            continue
        source_text = str(item.get("source_text") or item.get("preference") or "")
        blocked.append(
            {
                "preference_id": confirmation_id(
                    preflight_id(config),
                    source_text,
                    "not_executable",
                ),
                "source_text": source_text,
                "label": source_text or "未命名偏好",
                "requirement_type": requirement_type,
                "candidate_semantic": item.get("candidate_semantic") or item.get("field_id"),
                "reason": _user_facing_requirement_reason(requirement_type, item),
                "treatment": "不会参与筛选或排序。",
            }
        )
    return blocked


def _user_facing_requirement_reason(
    requirement_type: str,
    item: dict[str, Any],
) -> str:
    if requirement_type == "knowledge_base_or_reviewed_field":
        return "需要已审核知识库或已审核字段。"
    if requirement_type == "reviewed_ranking_policy":
        return "需要已审核排序策略。"
    if requirement_type == "unsupported":
        return "当前系统不支持执行该偏好。"
    return str(item.get("reason") or "当前没有可审核证据支持。")
```

- [ ] **Step 4: 对 user_boundary 生成受控确认项**

在 `src/api/workbench_preflight.py` 新增：

```python
def _boundary_confirmations(
    config: WorkbenchPreflightConfig,
    preferences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    confirmations: list[dict[str, Any]] = []
    current_preflight_id = preflight_id(config)
    for item in preferences:
        if str(item.get("requirement_type") or item.get("type") or "") != "user_boundary":
            continue
        source_text = str(item.get("source_text") or item.get("preference") or "")
        options = _boundary_options(config, source_text, item)
        confirmations.append(
            {
                "confirmation_id": confirmation_id(
                    current_preflight_id,
                    source_text,
                    "boundary",
                ),
                "source_text": source_text,
                "label": source_text or "需要确认的边界",
                "reason": str(item.get("reason") or "需要用户确认边界后才能执行。"),
                "requirement_type": "user_boundary",
                "options": options,
                "default_option_id": options[0]["option_id"] if options else None,
            }
        )
    return confirmations


def _boundary_options(
    config: WorkbenchPreflightConfig,
    source_text: str,
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    text = source_text or str(item.get("candidate_semantic") or "")
    if any(term in text for term in ("稳", "保底", "冲")):
        return [
            {
                "option_id": "rank_window_reach",
                "label": "冲一冲",
                "value": "reach",
                "query_patch": {
                    "soft_preferences": {
                        "rank_window_label": "冲一冲",
                        "rank_window_lower_percent": 0,
                        "rank_window_upper_percent": 0,
                    }
                },
            },
            {
                "option_id": "rank_window_steady",
                "label": "稳一点",
                "value": "steady",
                "query_patch": {
                    "soft_preferences": {
                        "rank_window_label": "稳一点",
                        "rank_window_lower_percent": 0,
                        "rank_window_upper_percent": 15,
                    }
                },
            },
            {
                "option_id": "rank_window_safe",
                "label": "保底",
                "value": "safe",
                "query_patch": {
                    "soft_preferences": {
                        "rank_window_label": "保底",
                        "rank_window_lower_percent": 0,
                        "rank_window_upper_percent": 50,
                    }
                },
            },
            _disabled_boundary_option(),
        ]
    return [_disabled_boundary_option()]


def _disabled_boundary_option() -> dict[str, Any]:
    return {
        "option_id": "do_not_use",
        "label": "暂不使用",
        "value": None,
        "query_patch": {},
        "disabled_boundary": True,
    }
```

- [ ] **Step 5: 补 user_boundary focused test**

在 `UploadedSemanticAdmissionsFlowTest` 中添加：

```python
    def test_uploaded_admissions_preflight_requires_user_boundary_confirmation(self) -> None:
        query = "我的排位是15000，想读人工智能，稳一点"
        fake_client = FakeSemanticIntentClient(
            [
                _semantic_recommendation_intent(),
                {
                    "requirements": [
                        {
                            "source_text": "稳一点",
                            "requirement_type": "user_boundary",
                            "candidate_semantic": "rank_window",
                            "reason": "稳一点需要用户确认位次窗口。",
                        }
                    ]
                },
            ],
        )
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )
            with patch("src.api.workbench.deepseek_slot_adapter_enabled", return_value=True):
                with patch(
                    "src.api.workbench._interactive_deepseek_client",
                    return_value=fake_client,
                ):
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

        self.assertEqual(response["status"], "needs_confirmation")
        self.assertEqual(response["boundary_confirmations"][0]["source_text"], "稳一点")
        option_labels = [
            option["label"] for option in response["boundary_confirmations"][0]["options"]
        ]
        self.assertEqual(option_labels, ["冲一冲", "稳一点", "保底", "暂不使用"])
        self.assertEqual(response["result_count"], 0)
```

- [ ] **Step 6: 运行 semantic preflight tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_excludes_external_preferences \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_requires_user_boundary_confirmation
```

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add src/api/workbench_preflight.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: classify uploaded admissions preflight evidence"
```

---

### Task 3: HTTP `/workbench/preflight` endpoint 和 preflight store

**Files:**
- Create: `src/api/preflight_store.py`
- Modify: `src/api/server.py`
- Test: `tests/test_tool_server_endpoints.py`

- [ ] **Step 1: 写失败测试：HTTP endpoint 返回 preflight contract**

在 `tests/test_tool_server_endpoints.py` 中添加 imports：

```python
from src.api.dataset_service import DatasetService
from tests.test_uploaded_dataset_flow import _queryable_uploaded_admissions
```

在 `ToolServerEndpointsTest` 中添加：

```python
    def test_workbench_preflight_endpoint_returns_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            service, dataset_id = _queryable_uploaded_admissions(root, use_excel=False)
            with patch.object(server_module, "dataset_service", service):
                response = self.client.post(
                    "/workbench/preflight",
                    headers=_auth_headers("query-token"),
                    json={
                        "dataset_id": dataset_id,
                        "domain_name": "admissions",
                        "user_input": "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选",
                        "hard_filters": {
                            "source_province": "广东",
                            "subject_type": "物理",
                            "reselected_subjects": ["化学", "生物"],
                            "user_rank": 15000,
                        },
                        "soft_preferences": {
                            "prompt": "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
                        },
                        "planner_mode": "llm_semantic",
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["schema_version"], "workbench_preflight.v1")
        self.assertEqual(payload["dataset_id"], dataset_id)
        self.assertEqual(payload["items"], [])
        self.assertNotIn("sql", json.dumps(payload, ensure_ascii=False).lower())
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_preflight_endpoint_returns_contract
```

Expected: FAIL，HTTP status `404`。

- [ ] **Step 3: 创建 preflight store**

创建 `src/api/preflight_store.py`：

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StoredPreflight:
    preflight_id: str
    input_signature: str
    dataset_id: str
    domain_name: str
    boundary_confirmations: list[dict[str, Any]]
    created_at: float


class PreflightStore:
    def __init__(self, *, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, StoredPreflight] = {}

    def put(self, response: dict[str, Any]) -> None:
        preflight_id = str(response["preflight_id"])
        self._items[preflight_id] = StoredPreflight(
            preflight_id=preflight_id,
            input_signature=str(response["input_signature"]),
            dataset_id=str(response.get("dataset_id") or ""),
            domain_name=str(response.get("domain_name") or ""),
            boundary_confirmations=list(response.get("boundary_confirmations") or []),
            created_at=time.time(),
        )

    def get(self, preflight_id: str) -> StoredPreflight | None:
        item = self._items.get(preflight_id)
        if item is None:
            return None
        if time.time() - item.created_at > self.ttl_seconds:
            self._items.pop(preflight_id, None)
            return None
        return item

    def clear(self) -> None:
        self._items.clear()
```

- [ ] **Step 4: 在 server 增加 request models 和 endpoint**

修改 `src/api/server.py` imports：

```python
from src.api.preflight_store import PreflightStore
```

新增 Pydantic models：

```python
class WorkbenchPreflightRequest(BaseModel):
    """uploaded admissions 查询前检查请求。"""

    dataset_id: str
    domain_name: str = "admissions"
    user_input: str = Field(min_length=1)
    hard_filters: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)
    model: str = "deepseek-v4-flash"
    planner_mode: str = "llm_semantic"
```

在 `dataset_service = DatasetService(DATA_ROOT)` 后新增：

```python
preflight_store = PreflightStore()
```

在 `/workbench/query` 前新增 endpoint：

```python
@app.post("/workbench/preflight")
def preflight_workbench(
    request: WorkbenchPreflightRequest,
    http_request: Request,
) -> dict[str, object]:
    """uploaded admissions 查询前检查，不执行 SQL。"""

    try:
        _ensure_scope(_actor_context_from_request(http_request), "query")
        response = dataset_service.preflight(
            request.dataset_id,
            user_input=request.user_input.strip(),
            hard_filters=request.hard_filters,
            soft_preferences=request.soft_preferences,
            model=request.model,
            planner_mode=request.planner_mode,
            domain_name=request.domain_name,
        )
        if response.get("status") in {"ready", "needs_confirmation"}:
            preflight_store.put(response)
        return response
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc
```

- [ ] **Step 5: 运行 endpoint test**

Run:

```bash
.venv/bin/python -m unittest tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_preflight_endpoint_returns_contract
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add src/api/preflight_store.py src/api/server.py tests/test_tool_server_endpoints.py
git commit -m "feat: expose uploaded admissions preflight endpoint"
```

---

### Task 4: 正式查询验证 preflight_id 和确认项

**Files:**
- Modify: `src/api/server.py`
- Modify: `src/api/preflight_store.py`
- Test: `tests/test_tool_server_endpoints.py`

- [ ] **Step 1: 写失败测试：伪造 preflight confirmation 被拒绝**

在 `ToolServerEndpointsTest` 中添加：

```python
    def test_workbench_query_rejects_forged_preflight_confirmation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            service, dataset_id = _queryable_uploaded_admissions(root, use_excel=False)
            with patch.object(server_module, "dataset_service", service):
                response = self.client.post(
                    "/workbench/query",
                    headers=_auth_headers("query-token"),
                    json={
                        "dataset_id": dataset_id,
                        "domain_name": "admissions",
                        "user_input": "我的排位是15000，想读人工智能，稳一点",
                        "hard_filters": {
                            "source_province": "广东",
                            "subject_type": "物理",
                            "reselected_subjects": ["化学", "生物"],
                            "user_rank": 15000,
                        },
                        "soft_preferences": {"prompt": "我的排位是15000，想读人工智能，稳一点"},
                        "planner_mode": "llm_semantic",
                        "preflight_id": "pf_forged",
                        "confirmed_boundaries": [
                            {
                                "confirmation_id": "pfc_forged",
                                "option_id": "rank_window_steady",
                            }
                        ],
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["detail"]["code"], "invalid_preflight")
```

- [ ] **Step 2: 写失败测试：当前 preflight 可被 query 引用**

在 `ToolServerEndpointsTest` 中添加：

```python
    def test_workbench_query_accepts_current_preflight_reference(self) -> None:
        prompt = "我想进深圳大学，目前排位15000，帮我看看有什么专业可以选"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            service, dataset_id = _queryable_uploaded_admissions(root, use_excel=False)
            with patch.object(server_module, "dataset_service", service):
                preflight = self.client.post(
                    "/workbench/preflight",
                    headers=_auth_headers("query-token"),
                    json={
                        "dataset_id": dataset_id,
                        "domain_name": "admissions",
                        "user_input": prompt,
                        "hard_filters": {
                            "source_province": "广东",
                            "subject_type": "物理",
                            "reselected_subjects": ["化学", "生物"],
                            "user_rank": 15000,
                        },
                        "soft_preferences": {"prompt": prompt},
                        "planner_mode": "llm_semantic",
                    },
                ).json()
                response = self.client.post(
                    "/workbench/query",
                    headers=_auth_headers("query-token"),
                    json={
                        "dataset_id": dataset_id,
                        "domain_name": "admissions",
                        "user_input": prompt,
                        "hard_filters": {
                            "source_province": "广东",
                            "subject_type": "物理",
                            "reselected_subjects": ["化学", "生物"],
                            "user_rank": 15000,
                        },
                        "soft_preferences": {"prompt": prompt},
                        "planner_mode": "legacy",
                        "preflight_id": preflight["preflight_id"],
                        "confirmed_boundaries": [],
                        "disabled_boundaries": [],
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        assert_workbench_contract(self, payload)
        self.assertIn(payload["status"], {"ok", "needs_confirmation", "no_results"})
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_query_rejects_forged_preflight_confirmation \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_query_accepts_current_preflight_reference
```

Expected: 第一个 FAIL，因为 request model 还不接受 `preflight_id` 或未拒绝；第二个可能 PASS 或忽略 preflight，后续需要强校验。

- [ ] **Step 4: 扩展 request model**

在 `src/api/server.py` 新增：

```python
class PreflightBoundarySelection(BaseModel):
    """用户对查询前检查确认项的受控选择。"""

    confirmation_id: str
    option_id: str = "do_not_use"
```

扩展 `WorkbenchQueryRequest`：

```python
    preflight_id: str | None = None
    confirmed_boundaries: list[PreflightBoundarySelection] = Field(default_factory=list)
    disabled_boundaries: list[PreflightBoundarySelection] = Field(default_factory=list)
```

- [ ] **Step 5: 在 preflight store 中增加 validate**

修改 `src/api/preflight_store.py`：

```python
class PreflightValidationError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
```

新增方法：

```python
    def validate(
        self,
        *,
        preflight_id: str,
        input_signature: str,
        dataset_id: str,
        domain_name: str,
        confirmed: list[dict[str, Any]],
        disabled: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        item = self.get(preflight_id)
        if item is None:
            raise PreflightValidationError("查询前检查已过期或不存在。")
        if item.input_signature != input_signature:
            raise PreflightValidationError("查询输入已变化，请重新运行查询前检查。")
        if item.dataset_id != dataset_id or item.domain_name != domain_name:
            raise PreflightValidationError("查询前检查不属于当前数据源。")
        boundary_by_id = {
            boundary["confirmation_id"]: boundary
            for boundary in item.boundary_confirmations
        }
        selected = [*confirmed, *disabled]
        selected_ids = {entry.get("confirmation_id") for entry in selected}
        unknown = selected_ids - set(boundary_by_id)
        if unknown:
            raise PreflightValidationError("存在不是系统生成的确认项。")
        if set(boundary_by_id) - selected_ids:
            raise PreflightValidationError("请先处理所有需要确认的边界。")
        return [
            _selected_boundary_patch(boundary_by_id[entry["confirmation_id"]], entry)
            for entry in confirmed
        ]


def _selected_boundary_patch(
    boundary: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, Any]:
    option_id = selected.get("option_id") or "do_not_use"
    for option in boundary.get("options") or []:
        if option.get("option_id") == option_id:
            return dict(option.get("query_patch") or {})
    raise PreflightValidationError("确认项选择值不在系统选项中。")
```

- [ ] **Step 6: server query 中校验 preflight 并合并受控 patch**

在 `src/api/server.py` imports 加：

```python
from src.api.preflight_store import PreflightStore, PreflightValidationError
from src.api.workbench_preflight import WorkbenchPreflightConfig, preflight_input_signature
```

新增 helpers：

```python
def _preflight_signature_for_request(request: WorkbenchQueryRequest) -> str:
    return preflight_input_signature(
        WorkbenchPreflightConfig(
            user_input=request.user_input.strip(),
            hard_filters=request.hard_filters,
            soft_preferences=request.soft_preferences,
            model=request.model,
            planner_mode=request.planner_mode,
            domain_name=request.domain_name,
            dataset_id=request.dataset_id,
        )
    )


def _apply_preflight_patches(
    request: WorkbenchQueryRequest,
    patches: list[dict[str, Any]],
) -> WorkbenchQueryRequest:
    hard_filters = dict(request.hard_filters)
    soft_preferences = dict(request.soft_preferences)
    for patch in patches:
        hard_filters.update(patch.get("hard_filters") or {})
        soft_preferences.update(patch.get("soft_preferences") or {})
    return request.model_copy(
        update={
            "hard_filters": hard_filters,
            "soft_preferences": {
                **soft_preferences,
                "preflight_id": request.preflight_id,
            },
        }
    )
```

在 `query_workbench()` 中 `_ensure_scope` 后添加：

```python
        if request.preflight_id:
            try:
                patches = preflight_store.validate(
                    preflight_id=request.preflight_id,
                    input_signature=_preflight_signature_for_request(request),
                    dataset_id=str(request.dataset_id or ""),
                    domain_name=request.domain_name,
                    confirmed=[
                        item.model_dump() for item in request.confirmed_boundaries
                    ],
                    disabled=[
                        item.model_dump() for item in request.disabled_boundaries
                    ],
                )
            except PreflightValidationError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "invalid_preflight",
                        "message": exc.message,
                        "details": {},
                    },
                ) from exc
            request = _apply_preflight_patches(request, patches)
```

- [ ] **Step 7: 运行 HTTP validation tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_query_rejects_forged_preflight_confirmation \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_query_accepts_current_preflight_reference
```

Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add src/api/preflight_store.py src/api/server.py tests/test_tool_server_endpoints.py
git commit -m "feat: validate preflight confirmations before query"
```

---

### Task 5: 前端 request/state 工具

**Files:**
- Modify: `frontend/src/utils/workbenchRequests.js`
- Modify: `frontend/src/utils/workbenchState.js`
- Modify: `frontend/src/utils/workbenchState.test.js`

- [ ] **Step 1: 写失败测试**

在 `frontend/src/utils/workbenchState.test.js` imports 中加入：

```js
  allPreflightBoundariesHandled,
  createEmptyPreflightState,
  isUploadedAdmissionsSource,
  splitPreflightState,
```

在 requests imports 中加入：

```js
  buildPreflightRequest,
  buildPreflightWorkbenchRequest,
```

添加测试：

```js
test('buildPreflightRequest only includes uploaded admissions data source', () => {
  const request = buildPreflightRequest({
    source: {
      type: 'uploaded',
      datasetId: 'dataset_1',
      domainName: 'admissions',
    },
    runRequest: {
      user_input: '我的排位是15000，稳一点',
      hard_filters: { user_rank: 15000 },
      soft_preferences: { prompt: '稳一点' },
    },
    model: 'deepseek-v4-flash',
  });

  assert.equal(request.dataset_id, 'dataset_1');
  assert.equal(request.domain_name, 'admissions');
  assert.equal(request.planner_mode, 'llm_semantic');
});

test('buildPreflightRequest rejects bundled admissions source', () => {
  assert.throws(() => buildPreflightRequest({
    source: { type: 'builtin', domainName: 'admissions' },
    runRequest: {
      user_input: '广东物理，排位 32000。',
      hard_filters: {},
      soft_preferences: {},
    },
    model: 'deepseek-v4-flash',
  }), /uploaded admissions/);
});

test('splitPreflightState groups recognized facts and boundary choices', () => {
  const split = splitPreflightState({
    recognized_facts: [{ label: '全省排位' }],
    boundary_confirmations: [{ confirmation_id: 'pfc_rank', label: '稳一点' }],
    not_executable_preferences: [{ source_text: '好就业' }],
    missing_requirements: [{ label: '科类' }],
  });

  assert.equal(split.facts.length, 1);
  assert.equal(split.boundaries.length, 1);
  assert.equal(split.blocked.length, 1);
  assert.equal(split.missing.length, 1);
});

test('allPreflightBoundariesHandled requires every boundary to be selected', () => {
  const preflight = {
    boundary_confirmations: [
      { confirmation_id: 'pfc_rank' },
      { confirmation_id: 'pfc_major' },
    ],
    missing_requirements: [],
  };

  assert.equal(allPreflightBoundariesHandled(preflight, { pfc_rank: 'rank_window_steady' }), false);
  assert.equal(allPreflightBoundariesHandled(preflight, {
    pfc_rank: 'rank_window_steady',
    pfc_major: 'do_not_use',
  }), true);
});

test('buildPreflightWorkbenchRequest submits only generated ids and option ids', () => {
  const request = buildPreflightWorkbenchRequest({
    previousRequest: {
      dataset_id: 'dataset_1',
      domain_name: 'admissions',
      user_input: '我的排位是15000，稳一点',
      hard_filters: { user_rank: 15000 },
      soft_preferences: { prompt: '稳一点' },
      planner_mode: 'llm_semantic',
    },
    preflight: {
      preflight_id: 'pf_123',
      boundary_confirmations: [
        { confirmation_id: 'pfc_rank' },
        { confirmation_id: 'pfc_major' },
      ],
    },
    selectedBoundaryOptions: {
      pfc_rank: 'rank_window_steady',
      pfc_major: 'do_not_use',
    },
  });

  assert.equal(request.preflight_id, 'pf_123');
  assert.deepEqual(request.confirmed_boundaries, [
    { confirmation_id: 'pfc_rank', option_id: 'rank_window_steady' },
  ]);
  assert.deepEqual(request.disabled_boundaries, [
    { confirmation_id: 'pfc_major', option_id: 'do_not_use' },
  ]);
  assert.equal('sql' in request, false);
});

test('isUploadedAdmissionsSource is true only for uploaded admissions', () => {
  assert.equal(isUploadedAdmissionsSource({
    type: 'uploaded',
    datasetId: 'dataset_1',
    domainName: 'admissions',
  }), true);
  assert.equal(isUploadedAdmissionsSource({
    type: 'builtin',
    datasetId: null,
    domainName: 'admissions',
  }), false);
  assert.equal(isUploadedAdmissionsSource({
    type: 'uploaded',
    datasetId: 'dataset_2',
    domainName: 'housing',
  }), false);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: FAIL，提示 named export 不存在。

- [ ] **Step 3: 实现 request helpers**

修改 `frontend/src/utils/workbenchRequests.js`：

```js
export function buildPreflightRequest({
  source,
  runRequest,
  model,
  plannerMode = 'llm_semantic',
}) {
  if (source?.type !== 'uploaded' || source?.domainName !== 'admissions' || !source?.datasetId) {
    throw new Error('preflight requires uploaded admissions source');
  }
  return {
    dataset_id: source.datasetId,
    domain_name: 'admissions',
    user_input: runRequest.user_input,
    hard_filters: runRequest.hard_filters || {},
    soft_preferences: runRequest.soft_preferences || {},
    model,
    planner_mode: plannerMode,
  };
}

export function buildPreflightWorkbenchRequest({
  previousRequest,
  preflight,
  selectedBoundaryOptions,
}) {
  const boundaryIds = new Set(
    (preflight?.boundary_confirmations || []).map((item) => item.confirmation_id),
  );
  const confirmed_boundaries = [];
  const disabled_boundaries = [];
  for (const [confirmationId, optionId] of Object.entries(selectedBoundaryOptions || {})) {
    if (!boundaryIds.has(confirmationId)) continue;
    const item = { confirmation_id: confirmationId, option_id: optionId };
    if (optionId === 'do_not_use') {
      disabled_boundaries.push(item);
    } else {
      confirmed_boundaries.push(item);
    }
  }
  return {
    ...previousRequest,
    preflight_id: preflight?.preflight_id || null,
    confirmed_boundaries,
    disabled_boundaries,
  };
}
```

- [ ] **Step 4: 实现 state helpers**

修改 `frontend/src/utils/workbenchState.js`：

```js
export function createEmptyPreflightState(overrides = {}) {
  return {
    schema_version: 'workbench_preflight.v1',
    status: 'idle',
    preflight_id: null,
    dataset_id: null,
    domain_name: null,
    recognized_facts: [],
    boundary_confirmations: [],
    not_executable_preferences: [],
    missing_requirements: [],
    planner: {},
    warnings: [],
    result_count: 0,
    items: [],
    top_results: [],
    ...overrides,
  };
}

export function splitPreflightState(preflight) {
  return {
    facts: Array.isArray(preflight?.recognized_facts) ? preflight.recognized_facts : [],
    boundaries: Array.isArray(preflight?.boundary_confirmations) ? preflight.boundary_confirmations : [],
    blocked: Array.isArray(preflight?.not_executable_preferences)
      ? preflight.not_executable_preferences
      : [],
    missing: Array.isArray(preflight?.missing_requirements)
      ? preflight.missing_requirements
      : [],
    warnings: Array.isArray(preflight?.warnings) ? preflight.warnings : [],
  };
}

export function allPreflightBoundariesHandled(preflight, selectedBoundaryOptions) {
  const split = splitPreflightState(preflight);
  if (split.missing.length) return false;
  return split.boundaries.every((boundary) => (
    boundary.confirmation_id
    && selectedBoundaryOptions?.[boundary.confirmation_id]
  ));
}

export function isUploadedAdmissionsSource(source) {
  return source?.type === 'uploaded'
    && source?.domainName === 'admissions'
    && Boolean(source?.datasetId);
}
```

- [ ] **Step 5: 运行 frontend unit tests**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/workbenchRequests.js frontend/src/utils/workbenchState.js frontend/src/utils/workbenchState.test.js
git commit -m "feat: add frontend preflight utilities"
```

---

### Task 6: `PreflightPanel.vue`

**Files:**
- Create: `frontend/src/components/PreflightPanel.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 创建组件**

创建 `frontend/src/components/PreflightPanel.vue`：

```vue
<script setup>
import { computed } from 'vue';
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
} from '@element-plus/icons-vue';

import { splitPreflightState } from '../utils/workbenchState';

const props = defineProps({
  preflight: {
    type: Object,
    required: true,
  },
  selectedBoundaryOptions: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['select-boundary']);

const groups = computed(() => splitPreflightState(props.preflight));
const statusCopy = computed(() => {
  const labels = {
    idle: '输入后先做查询前检查。',
    ready: '可以进入查询。',
    needs_confirmation: '需要你确认边界。',
    blocked: '当前不能查询。',
    error: '查询前检查失败。',
  };
  return labels[props.preflight?.status] || '等待查询前检查。';
});

function boundaryValue(boundary) {
  return props.selectedBoundaryOptions?.[boundary.confirmation_id] || '';
}

function itemTitle(item) {
  return item?.label || item?.source_text || item?.message || '未命名项目';
}

function itemMessage(item, fallback) {
  return item?.message || item?.reason || item?.treatment || fallback;
}
</script>

<template>
  <el-card class="workbench-card preflight-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>查询前检查</h2>
          <p class="preflight-subtitle">{{ statusCopy }}</p>
        </div>
        <el-tag
          :type="preflight.status === 'ready' ? 'success' : preflight.status === 'blocked' ? 'danger' : 'warning'"
          effect="plain"
        >
          {{ preflight.status === 'ready' ? '可以进入查询' : preflight.status === 'blocked' ? '已阻断' : '待处理' }}
        </el-tag>
      </div>
    </template>

    <el-skeleton v-if="loading" :rows="5" animated />

    <div v-else class="preflight-sections">
      <section class="preflight-section pass">
        <div class="preflight-section-title">
          <el-icon><CircleCheckFilled /></el-icon>
          <h3>已识别事实</h3>
        </div>
        <article
          v-for="fact in groups.facts"
          :key="fact.fact_id || fact.label"
          class="preflight-row"
        >
          <strong>{{ itemTitle(fact) }}</strong>
          <p>{{ itemMessage(fact, '可以进入验证链路。') }}</p>
        </article>
        <p v-if="!groups.facts.length" class="beginner-empty">暂无已识别事实</p>
      </section>

      <section class="preflight-section warn">
        <div class="preflight-section-title">
          <el-icon><WarningFilled /></el-icon>
          <h3>需要你确认</h3>
        </div>
        <article
          v-for="boundary in groups.boundaries"
          :key="boundary.confirmation_id"
          class="preflight-row boundary-row"
        >
          <div>
            <strong>{{ itemTitle(boundary) }}</strong>
            <p>{{ itemMessage(boundary, '需要确认边界后才能查询。') }}</p>
          </div>
          <el-radio-group
            :model-value="boundaryValue(boundary)"
            @update:model-value="emit('select-boundary', boundary.confirmation_id, $event)"
          >
            <el-radio-button
              v-for="option in boundary.options || []"
              :key="option.option_id"
              :label="option.option_id"
              :value="option.option_id"
            >
              {{ option.label }}
            </el-radio-button>
          </el-radio-group>
        </article>
        <p v-if="!groups.boundaries.length" class="beginner-empty">暂无需要确认的边界</p>
      </section>

      <section class="preflight-section muted">
        <div class="preflight-section-title">
          <el-icon><CircleCloseFilled /></el-icon>
          <h3>不会参与筛选</h3>
        </div>
        <article
          v-for="item in groups.blocked"
          :key="item.preference_id || item.source_text"
          class="preflight-row"
        >
          <strong>{{ item.source_text || itemTitle(item) }}</strong>
          <p>{{ itemMessage(item, '当前没有可审核证据支持。') }}</p>
        </article>
        <p v-if="!groups.blocked.length" class="beginner-empty">暂无被排除偏好</p>
      </section>

      <section class="preflight-section bad">
        <div class="preflight-section-title">
          <el-icon><WarningFilled /></el-icon>
          <h3>还缺少信息</h3>
        </div>
        <article
          v-for="item in groups.missing"
          :key="item.requirement_id || item.field"
          class="preflight-row"
        >
          <strong>{{ itemTitle(item) }}</strong>
          <p>{{ itemMessage(item, '请补充后再查询。') }}</p>
        </article>
        <p v-if="!groups.missing.length" class="beginner-empty">暂无缺口</p>
      </section>
    </div>
  </el-card>
</template>
```

- [ ] **Step 2: 补 CSS**

在 `frontend/src/style.css` 追加：

```css
.preflight-card {
  min-width: 0;
}

.preflight-subtitle {
  margin: 4px 0 0;
  color: #66717c;
  font-size: 13px;
  line-height: 1.45;
}

.preflight-sections {
  display: grid;
  gap: 12px;
}

.preflight-section {
  display: grid;
  gap: 8px;
  padding-block: 10px;
  border-top: 1px solid #e2e8e3;
}

.preflight-section:first-child {
  border-top: 0;
  padding-top: 0;
}

.preflight-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preflight-section-title h3 {
  margin: 0;
  font-size: 14px;
  line-height: 1.35;
}

.preflight-section.pass .el-icon {
  color: #0f7b45;
}

.preflight-section.warn .el-icon {
  color: #9a6812;
}

.preflight-section.bad .el-icon {
  color: #b42318;
}

.preflight-section.muted .el-icon {
  color: #66717c;
}

.preflight-row {
  display: grid;
  gap: 4px;
  padding: 9px 10px;
  border: 1px solid #e2e8e3;
  border-radius: 8px;
  background: #fbfdfb;
}

.preflight-row strong,
.preflight-row p {
  min-width: 0;
}

.preflight-row p {
  margin: 0;
  color: #66717c;
  font-size: 13px;
  line-height: 1.5;
}

.boundary-row {
  gap: 10px;
}

.boundary-row .el-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
```

- [ ] **Step 3: 运行 build 确认组件语法**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PreflightPanel.vue frontend/src/style.css
git commit -m "feat: add preflight panel"
```

---

### Task 7: 前端 App 两阶段门禁接入

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/WorkbenchRunBar.vue`
- Modify: `frontend/src/utils/workbenchPresentation.js`

- [ ] **Step 1: 扩展 RunBar 主按钮文案**

修改 `frontend/src/components/WorkbenchRunBar.vue` props：

```js
  primaryActionLabel: {
    type: String,
    default: '开始查询',
  },
  primaryActionDisabled: {
    type: Boolean,
    default: false,
  },
```

按钮改为：

```vue
      <el-button
        type="primary"
        :icon="Search"
        :loading="loading"
        :disabled="primaryActionDisabled"
        @click="emit('run')"
      >
        {{ loading ? '正在处理' : primaryActionLabel }}
      </el-button>
```

- [ ] **Step 2: App imports 和 state**

修改 `frontend/src/App.vue` imports：

```js
import PreflightPanel from './components/PreflightPanel.vue';
import {
  buildConfirmedWorkbenchRequest,
  buildPreflightRequest,
  buildPreflightWorkbenchRequest,
  buildWorkbenchRequest,
} from './utils/workbenchRequests';
import {
  allPreflightBoundariesHandled,
  createEmptyEvidenceReport,
  createEmptyPreflightState,
  createEmptyWorkbenchState,
  isUploadedAdmissionsSource,
  mergeDemoRun,
} from './utils/workbenchState';
```

在 refs 附近新增：

```js
const preflightData = ref(createEmptyPreflightState());
const preflightLoading = ref(false);
const preflightError = ref('');
const selectedBoundaryOptions = ref({});
const lastPreflightRequest = ref(null);
const lastPreflightContext = ref(null);
```

新增 computed：

```js
const requiresPreflight = computed(() => (
  mode.value === 'api' && isUploadedAdmissionsSource(selectedDataSource.value)
));
const preflightReadyForQuery = computed(() => (
  !requiresPreflight.value
  || (
    lastPreflightContext.value?.inputSignature === inputDraftSignature.value
    && ['ready', 'needs_confirmation'].includes(preflightData.value?.status)
    && allPreflightBoundariesHandled(
      preflightData.value,
      selectedBoundaryOptions.value,
    )
  )
));
const primaryActionLabel = computed(() => {
  if (!requiresPreflight.value) return '开始查询';
  if (!preflightData.value?.preflight_id) return '先做预检';
  if (!preflightReadyForQuery.value) return '处理确认项';
  return '确认后查询';
});
const primaryActionDisabled = computed(() => (
  requiresPreflight.value
  && Boolean(preflightData.value?.preflight_id)
  && !preflightReadyForQuery.value
));
```

- [ ] **Step 3: 新增 preflight actions**

在 methods 区域新增：

```js
async function runPreflight(runRequest) {
  if (!requiresPreflight.value) {
    await runWorkbench(runRequest);
    return;
  }
  preflightLoading.value = true;
  preflightError.value = '';
  selectedBoundaryOptions.value = {};
  lastPreflightRequest.value = runRequest;
  lastPreflightContext.value = null;
  const requestBody = buildPreflightRequest({
    source: selectedDataSource.value,
    runRequest,
    model: model.value,
  });
  try {
    const response = await fetch('/workbench/preflight', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(requestBody),
    });
    const apiPayload = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(apiPayload, '查询前检查失败'));
    }
    preflightData.value = {
      ...createEmptyPreflightState(),
      ...apiPayload,
    };
    lastPreflightContext.value = {
      requestBody,
      dataSourceId: selectedDataSourceId.value,
      mode: mode.value,
      inputSignature: runRequest.form_signature || inputDraftSignature.value,
    };
    runData.value = createEmptyWorkbenchState({
      selected_options: {
        extractor: extractor.value,
        generator: generator.value,
        model: model.value,
      },
    });
  } catch (error) {
    preflightError.value = error instanceof Error
      ? error.message
      : formatApiError(error, '查询前检查失败');
    preflightData.value = createEmptyPreflightState({ status: 'error' });
  } finally {
    preflightLoading.value = false;
  }
}

async function runWorkbenchFromPreflight() {
  if (!lastPreflightContext.value?.requestBody || !preflightData.value?.preflight_id) {
    preflightError.value = '请先完成查询前检查。';
    return;
  }
  const requestBody = buildPreflightWorkbenchRequest({
    previousRequest: {
      ...lastPreflightContext.value.requestBody,
      extractor: normalizedExtractor(),
      generator: generator.value,
      model: model.value,
    },
    preflight: preflightData.value,
    selectedBoundaryOptions: selectedBoundaryOptions.value,
  });
  await runWorkbenchWithRequestBody(requestBody);
}

function selectPreflightBoundary(confirmationId, optionId) {
  selectedBoundaryOptions.value = {
    ...selectedBoundaryOptions.value,
    [confirmationId]: optionId,
  };
}

function clearPreflightState() {
  preflightData.value = createEmptyPreflightState();
  preflightError.value = '';
  selectedBoundaryOptions.value = {};
  lastPreflightRequest.value = null;
  lastPreflightContext.value = null;
}
```

- [ ] **Step 4: 抽出 `runWorkbenchWithRequestBody`，复用 query 请求**

把现有 `runWorkbench(runRequest)` 中 fetch `/workbench/query` 的主体抽出：

```js
async function runWorkbenchWithRequestBody(requestBody) {
  loading.value = true;
  apiError.value = '';
  lastRunFailed.value = false;
  const requestId = nextWorkbenchRequestId();
  const requestDataSourceId = selectedDataSourceId.value;
  const requestMode = mode.value;
  const source = selectedDataSource.value;
  try {
    const response = await fetch('/workbench/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(requestBody),
    });
    const apiPayload = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(apiPayload, '后端运行失败'));
    }
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    lastRequestContext.value = {
      requestBody,
      dataSourceId: requestDataSourceId,
      mode: requestMode,
      inputSignature: inputDraftSignature.value,
    };
    runData.value = {
      ...apiPayload,
      selected_options: {
        ...(apiPayload.selected_options || {}),
        data_source: source.label,
      },
      frontend_state: {
        source: 'api',
        is_explicit_demo: false,
        options_source: workbenchOptions.value.source,
      },
    };
  } catch (error) {
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '后端运行失败');
    lastRunFailed.value = true;
  } finally {
    if (requestId === activeWorkbenchRequestId.value) {
      loading.value = false;
    }
  }
}
```

再把 `runWorkbench(runRequest)` 改成：

```js
async function runWorkbench(runRequest) {
  lastRunRequest.value = runRequest;
  if (mode.value === 'demo') {
    runDemo(runRequest);
    return;
  }
  lastRequestContext.value = null;
  const requestBody = buildWorkbenchRequest({
    source: selectedDataSource.value,
    runRequest,
    extractor: normalizedExtractor(),
    generator: generator.value,
    model: model.value,
  });
  await runWorkbenchWithRequestBody(requestBody);
}
```

- [ ] **Step 5: 主按钮路由**

把 `submitCurrentForm()` 改成：

```js
function submitCurrentForm() {
  if (requiresPreflight.value && preflightReadyForQuery.value && preflightData.value?.preflight_id) {
    runWorkbenchFromPreflight();
    return;
  }
  inputPanelRef.value?.submitRun?.();
}
```

把 `<UserInputPanel @run="runWorkbench" />` 改成：

```vue
                @run="requiresPreflight ? runPreflight : runWorkbench"
```

把 `handleInputDraftChange()` 末尾加：

```js
  if (
    lastPreflightContext.value?.inputSignature
    && lastPreflightContext.value.inputSignature !== inputDraftSignature.value
  ) {
    clearPreflightState();
  }
```

在 `handleDataSourceChange()`、`runDemo()`、`clearLastRequestContext()` 中调用 `clearPreflightState()`。

- [ ] **Step 6: 模板接入 panel 和 runbar props**

`WorkbenchRunBar` 增加 props：

```vue
            :primary-action-label="primaryActionLabel"
            :primary-action-disabled="primaryActionDisabled"
```

在 `result-column` 的 `CandidateRerunPanel` 前插入：

```vue
                <PreflightPanel
                  v-if="requiresPreflight"
                  :preflight="preflightData"
                  :selected-boundary-options="selectedBoundaryOptions"
                  :loading="preflightLoading"
                  @select-boundary="selectPreflightBoundary"
                />
                <el-alert
                  v-if="preflightError"
                  class="inline-alert"
                  type="error"
                  :closable="false"
                  show-icon
                  :title="preflightError"
                />
```

- [ ] **Step 7: 运行 frontend tests/build**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: both PASS。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.vue frontend/src/components/WorkbenchRunBar.vue frontend/src/utils/workbenchPresentation.js
git commit -m "feat: gate uploaded admissions queries with preflight"
```

---

### Task 8: 文档、contract 和 final verification

**Files:**
- Modify: `docs/api_contract.md`
- Modify: `frontend/README.md`
- Modify: `docs/methodology_report.md`

- [ ] **Step 1: 更新 `docs/api_contract.md`**

在 Uploaded Dataset / Ingestion API endpoint 表中加入：

```markdown
| `POST /workbench/preflight` | uploaded admissions 查询前检查。只返回已识别事实、需要确认的边界、不会参与筛选的偏好和缺失信息；不执行 SQL，不返回推荐结果。 |
```

在 uploaded admissions semantic capability 描述后加入：

```markdown
主查询页对 uploaded admissions 使用查询前检查门禁。前端必须先调用
`POST /workbench/preflight`，展示 `已识别事实`、`需要你确认`、`不会参与筛选` 和
`还缺少信息`。正式查询只能引用当前 `preflight_id` 和系统生成的
`confirmation_id`；伪造、过期、跨数据源或输入变化后的确认项必须被拒绝。
查询前检查不返回 SQL、结果行或 RankingPlan，也不能绕过 `PreferenceGrounder`、
`SemanticQueryVerifier` 或 `RankingVerifier`。
```

- [ ] **Step 2: 更新 `frontend/README.md`**

在 API 模式段落加入：

```markdown
当主查询页选择 uploaded admissions 数据源时，页面会先进入“查询前检查”。用户点击
“先做预检”后，前端只展示后端返回的已识别事实、需要确认的边界、不会参与筛选的偏好和还缺少的信息。
处理完需要确认的边界后，才会显示“确认后查询”。内置 admissions 数据源保持现有“开始查询”体验。
```

- [ ] **Step 3: 更新 `docs/methodology_report.md`**

在 EvidenceRequirementClassifier 链路描述附近加入：

```markdown
uploaded admissions 前端现在把该 gate 前移为查询前检查体验：`/workbench/preflight`
只暴露证据需求和用户边界确认项，不返回结果行。需要已审核知识库、已审核排序策略或已审核字段的偏好会在查询前显示为“不会参与筛选”，不能被前端确认执行。
```

- [ ] **Step 4: 运行 focused backend tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_returns_contract \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_excludes_external_preferences \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_admissions_preflight_requires_user_boundary_confirmation \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_preflight_endpoint_returns_contract \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_query_rejects_forged_preflight_confirmation \
  tests.test_tool_server_endpoints.ToolServerEndpointsTest.test_workbench_query_accepts_current_preflight_reference
```

Expected: PASS。

- [ ] **Step 5: 运行 frontend verification**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 6: 运行 full verification**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
git diff --check
```

Expected: `unittest` PASS；`git diff --check` 无输出。

- [ ] **Step 7: Commit docs and verification updates**

```bash
git add docs/api_contract.md docs/methodology_report.md frontend/README.md
git commit -m "docs: describe uploaded admissions preflight"
```

---

## Self-Review

- Spec coverage: 本计划覆盖 uploaded admissions 查询前检查、四类前端展示、中文文案、内置 admissions 隔离、后端 preflight contract、正式查询引用 `preflight_id` 和确认项、不可执行偏好不提供确认按钮、测试与文档更新。
- Placeholder scan: 未发现占位词或空泛步骤；每个任务都有具体文件、测试、命令和预期结果。
- Type consistency: 后端统一使用 `preflight_id`、`confirmed_boundaries`、`disabled_boundaries`、`confirmation_id`、`option_id`；前端 request/state helper 使用相同字段名。用户可见文案全部中文。
