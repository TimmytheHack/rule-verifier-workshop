# Uploaded Dataset LLM Semantic Planner First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 uploaded dataset / reviewed admissions domain 的默认查询入口切到 DeepSeek SemanticIntent first，并把 LLM 调用、验证结果和降级原因写入 EvidencePack。

**Architecture:** 只改 `DatasetService.query()` 进入的 uploaded dataset path；built-in legacy admissions demo 保持现状。DeepSeek 只提出 `SemanticIntent`，系统验证 query type、字段、operator 和值来源后复用现有 `AdmissionsMajorRankPlanner` / `SemanticAdmissionsRecommendationPlanner` 执行 verified SQL。

**Tech Stack:** Python `dataclasses`、Pydantic `SemanticIntent`、DuckDB、现有 `DatasetService`、`WorkbenchConfig`、`DeepSeekSemanticIntentExtractor`、`unittest`、`unittest.mock.patch`。

---

## 文件结构

- Modify: `src/api/workbench.py`
  - 增加 `planner_mode` 配置。
  - 增加 LLM semantic planner invocation 记录。
  - 改 `_run_semantic_capability_query()`：uploaded approved domain 先尝试 DeepSeek `SemanticIntent`。
  - 把 planner metadata / token usage 写入 semantic payload、EvidencePack 和 debug trace。
- Modify: `src/api/dataset_service.py`
  - uploaded dataset 查询默认保持 `planner_mode="auto"`，允许 API 调用覆盖。
- Modify: `src/semantic/llm_intent_extractor.py`
  - 明确 prompt 支持 `admissions_major_rank` 的 structured user context。
  - 继续禁止 SQL / hard rule / execution claim。
- Modify: `tests/test_uploaded_dataset_flow.py`
  - 增加 uploaded query 默认触发 LLM planner 的 fake DeepSeek tests。
  - 覆盖 Q1、Q2、Q3、fallback 和 payload redaction。
- Modify: `tests/test_semantic_llm_intent_extractor.py`
  - 增加 major-rank intent 抽取测试。
- Modify: `scripts/run_semantic_capability_probe.py`
  - 输出 planner metadata 和 token usage，避免只看答案误判 LLM 是否参与。
- Modify: `README.md`、`docs/methodology_report.md`
  - 更新“uploaded dataset 默认 LLM semantic planner first”的行为说明。

---

### Task 1: 写 failing tests，证明 uploaded query 现在没有 LLM planner first

**Files:**
- Modify: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 在测试文件中加入 fake DeepSeek client**

在 `tests/test_uploaded_dataset_flow.py` 的 helper 区域、`_semantic_recommendation_intent()` 前加入：

```python
class FakeSemanticIntentClient:
    def __init__(
        self,
        payload: dict[str, object],
        usage: dict[str, int] | None = None,
    ) -> None:
        self.payload = payload
        self.usage = usage or {
            "prompt_tokens": 21,
            "completion_tokens": 9,
            "total_tokens": 30,
        }
        self.calls: list[dict[str, str]] = []

    def chat_json(self, system_prompt: str, user_prompt: str):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

        class Response:
            def __init__(
                self,
                payload: dict[str, object],
                usage: dict[str, int],
            ) -> None:
                self.payload = payload
                self.usage = usage

        return Response(self.payload, self.usage)
```

- [ ] **Step 2: 加入 major-rank intent payload helper**

在同一区域加入：

```python
def _major_rank_semantic_intent() -> dict[str, object]:
    return {
        "query_type": "admissions_major_rank",
        "user_context": {
            "user_rank": 10000,
            "user_score": None,
            "source_province": "广东",
            "subject_type": "物理",
            "reselected_subjects": ["化学", "生物"],
        },
        "preferences": [],
        "requested_output": ["risk_buckets", "minimum_rank"],
        "source_language": "zh-CN",
    }
```

- [ ] **Step 3: 加入 planner metadata assertion helper**

在同一区域加入：

```python
def _assert_llm_planner_used(
    test_case: unittest.TestCase,
    response: dict[str, object],
    *,
    query_type: str,
) -> None:
    token_usage = response["token_usage"]["extractor"]
    test_case.assertIsNotNone(token_usage)
    test_case.assertGreater(token_usage["total_tokens"], 0)
    planner = response["evidence_pack"]["planner"]
    test_case.assertEqual(planner["mode"], "llm_semantic")
    test_case.assertEqual(planner["provider"], "deepseek")
    test_case.assertTrue(planner["called"])
    test_case.assertFalse(planner["fallback_used"])
    test_case.assertEqual(planner["token_usage"]["total_tokens"], 30)
    test_case.assertEqual(
        response["evidence_pack"]["semantic_intent"]["query_type"],
        query_type,
    )
```

- [ ] **Step 4: 添加 Q1 默认调用 LLM planner 的 failing test**

在 `UploadedSemanticAdmissionsFlowTest` 中加入：

```python
    def test_uploaded_major_rank_query_uses_llm_semantic_planner_first(
        self,
    ) -> None:
        query = "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
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
        self.assertTrue(fake_client.calls)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "admissions_major_rank")
        _assert_llm_planner_used(
            self,
            response,
            query_type="admissions_major_rank",
        )
        self.assertEqual(
            response["debug_trace"]["planner"]["semantic_intent"]["query_type"],
            "admissions_major_rank",
        )
        self.assertEqual(
            response["debug_trace"]["execution"]["selected_subjects"],
            ["化学", "生物"],
        )
```

- [ ] **Step 5: 添加 Q2 默认调用 LLM planner 的 failing test**

在 `UploadedSemanticAdmissionsFlowTest` 中加入：

```python
    def test_uploaded_recommendation_query_uses_llm_semantic_planner_first(
        self,
    ) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        fake_client = FakeSemanticIntentClient(_semantic_recommendation_intent())
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
        self.assertTrue(fake_client.calls)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "recommendation")
        _assert_llm_planner_used(
            self,
            response,
            query_type="semantic_recommendation",
        )
        self.assertEqual(
            response["evidence_pack"]["ranking"]["status"],
            "candidate_list_only",
        )
        self.assertIn("候选列表", response["answer"])
        self.assertEqual(
            response["no_schema_field_preferences"][0]["field_id"],
            "school_country_or_region",
        )
```

- [ ] **Step 6: 添加 Q3 分数无排位仍 needs_confirmation 的 failing test**

在 `UploadedSemanticAdmissionsFlowTest` 中加入：

```python
    def test_uploaded_score_without_rank_uses_llm_but_needs_rank_confirmation(
        self,
    ) -> None:
        query = "假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐"
        fake_client = FakeSemanticIntentClient(
            {
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
                        "reason": "用户明确专业方向。",
                    }
                ],
                "requested_output": ["recommendations"],
            }
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
        self.assertEqual(response["status"], "needs_confirmation")
        _assert_llm_planner_used(
            self,
            response,
            query_type="semantic_recommendation",
        )
        self.assertIn("请补充广东省排位", response["answer"])
        self.assertEqual(response["result_count"], 0)
```

- [ ] **Step 7: 运行 tests，确认失败**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_major_rank_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_recommendation_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_score_without_rank_uses_llm_but_needs_rank_confirmation
```

Expected: FAIL。失败原因应包括 `fake_client.calls` 为空、`token_usage["extractor"] is None` 或 EvidencePack 缺少 `planner`。

- [ ] **Step 8: Commit failing tests**

```bash
git add tests/test_uploaded_dataset_flow.py
git commit -m "test: require llm semantic planner for uploaded queries"
```

---

### Task 2: 增加 planner_mode 和 planner invocation metadata

**Files:**
- Modify: `src/api/workbench.py`
- Modify: `src/api/dataset_service.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 在 `src/api/workbench.py` 增加 planner options**

在 `GENERATOR_OPTIONS` 后加入：

```python
PLANNER_MODE_OPTIONS = {
    "auto": "自动选择语义规划器",
    "llm_semantic": "LLM 语义规划器",
    "regex_fallback": "规则 fallback",
}
```

- [ ] **Step 2: 扩展 `WorkbenchConfig`**

把 `WorkbenchConfig` 改成：

```python
@dataclass(frozen=True)
class WorkbenchConfig:
    """Validated frontend workbench run options."""

    user_input: str = DEFAULT_USER_INPUT
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_preferences: dict[str, Any] = field(default_factory=dict)
    extractor: str = "hybrid"
    generator: str = "template_evidence"
    model: str = "deepseek-v4-flash"
    confirmed_candidates: list[str] = field(default_factory=list)
    domain_name: str = "admissions"
    domain_path: str | None = None
    dataset_id: str | None = None
    planner_mode: str = "auto"
```

- [ ] **Step 3: 更新 `available_options()`**

把返回值改为包含 planners：

```python
    return {
        "extractors": _options(EXTRACTOR_OPTIONS),
        "generators": _options(GENERATOR_OPTIONS),
        "models": _options(MODEL_OPTIONS),
        "planners": _options(PLANNER_MODE_OPTIONS),
        "rank_windows": [dict(item) for item in RANK_WINDOW_OPTIONS],
        "sort_modes": _options(SORT_MODE_OPTIONS),
    }
```

- [ ] **Step 4: 更新 `_validate_config()`**

在 model 校验后加入：

```python
    if config.planner_mode not in PLANNER_MODE_OPTIONS:
        raise ValueError(f"不支持的语义规划方式：{config.planner_mode}")
```

- [ ] **Step 5: 更新 `_selected_options()`**

在 `_selected_options(config)` 返回 dict 中加入：

```python
        "planner": PLANNER_MODE_OPTIONS.get(config.planner_mode, str(config.planner_mode)),
```

- [ ] **Step 6: 更新 `src/api/dataset_service.py` query signature**

把 `DatasetService.query()` signature 改为：

```python
    def query(
        self,
        dataset_id: str,
        *,
        user_input: str,
        hard_filters: dict[str, Any] | None = None,
        soft_preferences: dict[str, Any] | None = None,
        extractor: str = "hybrid",
        generator: str = "template_evidence",
        model: str = "deepseek-v4-flash",
        confirmed_candidates: list[str] | None = None,
        domain_name: str | None = None,
        planner_mode: str = "auto",
    ) -> dict[str, Any]:
```

并在 `WorkbenchConfig(...)` 中加入：

```python
            planner_mode=planner_mode,
```

- [ ] **Step 7: 增加 planner invocation dataclass**

在 `WorkbenchConfig` 后加入：

```python
@dataclass(frozen=True)
class SemanticPlannerInvocation:
    """LLM semantic planner 的公开审计摘要。"""

    mode: str
    provider: str | None = None
    called: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    extraction: Any | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def token_usage(self) -> dict[str, int] | None:
        if self.extraction is None:
            return None
        usage = getattr(self.extraction, "usage", None) or {}
        return dict(usage) if usage else None
```

- [ ] **Step 8: 增加 planner metadata helpers**

在 `_semantic_ranking_plan()` 前加入：

```python
def _planner_metadata(invocation: SemanticPlannerInvocation | None) -> dict[str, Any]:
    if invocation is None:
        return {
            "mode": "legacy",
            "provider": None,
            "called": False,
            "fallback_used": False,
            "fallback_reason": None,
            "token_usage": None,
        }
    return {
        "mode": invocation.mode,
        "provider": invocation.provider,
        "called": invocation.called,
        "fallback_used": invocation.fallback_used,
        "fallback_reason": invocation.fallback_reason,
        "error_type": invocation.error_type,
        "error_message": invocation.error_message,
        "token_usage": invocation.token_usage,
    }


def _planner_semantic_intent(
    invocation: SemanticPlannerInvocation | None,
) -> dict[str, Any] | None:
    if invocation is None or invocation.extraction is None:
        return None
    return _json_ready(invocation.extraction.intent.model_dump())


def _planner_token_usage(
    invocation: SemanticPlannerInvocation | None,
) -> dict[str, int] | None:
    return invocation.token_usage if invocation is not None else None
```

- [ ] **Step 9: Run focused config tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_upload_csv_generates_dataset_id
```

Expected: PASS.

- [ ] **Step 10: Commit config plumbing**

```bash
git add src/api/workbench.py src/api/dataset_service.py
git commit -m "feat: add semantic planner mode metadata"
```

---

### Task 3: 让 uploaded admissions 先调用 DeepSeek SemanticIntent

**Files:**
- Modify: `src/api/workbench.py`
- Modify: `src/semantic/llm_intent_extractor.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 更新 `DeepSeekSemanticIntentExtractor` prompt**

在 `src/semantic/llm_intent_extractor.py` 的 `_user_prompt()` 中，紧跟 `query_type` JSON schema 前增加：

```python
        "如果用户要求“冲稳保”“最低录取排名”“每个专业的最低录取排名”，"
        "优先返回 query_type=admissions_major_rank，并把排位、科类和再选科目写入 user_context。"
        "例如“广东物化生，10000名”应返回 source_province=广东、subject_type=物理、"
        "reselected_subjects=[\"化学\",\"生物\"]、user_rank=10000。"
```

- [ ] **Step 2: 在 `tests/test_semantic_llm_intent_extractor.py` 加 major-rank test**

加入：

```python
    def test_extracts_major_rank_intent_with_subject_bundle(self) -> None:
        payload = {
            "query_type": "admissions_major_rank",
            "user_context": {
                "user_rank": 10000,
                "user_score": None,
                "source_province": "广东",
                "subject_type": "物理",
                "reselected_subjects": ["化学", "生物"],
            },
            "preferences": [],
            "requested_output": ["risk_buckets", "minimum_rank"],
        }
        extractor = DeepSeekSemanticIntentExtractor(
            client=FakeDeepSeekClient(payload)
        )

        result = extractor.extract(
            "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名",
            schema_context=[],
        )

        self.assertEqual(result.intent.query_type, "admissions_major_rank")
        self.assertEqual(result.intent.user_context.user_rank, 10000)
        self.assertEqual(result.intent.user_context.subject_type, "物理")
        self.assertEqual(
            result.intent.user_context.reselected_subjects,
            ["化学", "生物"],
        )
        self.assertEqual(result.usage["total_tokens"], 18)
```

- [ ] **Step 3: 增加 uploaded planner mode helper**

在 `src/api/workbench.py` 的 `_is_builtin_admissions_domain()` 后加入：

```python
def _is_uploaded_reviewed_domain(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> bool:
    return bool(config.dataset_id and config.domain_path) and _domain_pack_can_execute(
        domain_config
    )


def _should_call_llm_semantic_planner(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> bool:
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return False
    if not _is_uploaded_reviewed_domain(config, domain_config):
        return False
    if config.planner_mode == "regex_fallback":
        return False
    if config.planner_mode == "llm_semantic":
        return True
    return deepseek_slot_adapter_enabled()
```

- [ ] **Step 4: 增加 LLM intent invocation helper**

在 `_semantic_recommendation_intent()` 前加入：

```python
def _extract_semantic_planner_intent(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> SemanticPlannerInvocation:
    if not _should_call_llm_semantic_planner(config, domain_config):
        reason = (
            "planner_mode=regex_fallback"
            if config.planner_mode == "regex_fallback"
            else "LLM semantic planner disabled or not uploaded domain"
        )
        return SemanticPlannerInvocation(
            mode="regex_fallback",
            fallback_used=True,
            fallback_reason=reason,
        )
    if not deepseek_slot_adapter_enabled():
        return SemanticPlannerInvocation(
            mode="regex_fallback" if config.planner_mode == "auto" else "llm_semantic",
            provider="deepseek",
            called=False,
            fallback_used=config.planner_mode == "auto",
            fallback_reason="DeepSeek slot adapter disabled",
            error_type="llm_disabled",
            error_message="ENABLE_LLM 或 DEEPSEEK_API_KEY 未启用。",
        )
    try:
        from src.semantic.llm_intent_extractor import (
            DeepSeekSemanticIntentExtractor,
        )

        schema_context, query_options = _semantic_llm_context(domain_config)
        extraction = DeepSeekSemanticIntentExtractor(
            _interactive_deepseek_client(config.model)
        ).extract(
            _compose_user_request(config),
            schema_context=schema_context,
            hard_context={
                "domain": domain_config.domain_id,
                "query_options": query_options,
            },
        )
        return SemanticPlannerInvocation(
            mode="llm_semantic",
            provider=extraction.provider,
            called=True,
            fallback_used=False,
            extraction=extraction,
        )
    except Exception as exc:  # noqa: BLE001 - auto mode 允许可审计降级。
        if config.planner_mode == "llm_semantic":
            return SemanticPlannerInvocation(
                mode="llm_semantic",
                provider="deepseek",
                called=True,
                fallback_used=False,
                error_type=type(exc).__name__,
                error_message=_sanitize_user_text(str(exc)),
            )
        return SemanticPlannerInvocation(
            mode="regex_fallback",
            provider="deepseek",
            called=True,
            fallback_used=True,
            fallback_reason="DeepSeek semantic planner failed; fallback to regex.",
            error_type=type(exc).__name__,
            error_message=_sanitize_user_text(str(exc)),
        )
```

- [ ] **Step 5: 增加 intent -> major-rank request helper**

在 `_extract_semantic_planner_intent()` 后加入：

```python
def _major_rank_request_from_intent(intent: SemanticIntent) -> str:
    context = intent.user_context
    parts = []
    if context.source_province:
        parts.append(context.source_province)
    if context.subject_type:
        parts.append(f"{context.subject_type}类")
    if context.reselected_subjects:
        parts.append("再选科目：" + "、".join(context.reselected_subjects))
    if context.user_rank:
        parts.append(f"排位{context.user_rank}")
    parts.append("列出冲稳保的次序，以及每个专业的最低录取排名")
    return "，".join(parts)
```

- [ ] **Step 6: 改 `_run_semantic_capability_query()` 顺序**

把函数整体替换为：

```python
def _run_semantic_capability_query(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> Any | None:
    if domain_config.domain_id != ADMISSIONS_DOMAIN.domain_id:
        return None
    if not domain_config.semantic_capabilities:
        return None

    planner_invocation = _extract_semantic_planner_intent(config, domain_config)
    if planner_invocation.extraction is not None:
        intent = planner_invocation.extraction.intent
        if intent.query_type == "admissions_major_rank":
            result = AdmissionsMajorRankPlanner(
                domain_config=domain_config,
                database_path=_warehouse_database_path(domain_config),
                table_name=domain_config.table_name,
            ).run(_major_rank_request_from_intent(intent))
            return _attach_semantic_planner(result, planner_invocation)
        if intent.query_type == "semantic_recommendation":
            result = SemanticAdmissionsRecommendationPlanner(
                domain_config=domain_config,
                database_path=_warehouse_database_path(domain_config),
                table_name=domain_config.table_name,
                reranker=_semantic_reranker(config),
                ranking_plan=_semantic_ranking_plan(config),
            ).run(intent)
            return _attach_semantic_planner(result, planner_invocation)
        if config.planner_mode == "llm_semantic":
            return _attach_semantic_planner(
                _unsupported_semantic_intent_result(intent),
                planner_invocation,
            )

    if (
        planner_invocation.error_type
        and config.planner_mode == "llm_semantic"
    ):
        return _planner_blocked_result(planner_invocation)

    user_request = _compose_user_request(config)
    major_rank_result = AdmissionsMajorRankPlanner(
        domain_config=domain_config,
        database_path=_warehouse_database_path(domain_config),
        table_name=domain_config.table_name,
    ).run(user_request)
    if major_rank_result is not None:
        return _attach_semantic_planner(major_rank_result, planner_invocation)

    intent = _semantic_recommendation_intent(config, domain_config)
    if intent is None:
        return None
    result = SemanticAdmissionsRecommendationPlanner(
        domain_config=domain_config,
        database_path=_warehouse_database_path(domain_config),
        table_name=domain_config.table_name,
        reranker=_semantic_reranker(config),
        ranking_plan=_semantic_ranking_plan(config),
    ).run(intent)
    return _attach_semantic_planner(result, planner_invocation)
```

- [ ] **Step 7: 增加 attach helper**

在 `_run_semantic_capability_query()` 后加入：

```python
def _attach_semantic_planner(
    semantic_result: Any | None,
    invocation: SemanticPlannerInvocation,
) -> Any | None:
    if semantic_result is None:
        return None
    execution_summary = dict(getattr(semantic_result, "execution_summary", {}) or {})
    execution_summary["planner"] = _planner_metadata(invocation)
    semantic_intent = _planner_semantic_intent(invocation)
    if semantic_intent is not None:
        execution_summary["semantic_intent"] = semantic_intent
    return replace(semantic_result, execution_summary=execution_summary)
```

- [ ] **Step 8: 增加 unsupported / blocked result helpers**

在 `_attach_semantic_planner()` 后加入：

```python
def _unsupported_semantic_intent_result(intent: SemanticIntent) -> Any:
    from src.semantic.admissions_recommendation import (
        SemanticAdmissionsRecommendationResult,
    )

    return SemanticAdmissionsRecommendationResult(
        query_type="unknown",
        status="blocked",
        rows=[],
        result_sections={},
        answerable_intents=[],
        unanswerable_intents=[
            {
                "intent": intent.query_type,
                "answerable": False,
                "reason": "unsupported_semantic_query_type",
                "message": f"当前不支持 LLM 提出的查询类型：{intent.query_type}",
            }
        ],
        execution_summary={
            "executor": None,
            "query_type": intent.query_type,
            "filtered_row_count": 0,
        },
        warnings=[
            {
                "code": "unsupported_semantic_query_type",
                "severity": "error",
                "message": f"当前不支持 LLM 提出的查询类型：{intent.query_type}",
            }
        ],
    )


def _planner_blocked_result(invocation: SemanticPlannerInvocation) -> Any:
    from src.semantic.admissions_recommendation import (
        SemanticAdmissionsRecommendationResult,
    )

    message = invocation.error_message or "LLM semantic planner 不可用。"
    return SemanticAdmissionsRecommendationResult(
        query_type="unknown",
        status="blocked",
        rows=[],
        result_sections={},
        answerable_intents=[],
        unanswerable_intents=[
            {
                "intent": "llm_semantic_planner",
                "answerable": False,
                "reason": invocation.error_type or "planner_error",
                "message": message,
            }
        ],
        execution_summary={
            "executor": None,
            "query_type": "unknown",
            "filtered_row_count": 0,
        },
        warnings=[
            {
                "code": "llm_semantic_planner_failed",
                "severity": "error",
                "message": message,
            }
        ],
    )
```

- [ ] **Step 9: Run failing tests from Task 1**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_major_rank_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_recommendation_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_score_without_rank_uses_llm_but_needs_rank_confirmation \
  tests.test_semantic_llm_intent_extractor.DeepSeekSemanticIntentExtractorTest.test_extracts_major_rank_intent_with_subject_bundle
```

Expected: tests may still fail because payload/token metadata is not wired to public response yet. Major-rank and recommendation execution should now call fake client.

- [ ] **Step 10: Commit planner routing**

```bash
git add src/api/workbench.py src/semantic/llm_intent_extractor.py tests/test_semantic_llm_intent_extractor.py
git commit -m "feat: route uploaded queries through llm semantic intent"
```

---

### Task 4: 把 planner metadata 和 token usage 写入 EvidencePack / WorkbenchResponse

**Files:**
- Modify: `src/api/workbench.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 更新 `_semantic_evidence_pack()`**

在返回 dict 前计算：

```python
    execution_summary = _public_execution_summary(
        semantic_result.execution_summary
    )
    planner = execution_summary.get("planner") or _planner_metadata(None)
    semantic_intent = execution_summary.get("semantic_intent")
```

然后把返回 dict 中的 `"execution_summary": ...` 改为：

```python
        "execution_summary": execution_summary,
        "planner": planner,
        "semantic_intent": semantic_intent,
        "verified_intents": [
            item
            for item in (execution_summary.get("verified_query_plan") or {}).get(
                "filters",
                [],
            )
            if isinstance(item, dict)
        ],
        "rejected_intents": list(
            getattr(semantic_result, "not_executed_preferences", []) or []
        )
        + list(getattr(semantic_result, "unanswerable_intents", []) or []),
```

并删除原来重复调用 `_public_execution_summary(...)` 的 `"execution_summary"` 值。

- [ ] **Step 2: 更新 `_semantic_capability_payload()` token usage**

在 `evidence_pack = _semantic_evidence_pack(...)` 之后加入：

```python
    extractor_usage = (evidence_pack.get("planner") or {}).get("token_usage")
```

把 legacy payload 的 `"token_usage"` 改为：

```python
        "token_usage": {
            "extractor": extractor_usage,
            "generator": None,
            "total": _sum_usage([extractor_usage]),
        },
```

- [ ] **Step 3: 更新 debug_trace**

把 `WorkbenchResponse(... debug_trace={...})` 中的 debug trace 改为：

```python
        debug_trace={
            "planner": {
                "metadata": evidence_pack.get("planner"),
                "semantic_intent": evidence_pack.get("semantic_intent"),
            },
            "execution": _public_execution_summary(semantic_result.execution_summary),
            "data_warehouse": warehouse_audit,
        },
```

- [ ] **Step 4: 防止 public payload 泄漏 raw LLM payload**

确认 `_planner_semantic_intent()` 只使用 `intent.model_dump()`，不把 `raw_payload` 放进 public response。不要把 `IntentExtractionResult.raw_payload` 写入 EvidencePack。

- [ ] **Step 5: Run Task 1 tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_major_rank_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_recommendation_query_uses_llm_semantic_planner_first \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_score_without_rank_uses_llm_but_needs_rank_confirmation
```

Expected: PASS.

- [ ] **Step 6: Run semantic flow suite**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow tests.test_semantic_llm_intent_extractor
```

Expected: PASS.

- [ ] **Step 7: Commit evidence plumbing**

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: expose llm semantic planner evidence"
```

---

### Task 5: 覆盖 LLM 不可用、LLM 失败和 planner_mode override

**Files:**
- Modify: `tests/test_uploaded_dataset_flow.py`
- Modify: `src/api/workbench.py`

- [ ] **Step 1: 添加 auto fallback test**

在 `UploadedSemanticAdmissionsFlowTest` 中加入：

```python
    def test_uploaded_auto_planner_falls_back_when_llm_disabled(self) -> None:
        query = "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
        with TemporaryDirectory() as directory:
            service, dataset_id = _queryable_uploaded_admissions(
                Path(directory),
                use_excel=False,
            )

            with patch(
                "src.api.workbench.deepseek_slot_adapter_enabled",
                return_value=False,
            ):
                response = service.query(
                    dataset_id,
                    user_input=query,
                    soft_preferences={"prompt": query},
                )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        planner = response["evidence_pack"]["planner"]
        self.assertEqual(planner["mode"], "regex_fallback")
        self.assertFalse(planner["called"])
        self.assertTrue(planner["fallback_used"])
        self.assertEqual(response["token_usage"]["extractor"], None)
```

- [ ] **Step 2: 添加 explicit llm_semantic failure test**

加入：

```python
    def test_uploaded_explicit_llm_semantic_blocks_on_planner_error(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，请给出推荐"
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
                    side_effect=RuntimeError("network down"),
                ):
                    response = service.query(
                        dataset_id,
                        user_input=query,
                        soft_preferences={"prompt": query},
                        planner_mode="llm_semantic",
                    )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "blocked")
        planner = response["evidence_pack"]["planner"]
        self.assertEqual(planner["mode"], "llm_semantic")
        self.assertTrue(planner["called"])
        self.assertFalse(planner["fallback_used"])
        self.assertEqual(planner["error_type"], "RuntimeError")
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("traceback", serialized.lower())
```

- [ ] **Step 3: 添加 explicit regex_fallback 不调用 LLM test**

加入：

```python
    def test_uploaded_regex_fallback_planner_mode_does_not_call_llm(self) -> None:
        query = "我的排位是15000，想读人工智能，计算机，而且想留在广东省，请给出推荐"
        fake_client = FakeSemanticIntentClient(_semantic_recommendation_intent())
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
                        soft_preferences={
                            "prompt": query,
                            "semantic_intent": _semantic_recommendation_intent(),
                        },
                        planner_mode="regex_fallback",
                    )

        assert_workbench_contract(self, response)
        self.assertFalse(fake_client.calls)
        self.assertEqual(response["evidence_pack"]["planner"]["mode"], "regex_fallback")
```

- [ ] **Step 4: 若 tests 暴露 planner metadata 缺失，补 fallback metadata**

在 `_attach_semantic_planner()` 已覆盖 semantic result 的情况下，确认 fallback result 也有 `execution_summary["planner"]`。如果某个 result 为 `None`，不要构造 payload。

- [ ] **Step 5: Run fallback tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_auto_planner_falls_back_when_llm_disabled \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_explicit_llm_semantic_blocks_on_planner_error \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest.test_uploaded_regex_fallback_planner_mode_does_not_call_llm
```

Expected: PASS.

- [ ] **Step 6: Commit fallback behavior**

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py
git commit -m "test: cover semantic planner fallback modes"
```

---

### Task 6: 更新 probe 和文档，避免再次误判 DeepSeek 是否参与

**Files:**
- Modify: `scripts/run_semantic_capability_probe.py`
- Modify: `README.md`
- Modify: `docs/methodology_report.md`

- [ ] **Step 1: 更新 probe 输出**

在 `scripts/run_semantic_capability_probe.py` 的 returned payload 中，把 `evidence_pack` 改为包含 planner：

```python
        "token_usage": response.get("token_usage"),
        "planner": evidence.get("planner", {}),
        "semantic_intent": evidence.get("semantic_intent"),
        "verified_intents": evidence.get("verified_intents", []),
        "rejected_intents": evidence.get("rejected_intents", []),
        "evidence_pack": {
            "answerable_intents": evidence.get("answerable_intents", []),
            "unanswerable_intents": evidence.get("unanswerable_intents", []),
            "not_executed_preferences": evidence.get(
                "not_executed_preferences",
                [],
            ),
            "selection_evidence": evidence.get("selection_evidence", []),
            "execution_summary": evidence.get("execution_summary", {}),
        },
```

- [ ] **Step 2: 更新 README**

在 README 的 uploaded admissions semantic 链路段落中，把“DeepSeek 只提出候选 `SemanticIntent`”改为明确默认行为：

```markdown
uploaded admissions 推荐默认走 LLM semantic planner first：当 `ENABLE_LLM=true` 且 `DEEPSEEK_API_KEY` 可用时，普通 uploaded dataset query 会先调用 `DeepSeekSemanticIntentExtractor` 生成候选 `SemanticIntent`。系统随后用 reviewed mapping 和 verifier 生成 verified QueryAST / SQL；如果 LLM 不可用，`planner_mode=auto` 会降级到 regex fallback，并在 EvidencePack 的 `planner` 字段记录原因。
```

- [ ] **Step 3: 更新 methodology**

在 `docs/methodology_report.md` 的 semantic capability flow 处加入：

```markdown
uploaded dataset path 的默认 planner 是 `auto`：LLM 可用时先调用 DeepSeek semantic planner，LLM 不可用时降级到 deterministic fallback。EvidencePack 记录 `planner.mode`、`planner.called`、`planner.fallback_used`、`planner.token_usage` 和 verified / rejected intents。built-in legacy admissions demo 暂不切换默认 planner。
```

- [ ] **Step 4: Run probe script help**

Run:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py --help
```

Expected: exits 0 and shows existing CLI options.

- [ ] **Step 5: Run docs grep**

Run:

```bash
rg -n "fallback|planner|SemanticIntent|uploaded admissions" README.md docs/methodology_report.md scripts/run_semantic_capability_probe.py
```

Expected: output mentions planner metadata and uploaded default behavior.

- [ ] **Step 6: Commit docs/probe**

```bash
git add scripts/run_semantic_capability_probe.py README.md docs/methodology_report.md
git commit -m "docs: describe uploaded llm planner evidence"
```

---

### Task 7: 全量验证和 live DeepSeek spot check

**Files:**
- No code changes unless verification finds a defect.

- [ ] **Step 1: Run affected suites**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow \
  tests.test_semantic_llm_intent_extractor \
  tests.test_api_workbench \
  tests.test_workbench_api_contract \
  tests.test_workbench_golden_e2e \
  tests.test_security_review_regressions \
  tests.test_admissions_query_types \
  tests.test_semantic_admissions_recommendation
```

Expected: PASS with existing expected failures only.

- [ ] **Step 2: Run full suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: PASS with existing expected failures only.

- [ ] **Step 3: Run live DeepSeek direct probe**

Run:

```bash
.venv/bin/python - <<'PY'
from src.extractors.deepseek_extractor import DeepSeekClient

client = DeepSeekClient(timeout_seconds=20, max_retries=0)
response = client.chat_json(
    system_prompt="只返回 JSON。",
    user_prompt='返回 {"ok": true, "message": "pong"}',
)
print({
    "ok": response.payload.get("ok"),
    "usage_total": response.usage.get("total_tokens"),
})
PY
```

Expected: prints `{"ok": True, "usage_total": <positive int>}` or equivalent Python dict. Do not print API keys.

- [ ] **Step 4: Run live uploaded probe with new Excel if available**

Run:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py \
  "/Users/tz/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/4c3344e6e0eb93b6117c7beb32e4cc5f/Message/MessageTemp/852a31997f8ce6410ad61299d5b75338/File/22-25年全国高校在广东的专业录取分数.xlsx" \
  --dataset-id ds_live_llm_planner_probe \
  --root /tmp/szu_live_llm_planner_probe \
  --live-llm \
  --query "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
```

Expected:

- `status` is `ok`.
- `query_type` is `admissions_major_rank`.
- `planner.called` is `true`.
- `planner.token_usage.total_tokens` is positive.
- `execution_summary.selected_counts` contains 冲 10、稳 13、保 10.

- [ ] **Step 5: Run `git diff --check`**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Commit verification fixes if any**

If Step 1-5 exposed small fixes, commit only those files:

```bash
git add src/api/workbench.py tests/test_uploaded_dataset_flow.py scripts/run_semantic_capability_probe.py README.md docs/methodology_report.md
git commit -m "fix: stabilize uploaded llm planner verification"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage: covers uploaded default LLM planner, fallback, EvidencePack planner metadata, major-rank, recommendation, score-without-rank, SQL boundary, docs and live probe.
- Placeholder scan: no unresolved placeholder text remains.
- Type consistency: plan uses existing `WorkbenchConfig`, `DatasetService.query`, `SemanticIntent`, `IntentExtractionResult`, `AdmissionsMajorRankPlanner`, `SemanticAdmissionsRecommendationPlanner`, `token_usage`, `evidence_pack`, and `debug_trace` names.
- Scope: only uploaded reviewed admissions path changes default planner. Built-in legacy admissions remains out of scope.
