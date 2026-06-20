# 排位窗口和排序确认 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 admissions 排位窗口在高排位考生上过窄的问题，并把排位范围、排序策略、LLM 选项建议全部收束为前端受控选择。

**Architecture:** 后端继续只执行 schema-grounded、前端受控字段提交的规则；自然语言和 LLM 只能建议 `rank_window`、`sort_mode` 的候选选项，不能直接生成 SQL。`verified_filter` 的排位窗口改为只使用上界，避免排位 1000 这类高排位考生因为百分比下界过窄返回 0 条；排序通过 allowlist 传入 `DuckDBExecutor` 和 recommendation planner。

**Tech Stack:** Python `unittest`、FastAPI Workbench、DuckDBExecutor、Vue 3、Element Plus、Vite。

---

## 参考项目和设计结论

- [Microsoft Recommenders](https://github.com/recommenders-team/recommenders)：可参考其 candidate generation / ranking 分层思路，但本项目不能引入黑盒 ranking 作为执行规则。
- [RecBole](https://github.com/RUCAIBox/RecBole)：可参考统一推荐配置和可替换排序策略，但本项目排序必须来自前端受控选项。
- [LensKit](https://github.com/lenskit/lkpy)：可参考 recommendation pipeline 中 candidate selector 与 ranker 的分离方式。
- [python-constraint](https://github.com/python-constraint/python-constraint)：可参考 constraint satisfaction 的显式约束建模；本项目已有 RuleVerifier / RulePromoter，不需要引入新求解器。

结论：不要把 LLM 当推荐器。LLM 可以解释用户意图并建议选项，但执行路径只能接受前端传入的 allowlist value。

## File Structure

- `src/api/workbench.py`：新增 rank window 执行语义、排序选项白名单、`available_options()` 输出、DuckDBExecutor 调用的排序 override。
- `src/executors/duckdb_executor.py`：允许调用方传入 `sort_policy_override`，仍只使用已有 numeric helper，不接受自由 SQL。
- `src/api/admissions_query_planner.py`：recommendation 路径读取同一 `sort_mode` 白名单并记录到 `execution_summary.sort`。
- `src/reporting/decision_option_suggester.py`：新增 evidence-only 选项建议器；先 deterministic，LLM 只能作为可选 reference-only 来源。
- `frontend/src/App.vue`：加载 `/api/workbench/options`，把 `rank_windows`、`sort_modes` 传入输入面板。
- `frontend/src/components/UserInputPanel.vue`：渲染强制选择的排位窗口和排序控件；未选择时阻止提交。
- `frontend/src/components/BeginnerDecisionPanel.vue`：展示后端返回的 `decision_option_suggestions`。
- `docs/api_contract.md`、`docs/methodology_report.md`、`frontend/README.md`：更新行为边界。
- Tests：`tests/test_rule_verifier.py`、`tests/test_duckdb_executor.py`、`tests/test_admissions_query_types.py`、`tests/test_workbench_api_contract.py`，前端用 `npm run build` 做编译验证。

---

### Task 1: 把前端确认的排位窗口改为只执行上界

**Files:**
- Modify: `src/api/workbench.py`
- Modify: `tests/test_rule_verifier.py`
- Modify: `docs/api_contract.md`

- [ ] **Step 1: Write failing tests for upper-only rank windows**

在 `tests/test_rule_verifier.py` 的 `RuleVerifierTest` 中修改 `test_directional_rank_window_creates_structured_confirmed_rule`，并新增高排位测试：

```python
    def test_directional_rank_window_creates_structured_confirmed_rule(self) -> None:
        config = WorkbenchConfig(
            user_input="广东物理，排位32000。",
            hard_filters={
                "source_province": "广东",
                "subject_type": "物理",
                "user_rank": 32000,
            },
            soft_preferences={
                "prompt": "",
                "rank_window_label": "保底",
                "rank_window_lower_percent": 0,
                "rank_window_upper_percent": 50,
            },
        )
        slots = _slots_from_inputs(RegexExtractor().extract(""), config)
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        classified = _apply_soft_confirmations(classified, config, slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)
        final_by_id = {rule["rule_id"]: rule for rule in final_rules}

        self.assertEqual(
            slots["preferences"]["risk_preference_raw"],
            "已选择保底（后 50% 以内）",
        )
        self.assertEqual(final_by_id["e_safety_margin"]["operator"], "<=")
        self.assertEqual(final_by_id["e_safety_margin"]["value"], 48000)

    def test_high_rank_window_does_not_apply_lower_bound(self) -> None:
        config = WorkbenchConfig(
            user_input="广东物理，排位1000。",
            hard_filters={
                "source_province": "广东",
                "subject_type": "物理",
                "user_rank": 1000,
            },
            soft_preferences={
                "prompt": "",
                "rank_window_label": "稳一点",
                "rank_window_lower_percent": 5,
                "rank_window_upper_percent": 15,
            },
        )
        slots = _slots_from_inputs(RegexExtractor().extract(""), config)
        classified = RuleClassifier(TAXONOMY_PATH, self.verifier).classify(slots)
        classified = _apply_soft_confirmations(classified, config, slots)
        final_rules = RulePromoter(
            TAXONOMY_PATH,
            simulated_confirmation_enabled=True,
        ).final_executable_rules(classified)
        final_by_id = {rule["rule_id"]: rule for rule in final_rules}

        self.assertEqual(final_by_id["e_safety_margin"]["operator"], "<=")
        self.assertEqual(final_by_id["e_safety_margin"]["value"], 1150)
        self.assertNotEqual(final_by_id["e_safety_margin"].get("value"), [950, 1150])
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_rule_verifier.RuleVerifierTest.test_directional_rank_window_creates_structured_confirmed_rule \
  tests.test_rule_verifier.RuleVerifierTest.test_high_rank_window_does_not_apply_lower_bound
```

Expected: FAIL because current implementation still emits `operator="between"` and `[lower_bound, upper_bound]`.

- [ ] **Step 3: Add source-aware rank window selection**

In `src/api/workbench.py`, extend `RankWindowSelection`:

```python
@dataclass(frozen=True)
class RankWindowSelection:
    """用户显式确认的位次窗口。"""

    label: str
    lower_percent: int
    upper_percent: int
    upper_only: bool = True
```

Update `_rank_window_selection` so explicit `rank_window_*` fields are upper-only, while legacy `safety_margin_percent` remains symmetric for backwards compatibility:

```python
def _rank_window_selection(
    soft_preferences: dict[str, Any],
) -> RankWindowSelection | None:
    lower_percent = _optional_percent(
        soft_preferences.get("rank_window_lower_percent")
    )
    upper_percent = _optional_percent(
        soft_preferences.get("rank_window_upper_percent")
    )
    if lower_percent is not None or upper_percent is not None:
        lower = lower_percent if lower_percent is not None else 0
        upper = upper_percent if upper_percent is not None else 0
        return RankWindowSelection(
            label=_rank_window_label(soft_preferences, lower, upper),
            lower_percent=lower,
            upper_percent=upper,
            upper_only=True,
        )

    safety_percent = _optional_percent(soft_preferences.get("safety_margin_percent"))
    if safety_percent is None:
        return None
    return RankWindowSelection(
        label=_rank_window_label(soft_preferences, safety_percent, safety_percent),
        lower_percent=safety_percent,
        upper_percent=safety_percent,
        upper_only=False,
    )
```

Update `_rank_window_boundary_text`:

```python
def _rank_window_boundary_text(rank_window: RankWindowSelection) -> str:
    if rank_window.upper_only:
        return f"{rank_window.label}（后 {rank_window.upper_percent}% 以内）"
    return (
        f"{rank_window.label}（前 {rank_window.lower_percent}% / "
        f"后 {rank_window.upper_percent}%）"
    )
```

Update `_apply_soft_confirmations` safety-margin block:

```python
    if (
        rank_window
        and "c_safety_margin" in candidate_rule_ids
        and user_rank
        and rank_field
    ):
        upper_bound = int(user_rank * (1 + rank_window.upper_percent / 100))
        if rank_window.upper_only:
            simulated["safety_margin"] = {
                "selected_option": f"+{rank_window.upper_percent}%",
                "label": _rank_window_boundary_text(rank_window),
                "field": rank_field,
                "operator": "<=",
                "value": upper_bound,
                "source_expression": (
                    f"{user_rank} * {1 + rank_window.upper_percent / 100:.2f}"
                ),
            }
        else:
            lower_bound = max(
                1,
                int(user_rank * (1 - rank_window.lower_percent / 100)),
            )
            simulated["safety_margin"] = {
                "selected_option": (
                    f"-{rank_window.lower_percent}%/+{rank_window.upper_percent}%"
                ),
                "label": _rank_window_boundary_text(rank_window),
                "field": rank_field,
                "operator": "between",
                "value": [lower_bound, upper_bound],
                "source_expression": (
                    f"{user_rank} * {1 - rank_window.lower_percent / 100:.2f} 到 "
                    f"{user_rank} * {1 + rank_window.upper_percent / 100:.2f}"
                ),
            }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_rule_verifier.RuleVerifierTest.test_directional_rank_window_creates_structured_confirmed_rule \
  tests.test_rule_verifier.RuleVerifierTest.test_high_rank_window_does_not_apply_lower_bound
```

Expected: PASS.

- [ ] **Step 5: Update API docs**

In `docs/api_contract.md`, replace the rank window paragraph with:

```markdown
前端显式提交的 `rank_window_lower_percent` / `rank_window_upper_percent`
只使用上界执行：用户排位 `1000` 且 `rank_window_upper_percent=15`
会生成 `专业组最低位次1 <= 1150`。`rank_window_lower_percent`
只保留为 UI 分区标签，不进入 hard filter。旧兼容字段
`safety_margin_percent` 仍表示对称窗口。
```

- [ ] **Step 6: Commit Task 1**

```bash
git add src/api/workbench.py tests/test_rule_verifier.py docs/api_contract.md
git commit -m "fix: use upper-only confirmed rank windows"
```

---

### Task 2: 给 DuckDBExecutor 增加受控排序 override

**Files:**
- Modify: `src/executors/duckdb_executor.py`
- Modify: `src/api/workbench.py`
- Modify: `tests/test_duckdb_executor.py`
- Modify: `tests/test_api_workbench.py`

- [ ] **Step 1: Write failing executor sort tests**

Append to `tests/test_duckdb_executor.py`:

```python
    def test_sort_override_can_show_safer_rank_first(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "sample.duckdb"
            _write_database(database_path, _sample_dataframe())

            result = DuckDBExecutor(database_path).execute(
                [
                    {
                        "rule_id": "e_source_province",
                        "field": "生源地",
                        "operator": "eq",
                        "value": "广东",
                    },
                    {
                        "rule_id": "e_subject_type",
                        "field": "科类",
                        "operator": "eq",
                        "value": "物理",
                    },
                    {
                        "rule_id": "e_safety_margin",
                        "field": "专业组最低位次1",
                        "operator": "<=",
                        "value": 48000,
                    },
                ],
                user_rank=32000,
                sort_policy_override=[
                    {
                        "helper": "__group_rank_num",
                        "label_field_id": "group_min_rank_2024",
                        "direction": "DESC",
                        "nulls": "LAST",
                    },
                    {
                        "helper": "__id_num",
                        "label_field_id": "row_id",
                        "direction": "ASC",
                        "nulls": "LAST",
                        "optional": True,
                    },
                ],
            )

        self.assertTrue(result.audit.sort_key[0].endswith("DESC NULLS LAST"))
        self.assertEqual(result.audit.skipped_soft_rule_ids, [])
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_duckdb_executor.DuckDBExecutorTest.test_sort_override_can_show_safer_rank_first
```

Expected: ERROR because `DuckDBExecutor.execute()` does not accept `sort_policy_override`.

- [ ] **Step 3: Implement sort override without free-form SQL**

In `src/executors/duckdb_executor.py`, change the method signatures:

```python
    def execute(
        self,
        executable_rules: list[dict[str, Any]],
        user_rank: int | None = None,
        top_k: int = 5,
        sort_policy_override: list[dict[str, Any]] | None = None,
    ) -> ExecutionResult:
```

Pass the override into SQL compilation and audit:

```python
            compiled = _compile_select_sql(
                table_name=self.table_name,
                columns=columns,
                hard_rules=hard_rules,
                domain_config=self.domain_config,
                sort_policy_override=sort_policy_override,
            )
```

```python
                sort_key=_sort_key_labels(
                    self.domain_config,
                    columns,
                    sort_policy_override=sort_policy_override,
                ),
```

Update helper signatures:

```python
def _compile_select_sql(
    table_name: str,
    columns: set[str],
    hard_rules: list[dict[str, Any]],
    domain_config: DomainConfig,
    sort_policy_override: list[dict[str, Any]] | None = None,
) -> _CompiledSQL:
```

Where `_order_clause` is called, pass the override:

```python
    order_clause = _order_clause(
        domain_config,
        columns,
        sort_policy_override=sort_policy_override,
    )
```

Replace `_order_clause` and `_sort_key_labels` with allowlist-structure versions:

```python
def _sort_policy(
    domain_config: DomainConfig,
    sort_policy_override: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return list(sort_policy_override or domain_config.execution.get("sort_policy") or [])


def _order_clause(
    domain_config: DomainConfig,
    columns: set[str],
    sort_policy_override: list[dict[str, Any]] | None = None,
) -> str:
    parts = []
    helper_names = {
        str(item["name"])
        for item in domain_config.execution.get("numeric_helper_fields") or []
    }
    for item in _sort_policy(domain_config, sort_policy_override):
        field_id = item.get("label_field_id")
        if field_id:
            source_column = domain_config.source_column(field_id)
            if item.get("optional") and source_column not in columns:
                continue
        helper = str(item["helper"])
        if helper not in helper_names:
            raise ValueError(f"DuckDBExecutor cannot sort by unknown helper: {helper}")
        direction = str(item.get("direction") or "ASC").upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"DuckDBExecutor cannot sort direction: {direction}")
        nulls = str(item.get("nulls") or "LAST").upper()
        if nulls not in {"FIRST", "LAST"}:
            raise ValueError(f"DuckDBExecutor cannot sort nulls: {nulls}")
        parts.append(f"  {_quote_identifier(helper)} {direction} NULLS {nulls}")
    if not parts:
        return ""
    return "ORDER BY\n" + ",\n".join(parts)


def _sort_key_labels(
    domain_config: DomainConfig,
    columns: set[str],
    sort_policy_override: list[dict[str, Any]] | None = None,
) -> list[str]:
    labels = []
    for item in _sort_policy(domain_config, sort_policy_override):
        field_id = item.get("label_field_id")
        if field_id:
            source_column = domain_config.source_column(field_id)
            if item.get("optional") and source_column not in columns:
                continue
            label = source_column
        else:
            label = str(item.get("helper"))
        direction = str(item.get("direction") or "ASC").upper()
        nulls = str(item.get("nulls") or "LAST").upper()
        labels.append(f"{label} {direction} NULLS {nulls}")
    return labels
```

- [ ] **Step 4: Add backend sort option whitelist**

In `src/api/workbench.py`, add constants near `MODEL_OPTIONS`:

```python
SORT_MODE_OPTIONS = {
    "rank_asc": "按历史位次从高到低看（更冲）",
    "rank_desc": "按历史位次从低到高看（更稳）",
    "school_rank_asc": "同等条件下优先院校排名",
}

ADMISSIONS_SORT_POLICIES = {
    "rank_asc": [
        {"helper": "__group_rank_num", "label_field_id": "group_min_rank_2024", "direction": "ASC", "nulls": "LAST"},
        {"helper": "__school_rank_num", "label_field_id": "school_rank", "direction": "ASC", "nulls": "LAST", "optional": True},
        {"helper": "__id_num", "label_field_id": "row_id", "direction": "ASC", "nulls": "LAST", "optional": True},
    ],
    "rank_desc": [
        {"helper": "__group_rank_num", "label_field_id": "group_min_rank_2024", "direction": "DESC", "nulls": "LAST"},
        {"helper": "__school_rank_num", "label_field_id": "school_rank", "direction": "ASC", "nulls": "LAST", "optional": True},
        {"helper": "__id_num", "label_field_id": "row_id", "direction": "ASC", "nulls": "LAST", "optional": True},
    ],
    "school_rank_asc": [
        {"helper": "__school_rank_num", "label_field_id": "school_rank", "direction": "ASC", "nulls": "LAST", "optional": True},
        {"helper": "__group_rank_num", "label_field_id": "group_min_rank_2024", "direction": "ASC", "nulls": "LAST"},
        {"helper": "__id_num", "label_field_id": "row_id", "direction": "ASC", "nulls": "LAST", "optional": True},
    ],
}
```

Add helper:

```python
def _admissions_sort_policy(config: WorkbenchConfig) -> list[dict[str, Any]] | None:
    if config.domain_name != ADMISSIONS_DOMAIN.domain_id or config.domain_path:
        return None
    sort_mode = _clean_text(config.soft_preferences.get("sort_mode"))
    if sort_mode in ADMISSIONS_SORT_POLICIES:
        return ADMISSIONS_SORT_POLICIES[sort_mode]
    return None
```

When constructing `DuckDBExecutor(...).execute(...)`, pass:

```python
        sort_policy_override=_admissions_sort_policy(config),
```

- [ ] **Step 5: Run executor and API tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_duckdb_executor.DuckDBExecutorTest.test_sort_override_can_show_safer_rank_first \
  tests.test_api_workbench
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/executors/duckdb_executor.py src/api/workbench.py tests/test_duckdb_executor.py tests/test_api_workbench.py
git commit -m "feat: add controlled admissions sort modes"
```

---

### Task 3: 让 recommendation 路径使用同一排序选项

**Files:**
- Modify: `src/api/admissions_query_planner.py`
- Modify: `tests/test_admissions_query_types.py`

- [ ] **Step 1: Write failing recommendation sort tests**

Append to `tests/test_admissions_query_types.py`:

```python
    def test_recommendation_sort_mode_is_recorded_and_applied(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=RANK_ONLY_RECOMMENDATION_QUERY,
                soft_preferences={
                    "prompt": RANK_ONLY_RECOMMENDATION_QUERY,
                    "sort_mode": "rank_desc",
                },
                extractor="regex",
            )
        )

        self.assertEqual(result["query_type"], "recommendation")
        execution = result["evidence_pack"]["execution_summary"]
        self.assertEqual(
            execution["sort"],
            [{"field": "rank_margin", "direction": "DESC"}],
        )
        self.assertIn("ORDER BY", execution["sql"])
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_admissions_query_types.AdmissionsQueryTypesTest.test_recommendation_sort_mode_is_recorded_and_applied
```

Expected: FAIL because recommendation currently always records `rank_margin ASC`.

- [ ] **Step 3: Extend recommendation inputs**

In `src/api/admissions_query_planner.py`, add `sort_mode` to `_RecommendationInputs`:

```python
    sort_mode: str | None = None
```

In `_recommendation_inputs`, set it:

```python
            sort_mode=_clean_text(config.soft_preferences.get("sort_mode")),
```

- [ ] **Step 4: Apply sort mode in SQL and execution summary**

Add helper:

```python
def _recommendation_sort(inputs: _RecommendationInputs, default_metric: str) -> dict[str, str]:
    if inputs.sort_mode == "rank_desc" and inputs.rank:
        return {"field": "rank_margin", "direction": "DESC"}
    if inputs.sort_mode == "rank_asc" and inputs.rank:
        return {"field": "rank_margin", "direction": "ASC"}
    if inputs.sort_mode == "school_rank_asc":
        return {"field": "school_rank", "direction": "ASC"}
    return {"field": default_metric, "direction": "ASC"}
```

In `_recommendation`, replace the fixed sort list:

```python
        sort_spec = _recommendation_sort(inputs, metric)
```

and in `execution_summary`:

```python
            "sort": [sort_spec],
```

In `_fetch_recommendation_rows`, replace the fixed `order_metric` logic with:

```python
        sort_spec = _recommendation_sort(inputs, "rank_margin" if inputs.rank else "score_margin")
        if inputs.rank:
            rank_expr = _numeric_expr(kwargs["group_rank_col"])
            rank_window = margin.get("rank_margin") or {}
            lower = max(1, inputs.rank - int(rank_window.get("reach_max_abs") or 8000))
            upper = inputs.rank + int(rank_window.get("safety_min") or 30000)
            conditions.append(f"{rank_expr} BETWEEN ? AND ?")
            params.extend([lower, upper])
            if sort_spec == {"field": "rank_margin", "direction": "DESC"}:
                order_metric = f"({rank_expr} - ?)"
                order_direction = "DESC"
                order_params = [inputs.rank]
            elif sort_spec == {"field": "rank_margin", "direction": "ASC"}:
                order_metric = f"ABS({rank_expr} - ?)"
                order_direction = "ASC"
                order_params = [inputs.rank]
            else:
                order_metric = _numeric_expr(kwargs["group_rank_col"])
                order_direction = "ASC"
                order_params = []
```

Update SQL `ORDER BY` line:

```python
ORDER BY {order_metric} {order_direction} NULLS LAST, group_min_score DESC NULLS LAST
```

- [ ] **Step 5: Run recommendation tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_admissions_query_types
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/api/admissions_query_planner.py tests/test_admissions_query_types.py
git commit -m "feat: apply controlled sort to admissions recommendations"
```

---

### Task 4: 扩展 `/api/workbench/options` 为前端提供受控窗口和排序选项

**Files:**
- Modify: `src/api/workbench.py`
- Modify: `tests/test_workbench_api_contract.py`
- Modify: `docs/api_contract.md`

- [ ] **Step 1: Write failing options contract test**

Append to `tests/test_workbench_api_contract.py`:

```python
    def test_available_options_include_rank_windows_and_sort_modes(self) -> None:
        from src.api.workbench import available_options

        options = available_options()

        self.assertIn("rank_windows", options)
        self.assertIn("sort_modes", options)
        self.assertEqual(
            [item["value"] for item in options["rank_windows"]],
            ["reach", "steady", "safe"],
        )
        self.assertEqual(
            [item["value"] for item in options["sort_modes"]],
            ["rank_asc", "rank_desc", "school_rank_asc"],
        )
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract.WorkbenchApiContractTest.test_available_options_include_rank_windows_and_sort_modes
```

Expected: FAIL because these keys do not exist.

- [ ] **Step 3: Add option constants**

In `src/api/workbench.py`, add:

```python
RANK_WINDOW_OPTIONS = [
    {
        "value": "reach",
        "label": "冲一冲",
        "rank_window_lower_percent": 0,
        "rank_window_upper_percent": 0,
        "description": "只执行后 0% 上界，不设置前向下界。",
    },
    {
        "value": "steady",
        "label": "稳一点",
        "rank_window_lower_percent": 0,
        "rank_window_upper_percent": 15,
        "description": "只执行后 15% 上界，不设置前向下界。",
    },
    {
        "value": "safe",
        "label": "保底",
        "rank_window_lower_percent": 0,
        "rank_window_upper_percent": 50,
        "description": "只执行后 50% 上界，不设置前向下界。",
    },
]
```

Update `available_options()`:

```python
def available_options() -> dict[str, Any]:
    """Return the user-facing option whitelist for API mode."""

    return {
        "extractors": _options(EXTRACTOR_OPTIONS),
        "generators": _options(GENERATOR_OPTIONS),
        "models": _options(MODEL_OPTIONS),
        "rank_windows": RANK_WINDOW_OPTIONS,
        "sort_modes": _options(SORT_MODE_OPTIONS),
    }
```

- [ ] **Step 4: Update API contract**

In `docs/api_contract.md`, add under `/api/workbench/options`:

```markdown
`GET /api/workbench/options` 必须返回 `rank_windows` 和 `sort_modes`。
前端只能提交这些 `value` 对应的受控字段；LLM 建议不得绕过这些白名单。
```

- [ ] **Step 5: Run contract tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add src/api/workbench.py tests/test_workbench_api_contract.py docs/api_contract.md
git commit -m "feat: expose admissions decision options"
```

---

### Task 5: 前端强制用户选择排位窗口和排序

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/UserInputPanel.vue`
- Modify: `frontend/README.md`

- [ ] **Step 1: Add frontend option state in App.vue**

In `frontend/src/App.vue`, add state:

```js
const workbenchOptions = ref({
  rank_windows: [
    { value: 'reach', label: '冲一冲', rank_window_lower_percent: 0, rank_window_upper_percent: 0 },
    { value: 'steady', label: '稳一点', rank_window_lower_percent: 0, rank_window_upper_percent: 15 },
    { value: 'safe', label: '保底', rank_window_lower_percent: 0, rank_window_upper_percent: 50 },
  ],
  sort_modes: [
    { value: 'rank_asc', label: '按历史位次从高到低看（更冲）' },
    { value: 'rank_desc', label: '按历史位次从低到高看（更稳）' },
    { value: 'school_rank_asc', label: '同等条件下优先院校排名' },
  ],
});
```

Add loader:

```js
async function fetchWorkbenchOptions() {
  if (mode.value !== 'api') return;
  try {
    const response = await fetch('/api/workbench/options', {
      headers: authHeaders(),
    });
    if (!response.ok) return;
    const payload = await response.json();
    workbenchOptions.value = {
      ...workbenchOptions.value,
      ...payload,
    };
  } catch {
    // 本地开发时允许使用内置白名单。
  }
}

watch(mode, fetchWorkbenchOptions, { immediate: true });
```

Pass options:

```vue
<UserInputPanel
  :default-hard-filters="defaultHardFilters"
  :default-soft-preferences="defaultSoftPreferences"
  :mode="mode"
  :loading="loading"
  :rank-window-options="workbenchOptions.rank_windows"
  :sort-mode-options="workbenchOptions.sort_modes"
  @run="runWorkbench"
/>
```

- [ ] **Step 2: Refactor UserInputPanel props and state**

In `frontend/src/components/UserInputPanel.vue`, add props:

```js
  rankWindowOptions: {
    type: Array,
    default: () => [],
  },
  sortModeOptions: {
    type: Array,
    default: () => [],
  },
```

Change `emptySoftPreferences()`:

```js
function emptySoftPreferences() {
  return {
    prompt: '想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。',
    safety_margin_percent: '',
    rank_window_preset: '',
    rank_window_lower_percent: null,
    rank_window_upper_percent: null,
    rank_window_label: '',
    sort_mode: '',
    tuition_cap_yuan: '',
  };
}
```

- [ ] **Step 3: Force controlled selection before emit**

In `UserInputPanel.vue`, add local validation:

```js
const formError = ref('');
```

Import `ref`:

```js
import { reactive, ref, watch } from 'vue';
```

At the top of `submitRun()`:

```js
function submitRun() {
  const rankWindow = selectedRankWindow();
  if (!rankWindow) {
    formError.value = '请先选择排位范围：冲一冲、稳一点或保底。';
    return;
  }
  if (!soft.sort_mode) {
    formError.value = '请先选择排序方式。';
    return;
  }
  formError.value = '';
  const hardPayload = {
```

Include sort mode in payload:

```js
  const softPayload = {
    prompt: (soft.prompt || '').trim(),
    safety_margin_percent: null,
    rank_window_label: rankWindow?.label || null,
    rank_window_lower_percent: rankWindow?.lower ?? null,
    rank_window_upper_percent: rankWindow?.upper ?? null,
    sort_mode: soft.sort_mode || null,
    tuition_cap_yuan: soft.tuition_cap_yuan || null,
  };
```

- [ ] **Step 4: Render controls**

Replace hardcoded `rankWindowOptions` usage with backend-driven values. Add this computed helper:

```js
function normalizedRankWindowOptions() {
  return (props.rankWindowOptions || []).map((item) => ({
    label: item.label,
    value: item.value,
    lower: Number(item.rank_window_lower_percent || 0),
    upper: Number(item.rank_window_upper_percent || 0),
    description: item.description || '',
  }));
}
```

Update `applyRankWindowPreset`:

```js
function applyRankWindowPreset(value) {
  const option = normalizedRankWindowOptions().find((item) => item.value === value);
  if (!option) {
    soft.rank_window_preset = '';
    soft.rank_window_label = '';
    return;
  }
  soft.rank_window_preset = option.value;
  soft.rank_window_label = option.label;
  soft.rank_window_lower_percent = option.lower;
  soft.rank_window_upper_percent = option.upper;
}
```

Update `selectedRankWindow`:

```js
function selectedRankWindow() {
  if (!soft.rank_window_preset) return null;
  const option = normalizedRankWindowOptions().find((item) => item.value === soft.rank_window_preset);
  if (!option) return null;
  return {
    label: option.label,
    lower: option.lower,
    upper: option.upper,
  };
}
```

In the template, add an alert and sort select near the rank window controls:

```vue
<el-alert
  v-if="formError"
  class="inline-alert"
  type="warning"
  :closable="false"
  :title="formError"
/>

<div class="control-block">
  <span class="control-label">排序方式</span>
  <el-select v-model="soft.sort_mode" class="full-control">
    <el-option
      v-for="option in sortModeOptions"
      :key="option.value"
      :label="option.label"
      :value="option.value"
    />
  </el-select>
</div>
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0. Existing Vite chunk warnings are acceptable.

- [ ] **Step 6: Update frontend README**

Append to `frontend/README.md`:

```markdown
排位范围和排序方式必须由用户在前端控件中选择。前端只提交后端白名单中的
`rank_window_*` 和 `sort_mode` 值；自由文本和 LLM 只能提示选择，不生成 hard filter。
```

- [ ] **Step 7: Commit Task 5**

```bash
git add frontend/src/App.vue frontend/src/components/UserInputPanel.vue frontend/README.md
git commit -m "feat: require rank window and sort selection"
```

---

### Task 6: 增加 evidence-only 选项建议器，LLM 只建议不执行

**Files:**
- Create: `src/reporting/decision_option_suggester.py`
- Modify: `src/api/workbench.py`
- Modify: `tests/test_workbench_api_contract.py`
- Modify: `tests/test_career_guidance.py`
- Modify: `docs/methodology_report.md`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_workbench_api_contract.py`:

```python
    def test_decision_option_suggestions_are_reference_only(self) -> None:
        result = run_workbench(
            WorkbenchConfig(
                user_input="广东物理，排位1000，想学计算机，学校稳一点。",
                hard_filters={
                    "source_province": "广东",
                    "subject_type": "物理",
                    "user_rank": 1000,
                    "major_keyword": "计算机",
                },
                soft_preferences={
                    "prompt": "学校稳一点。",
                },
                extractor="regex",
            )
        )

        suggestions = result["evidence_pack"]["decision_option_suggestions"]
        self.assertEqual(suggestions["status"], "reference_only")
        self.assertFalse(suggestions["executable"])
        self.assertEqual(suggestions["execution_effect"], "does_not_change_sql_or_results")
        self.assertIn("rank_window", suggestions["suggestions"])
        self.assertIn("sort_mode", suggestions["suggestions"])
        self.assertNotIn("e_safety_margin", [
            item["id"] for item in result["executed_filters"]
        ])
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract.WorkbenchApiContractTest.test_decision_option_suggestions_are_reference_only
```

Expected: FAIL because `decision_option_suggestions` is missing.

- [ ] **Step 3: Create deterministic suggester**

Create `src/reporting/decision_option_suggester.py`:

```python
"""受控排位窗口和排序选项建议；只进 EvidencePack，不参与执行。"""

from __future__ import annotations

from typing import Any


def decision_option_suggestions_for_query(
    user_request: str,
    slots: dict[str, Any],
) -> dict[str, Any]:
    text = user_request or ""
    preferences = slots.get("preferences") or {}
    suggestions: dict[str, dict[str, Any]] = {}

    if any(term in text for term in ["稳一点", "稳妥", "保守一点"]):
        suggestions["rank_window"] = {
            "suggested_value": "steady",
            "label": "稳一点",
            "reason": "用户表达了稳妥偏好，但必须由前端控件确认后才执行。",
        }
        suggestions["sort_mode"] = {
            "suggested_value": "rank_desc",
            "label": "按历史位次从低到高看（更稳）",
            "reason": "稳妥偏好通常需要先看更有余量的结果，但排序也必须由用户确认。",
        }
    elif preferences.get("recommendation_request_raw"):
        suggestions["rank_window"] = {
            "suggested_value": "steady",
            "label": "稳一点",
            "reason": "推荐请求需要先选择排位范围，默认建议从稳一点开始确认。",
        }
        suggestions["sort_mode"] = {
            "suggested_value": "rank_asc",
            "label": "按历史位次从高到低看（更冲）",
            "reason": "未表达保守偏好时，可以先按历史位次从高到低浏览。",
        }

    return {
        "status": "reference_only",
        "execution_effect": "does_not_change_sql_or_results",
        "executable": False,
        "source": "fixed_policy",
        "suggestions": suggestions,
    }
```

- [ ] **Step 4: Wire into EvidencePack payload**

In `src/api/workbench.py`, import:

```python
from src.reporting.decision_option_suggester import (
    decision_option_suggestions_for_query,
)
```

Add helper:

```python
def _decision_option_suggestions_for_payload(
    config: WorkbenchConfig,
    slots: dict[str, Any],
) -> dict[str, Any]:
    return decision_option_suggestions_for_query(
        _compose_user_request(config),
        slots,
    )
```

Where evidence packs are built, add:

```python
        "decision_option_suggestions": _decision_option_suggestions_for_payload(
            config,
            slots,
        ),
```

Use the same value in legacy and planned payload paths. Do not read this field in executor, verifier, planner, or frontend submit logic.

- [ ] **Step 5: Run tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_workbench_api_contract.WorkbenchApiContractTest.test_decision_option_suggestions_are_reference_only \
  tests.test_career_guidance
```

Expected: PASS.

- [ ] **Step 6: Document LLM boundary**

In `docs/methodology_report.md`, add:

```markdown
`decision_option_suggestions` 只能作为 reference-only 建议展示。即使未来使用 LLM
生成建议，也只能输出后端白名单中的 `rank_window` 和 `sort_mode` 候选值；
实际执行仍必须来自前端控件提交的结构化字段。
```

- [ ] **Step 7: Commit Task 6**

```bash
git add src/reporting/decision_option_suggester.py src/api/workbench.py tests/test_workbench_api_contract.py tests/test_career_guidance.py docs/methodology_report.md
git commit -m "feat: suggest controlled decision options"
```

---

### Task 7: 前端展示选项建议但不自动执行

**Files:**
- Modify: `frontend/src/components/BeginnerDecisionPanel.vue`
- Modify: `frontend/README.md`

- [ ] **Step 1: Add computed suggestions**

In `frontend/src/components/BeginnerDecisionPanel.vue`, add:

```js
const optionSuggestions = computed(() => (
  props.runData.evidence_pack?.decision_option_suggestions?.suggestions || {}
));
```

- [ ] **Step 2: Render reference-only suggestions**

In the template, before “还需补充信息”, add:

```vue
<section
  v-if="Object.keys(optionSuggestions).length"
  class="beginner-section warn"
>
  <div class="beginner-section-title">
    <el-icon><WarningFilled /></el-icon>
    <h3>建议先确认</h3>
  </div>
  <div class="beginner-list">
    <article
      v-for="(suggestion, key) in optionSuggestions"
      :key="key"
      class="beginner-row"
    >
      <strong>{{ suggestion.label || suggestion.suggested_value }}</strong>
      <p>{{ suggestion.reason }}</p>
    </article>
  </div>
</section>
```

This section must not mutate form state or call `emit('run')`.

- [ ] **Step 3: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0. Existing Vite chunk warnings are acceptable.

- [ ] **Step 4: Update frontend README**

Append:

```markdown
“建议先确认”只展示后端 EvidencePack 中的 reference-only 选项建议，不自动改写表单，也不触发查询。
```

- [ ] **Step 5: Commit Task 7**

```bash
git add frontend/src/components/BeginnerDecisionPanel.vue frontend/README.md
git commit -m "feat: show decision option suggestions"
```

---

### Task 8: Full verification and stale text scan

**Files:**
- Verify only unless stale docs are found.

- [ ] **Step 1: Run backend tests**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: `OK` with the existing expected failure count unchanged.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0. Existing Vite chunk warnings are acceptable.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 4: Scan execution boundary**

Run:

```bash
rg -n "decision_option_suggestions|sort_mode|rank_window_lower_percent|rank_window_upper_percent" src frontend/src docs tests
```

Expected:
- `decision_option_suggestions` appears only in EvidencePack/API/frontend display/tests/docs.
- `sort_mode` appears in frontend controlled form, backend allowlist, DuckDB sort override, recommendation planner tests/docs.
- `rank_window_lower_percent` is not used to compute a hard filter lower bound for new front-end `rank_window_*` submissions.

- [ ] **Step 5: Manual API smoke test**

Run:

```bash
curl -sS -X POST http://127.0.0.1:8001/workbench/query \
  -H 'Content-Type: application/json' \
  -H 'X-Actor-Token: operator-token' \
  --data '{
    "domain_name":"admissions",
    "user_input":"广东物理，排位1000；偏好描述：想学计算机，稳一点。",
    "hard_filters":{"source_province":"广东","subject_type":"物理","reselected_subjects":["化学","生物"],"user_rank":1000,"major_keyword":"计算机"},
    "soft_preferences":{"prompt":"想学计算机，稳一点。","rank_window_label":"稳一点","rank_window_lower_percent":5,"rank_window_upper_percent":15,"sort_mode":"rank_desc"},
    "extractor":"regex",
    "generator":"template_evidence"
  }' | .venv/bin/python -m json.tool | rg -n "e_safety_margin|专业组最低位次1|sort_key|decision_option_suggestions|result_count"
```

Expected:
- `e_safety_margin` uses `operator <=` and value `1150`.
- `sort_key` first item ends with `DESC NULLS LAST`.
- `result_count` is not forced to 0 by a lower bound.

- [ ] **Step 6: Commit verification doc fixes if needed**

If Step 4 finds stale tracked text, edit only the stale docs and commit:

```bash
git add docs README.md frontend/README.md
git commit -m "docs: align rank window confirmation behavior"
```

If no stale text exists, do not create an empty commit.

---

## Self-Review

Spec coverage:
- 排位 1000 上界问题：Task 1 removes new controlled rank-window lower bound.
- 排序由用户选择：Tasks 2, 3, 5 add controlled sort mode across backend and frontend.
- 前端强制确认：Task 5 blocks submit until rank window and sort mode are selected.
- 后端分析可选项：Task 4 exposes option allowlists; Task 6 adds reference-only suggestions.
- LLM 边界：Task 6 documents that LLM may suggest only allowlisted option values and never executes.
- 开源参考：reference section records candidate/ranking/constraint inspirations without importing a new recommender engine.

Placeholder scan:
- No empty-marker wording found in task instructions.
- Every behavior-changing task includes failing test, expected failure, implementation sketch, passing command, and commit command.

Type consistency:
- `sort_mode` is the only submitted sorting key.
- `rank_window_lower_percent` and `rank_window_upper_percent` remain frontend/API fields; new execution semantics are represented by `RankWindowSelection.upper_only`.
- `decision_option_suggestions` is evidence-only and never appears in executor or planner inputs.
