# Program Risk Review Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一次可复现的程序风险审查，找出硬编码、边界绕过、权限伤害和发布缺口，并把确认后的问题转成有测试、有文档、有提交的改动计划。

**Architecture:** 本计划把审查拆成四条并行线：后端规则边界、API/tool 权限安全、前端 smoke 与 UX 边界、文档与发布就绪度。每条线只收集证据并新增必要的 guard test，不直接放松 verifier、confirmation loop、DuckDB executor 或 EvidencePack 边界；最终由一个汇总任务统一分级、定整改顺序、决定是否进入实现。

**Tech Stack:** Python unittest、FastAPI TestClient、DuckDB、Vue/Vite、Element Plus、shell `rg`/`git`、现有 `.venv`、现有 `make` targets。

---

## 范围检查

这不是单一功能实现，而是一次跨后端、工具层、前端和发布文档的风险审查。执行时应按并行 agent lane 拆开，产物汇总到同一份中文审查报告；任何生产行为变更必须在报告确认后进入单独整改任务。

本计划默认执行者在仓库根目录 `/Users/tz/Desktop/Projects/SZU` 工作，并遵守根目录 `AGENTS.md`：人类可读 Markdown 用中文，源码注释用中文，不提交 `.env`、`.venv`、大表、DuckDB、本地上传目录或临时 outputs。

## 文件结构

- 创建：`docs/risk_review/2026-06-20-program-risk-review.md`
  - 记录本次审查的范围、命令、发现、证据、严重级别、负责人 lane 和整改建议。
- 创建：`docs/risk_review/2026-06-20-remediation-roadmap.md`
  - 把确认后的发现拆成后续变更批次，明确每批要保护的不变量、测试和文档更新。
- 创建或修改：`tests/test_security_review_regressions.py`
  - 增加本次审查确认的权限、路径、敏感信息、confirmation 和 hardcoded 行为回归测试。
- 修改：`docs/security_model.md`
  - 只在审查发现现有安全边界说明过时或不完整时更新。
- 修改：`docs/tool_contract.md`
  - 只在 tool 权限、LLM-safe schema 或 audit 边界说明过时或不完整时更新。
- 修改：`docs/production_deployment.md`
  - 只在发布部署、安全配置或本地 dev token 说明过时或不完整时更新。
- 修改：`README.md`
  - 只在用户可见启动、鉴权、数据产物或已知风险说明过时或不完整时更新。
- 读取重点文件：
  - `src/api/workbench.py`
  - `src/api/server.py`
  - `src/api/tool_registry.py`
  - `src/api/admissions_query_planner.py`
  - `src/executors/duckdb_executor.py`
  - `src/schema/attribute_grounder.py`
  - `src/rules/rule_verifier.py`
  - `src/rules/rule_promoter.py`
  - `src/reporting/evidence_pack.py`
  - `frontend/src/App.vue`
  - `frontend/src/components/DatasetIngestionPanel.vue`
  - `frontend/src/components/UserInputPanel.vue`
  - `frontend/src/components/CandidateConfirmation.vue`
  - `schemas/tools/*.json`
  - `domains/*/domain.json`
  - `Makefile`
  - `Dockerfile`
  - `docker-compose.yml`
  - `RELEASE_CHECKLIST.md`
  - `docs/security_model.md`
  - `docs/tool_contract.md`
  - `docs/production_deployment.md`

## 审查分级

- `P0`：可导致未经 verifier/confirmation 的 SQL 执行、原始 Excel 进入答案生成、admin tool 被 LLM-safe/default 暴露、secret 泄露、路径穿越写入仓库外。
- `P1`：可导致错误推荐暗示、no-schema 偏好被执行、candidate_id 跨 query 被接受、权限边界仅靠前端、发布文档误导 operator。
- `P2`：硬编码使 domain 泛化困难、dev-only 默认容易误用、审计证据不完整、UX 文案让用户以为 unsupported filter 已应用。
- `P3`：可维护性或发布整洁度问题，不改变执行安全性。

## Task 1: 建立审查产物和基线

**Agent lane:** 协调 agent。

**Files:**
- Create: `docs/risk_review/2026-06-20-program-risk-review.md`
- Create: `docs/risk_review/2026-06-20-remediation-roadmap.md`

- [ ] **Step 1: 创建审查目录和报告骨架**

Run:

```bash
mkdir -p docs/risk_review
```

Use `apply_patch` to create `docs/risk_review/2026-06-20-program-risk-review.md` with exactly this starting content:

```markdown
# 程序风险审查报告（2026-06-20）

## 审查目标

本次审查检查硬编码、规则边界绕过、API/tool 权限伤害、前端误导风险、发布文档缺口。核心不变量保持不变：自然语言、前端和 LLM tool call 只能提出结构化意图，只有经过 schema grounding、RuleVerifier、confirmation loop、DuckDB executor 和 EvidencePack 边界的规则可以执行。

## 审查范围

| lane | 范围 | 负责人 |
|---|---|---|
| 后端规则管线 | Extractor 到 EvidencePack 的执行边界、hard rule 来源、candidate_id、no-schema 偏好 | Agent 1 |
| API/tool 权限 | HTTP 鉴权、LLM-safe tool、audit、路径、错误净化、schema contract | Agent 2 |
| 前端 smoke 与 UX | Vite 构建、后端 smoke、dev token、前端 hard filter 入口、确认与未执行展示 | Agent 3 |
| 文档与发布 | README、安全模型、tool contract、生产部署、release checklist、sample outputs | Agent 4 |

## 基线命令

```text
.venv/bin/python -m unittest discover -s tests
cd frontend && npm run build
git diff --check
```

## 初始硬编码扫描

```text
rg -n "(/Users/|outputs/|广东省|duckdb|localhost|127\\.0\\.0\\.1|deepseek|api[_-]?key|token|password|subprocess|shell=True|eval\\(|exec\\(|raw_sql|sql|hard_filters|confirmed_candidates|candidate_id|allow_origins|DATA_ROOT|OUTPUT_ROOT)" src frontend docs tests scripts schemas domains README.md RELEASE_CHECKLIST.md CHANGELOG.md docker-compose.yml Dockerfile Makefile
```

## 发现列表

| id | severity | lane | 文件 | 证据 | 风险 | 建议 | 状态 |
|---|---|---|---|---|---|---|---|

## 已确认安全不变量

| invariant | 证据 | 覆盖测试 |
|---|---|---|

## 残余风险

| 风险 | 原因 | 后续动作 |
|---|---|---|
```

Expected: file exists and contains the exact title `# 程序风险审查报告（2026-06-20）`.

- [ ] **Step 2: 创建整改路线图骨架**

Use `apply_patch` to create `docs/risk_review/2026-06-20-remediation-roadmap.md` with exactly this starting content:

```markdown
# 程序风险整改路线图（2026-06-20）

## 整改原则

- 不为提升命中率放松 RuleVerifier、confirmation loop 或 DuckDBExecutor 检查。
- 先补 guard test，再改生产代码。
- 每个批次只提交同一类风险，避免把文档、前端 UX 和执行管线混在一个提交里。
- 大表、DuckDB、本地 upload、`.env`、`.venv` 和临时 outputs 不进入提交。

## 批次

| batch | 目标 | 前置条件 | 测试 | 文档 | 状态 |
|---|---|---|---|---|---|

## 暂不整改项

| 风险 | 暂不整改原因 | 重新评估触发条件 |
|---|---|---|
```

Expected: file exists and contains the exact title `# 程序风险整改路线图（2026-06-20）`.

- [ ] **Step 3: 记录当前 git 状态**

Run:

```bash
git status --short
```

Expected: output is empty before review edits, or contains only user-owned changes that are unrelated to this plan. If unrelated changes appear, list them in the report under `## 残余风险` as `工作区已有未提交改动，审查提交只包含本计划产物。`

- [ ] **Step 4: 运行基线后端测试**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: all tests pass. If the command fails before review changes, add a `P1` finding with the failing test names and do not attribute the failure to a new edit.

- [ ] **Step 5: 运行基线前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build exits with code 0. If dependencies are missing, record exact stderr in the review report and run no npm install unless the repository already documents that action.

- [ ] **Step 6: 提交审查骨架**

Run:

```bash
git add docs/risk_review/2026-06-20-program-risk-review.md docs/risk_review/2026-06-20-remediation-roadmap.md
git commit -m "docs: start program risk review"
```

Expected: commit succeeds and includes only the two review documents.

## Task 2: Agent 1 审查后端规则管线边界

**Agent lane:** 后端规则管线。

**Files:**
- Read: `src/api/workbench.py`
- Read: `src/api/admissions_query_planner.py`
- Read: `src/schema/attribute_grounder.py`
- Read: `src/rules/rule_verifier.py`
- Read: `src/rules/rule_promoter.py`
- Read: `src/executors/duckdb_executor.py`
- Read: `src/reporting/evidence_pack.py`
- Modify: `docs/risk_review/2026-06-20-program-risk-review.md`
- Create or Modify: `tests/test_security_review_regressions.py`

- [ ] **Step 1: Map runtime order from code**

Run:

```bash
nl -ba src/api/workbench.py | sed -n '240,335p;1667,1823p'
nl -ba src/api/admissions_query_planner.py | sed -n '720,895p;1140,1270p'
nl -ba src/executors/duckdb_executor.py | sed -n '44,180p;220,320p'
```

Expected: output shows extraction or planned query entering verifier/confirmation before execution, and SQL built from quoted identifiers plus parameter binding markers. Add one row to `## 已确认安全不变量` for each invariant that the code and tests support.

- [ ] **Step 2: Scan backend hardcoded defaults**

Run:

```bash
rg -n "(DEFAULT_USER_INPUT|WAREHOUSE_DATABASE_PATH|WAREHOUSE_VALUE_INDEX_PATH|WORKBOOK_NAME|deepseek-v4|outputs/data|广东省|深圳大学|DEFAULT_LIMIT|score_margin|rank_margin)" src domains tests scripts
```

Expected: each result is classified as `domain fixture`, `runtime default`, `test fixture`, `release artifact`, or `risk`. Add `P2` findings for runtime defaults that make non-admissions domains or production deployment ambiguous.

- [ ] **Step 3: Add regression tests for score-only and no-schema execution boundaries**

Use `apply_patch` to create or extend `tests/test_security_review_regressions.py` with this code if the file does not already contain equivalent tests:

```python
from __future__ import annotations

import unittest

from src.api.workbench import WorkbenchConfig
from tests.warehouse_test_utils import run_workbench_with_test_warehouse


class SecurityReviewRegressionTest(unittest.TestCase):
    def test_score_only_query_is_blocked_from_recommendation_execution(self) -> None:
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input="广东物理，630分，想读计算机。",
                hard_filters={"source_province": "广东", "subject_type": "物理", "user_score": 630},
                soft_preferences={"prompt": "想读计算机"},
                extractor="regex",
            )
        )

        self.assertIn(result["status"], {"blocked", "needs_confirmation", "ok", "no_results"})
        serialized = str(result)
        self.assertNotIn("录取概率", serialized)
        self.assertNotIn("仅按分数估计风险", serialized)
        if result["query_type"] == "recommendation":
            self.assertEqual(result["debug_trace"]["execution"]["sql"], "")

    def test_no_schema_preference_never_becomes_executed_filter(self) -> None:
        prompt = "广东物理，排名3.2万，计算机相关，珠三角优先，不要校企合作。"
        first = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                extractor="regex",
                soft_preferences={"prompt": prompt},
            )
        )
        candidate_id = next(
            item["candidate_id"]
            for item in first["candidates_to_confirm"]
            if item["source_text"] == "不要校企合作"
        )
        result = run_workbench_with_test_warehouse(
            WorkbenchConfig(
                user_input=prompt,
                extractor="regex",
                soft_preferences={"prompt": prompt},
                confirmed_candidates=[candidate_id],
            )
        )

        self.assertEqual(result["rejected_confirmations"][0]["reason_code"], "candidate_not_executable")
        self.assertNotIn("合作办学类型字段", [item["field"] for item in result["executed_filters"]])
        self.assertNotIn("校企合作", str(result["debug_trace"]["execution"]["params"]))


if __name__ == "__main__":
    unittest.main()
```

Expected: this file imports only existing test helpers and does not build a new warehouse outside the existing test cache.

- [ ] **Step 4: Run the focused backend boundary tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_security_review_regressions tests.test_workbench_confirmation_loop tests.test_workbench_api_contract
```

Expected: all selected tests pass. If the first score-only test fails because current behavior executes score-only recommendation SQL, record a `P1` finding: `score-only recommendation can execute without province rank boundary`.

- [ ] **Step 5: Record Agent 1 findings**

Edit `docs/risk_review/2026-06-20-program-risk-review.md`:

```markdown
| A1-001 | P2 | 后端规则管线 | `src/api/workbench.py:90` | 内置 admissions warehouse 路径默认指向 `outputs/data/guangdong_admissions.duckdb` | 非内置 domain 或生产部署可能被误读为同一数据源 | 保持内置路径但在部署文档和 readiness 中明确需要构建 warehouse；不要静默 fallback 到 Excel/Pandas | confirmed |
```

Expected: include this row if the hardcoded path remains present after review. Add more rows only with file evidence and reproducible command output.

- [ ] **Step 6: Commit Agent 1 review artifacts**

Run:

```bash
git add docs/risk_review/2026-06-20-program-risk-review.md tests/test_security_review_regressions.py
git commit -m "test: capture backend boundary review"
```

Expected: commit includes only Agent 1 report edits and the focused regression test file.

## Task 3: Agent 2 审查 API/tool 权限与路径安全

**Agent lane:** API/tool 权限安全。

**Files:**
- Read: `src/api/server.py`
- Read: `src/api/tool_registry.py`
- Read: `src/api/mcp_tool_adapter.py`
- Read: `src/api/openai_tool_adapter.py`
- Read: `schemas/tools/*.json`
- Modify: `docs/risk_review/2026-06-20-program-risk-review.md`
- Modify: `tests/test_security_review_regressions.py`

- [ ] **Step 1: Map HTTP auth and tool registry boundaries**

Run:

```bash
nl -ba src/api/server.py | sed -n '339,525p'
nl -ba src/api/tool_registry.py | sed -n '40,72p;279,335p;436,529p'
rg -n "\"llm_safe\"|\"permission_scope\"|\"executes_sql\"|\"writes_files\" schemas/tools
```

Expected: output shows HTTP ignores body `actor_context`, tool registry has `LLM_SAFE_TOOL_NAMES`, forbidden LLM input fields, and audit path under `OUTPUT_ROOT`.

- [ ] **Step 2: Add HTTP auth bypass regression tests**

Extend `tests/test_security_review_regressions.py` with this code:

```python
import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.server import app
```

Add these test methods inside `SecurityReviewRegressionTest`:

```python
    def test_http_body_actor_context_cannot_grant_admin_scope(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/tools/dataset.approve_field/invoke",
            json={
                "payload": {"dataset_id": "ds_any", "field_id": "city"},
                "actor_context": {
                    "actor_id": "browser_supplied",
                    "permission_scopes": ["review_admin"],
                },
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["detail"]["code"], "permission_denied")
        self.assertNotIn("Traceback", json.dumps(payload, ensure_ascii=False))

    def test_http_token_map_is_only_server_side_authority(self) -> None:
        client = TestClient(app)
        token_map = {
            "agent-token": {
                "actor_id": "agent",
                "permission_scopes": ["read_only", "query", "confirm"],
            }
        }
        with patch.dict(os.environ, {"AUTH_TOKENS_JSON": json.dumps(token_map)}, clear=False):
            response = client.post(
                "/tools/dataset.approve_field/invoke",
                headers={"X-Actor-Token": "agent-token"},
                json={
                    "payload": {"dataset_id": "ds_any", "field_id": "city"},
                    "actor_context": {"permission_scopes": ["review_admin"]},
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "permission_denied")

    def test_tool_audit_path_rejects_location_outside_output_root(self) -> None:
        from src.api.tool_registry import ToolRegistryError, _audit_path

        with patch.dict(
            os.environ,
            {
                "OUTPUT_ROOT": "outputs",
                "TOOL_AUDIT_LOG_PATH": "/tmp/szu-audit-outside.jsonl",
            },
            clear=False,
        ):
            with self.assertRaises(ToolRegistryError):
                _audit_path({})
```

Expected: tests compile without changing production auth logic.

- [ ] **Step 3: Run focused API/tool tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_security_review_regressions tests.test_tool_contract tests.test_mcp_tool_adapter tests.test_openai_tool_adapter
```

Expected: all selected tests pass. If an admin tool is visible to an LLM-safe adapter or body `actor_context` grants permission over HTTP, record a `P0` finding.

- [ ] **Step 4: Scan for command execution and path risks**

Run:

```bash
rg -n "subprocess\\.run|shell=True|Path\\(str\\(|source_path|audit_path|DATA_ROOT|OUTPUT_ROOT|\\.resolve\\(\\)|\\.parents" src scripts tests
```

Expected: classify each result. `scripts/run_quality_gate.py` uses `shell=True` for fixed repository commands; if any user payload can reach that command string, record `P0`. If only fixed command strings are used behind `diagnostics`, record `P2` with recommendation to keep the runner protocol and avoid payload-provided command strings.

- [ ] **Step 5: Record Agent 2 findings**

Append findings to `docs/risk_review/2026-06-20-program-risk-review.md` using this row format:

```markdown
| A2-001 | P2 | API/tool 权限 | `Makefile:5` | 本地 `DEV_AUTH_TOKENS_JSON` 包含 operator-token 全权限 | 本地开发方便但 operator token 名称容易被误用于非本地环境 | 文档继续要求生产配置真实 `AUTH_TOKENS_JSON`；前端 dev token 保持 `import.meta.env.DEV` 限制；发布 checklist 检查生产 token | confirmed |
```

Expected: include this row if the Makefile dev token remains present. Add additional rows only with command evidence.

- [ ] **Step 6: Commit Agent 2 review artifacts**

Run:

```bash
git add docs/risk_review/2026-06-20-program-risk-review.md tests/test_security_review_regressions.py
git commit -m "test: capture tool permission review"
```

Expected: commit includes only Agent 2 report edits and regression tests.

## Task 4: Agent 3 运行前端 smoke 和 UX 边界审查

**Agent lane:** 前端 smoke 与 UX。

**Files:**
- Read: `frontend/src/App.vue`
- Read: `frontend/src/components/UserInputPanel.vue`
- Read: `frontend/src/components/DatasetIngestionPanel.vue`
- Read: `frontend/src/components/CandidateConfirmation.vue`
- Read: `frontend/src/components/ResultTable.vue`
- Read: `frontend/src/components/EvidenceReport.vue`
- Modify: `docs/risk_review/2026-06-20-program-risk-review.md`

- [ ] **Step 1: Build the frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build exits with code 0. If it fails, record `P1` if the failure blocks release, or `P2` if it is environment-only and documented.

- [ ] **Step 2: Scan frontend hardcoded defaults and auth assumptions**

Run:

```bash
rg -n "(DEFAULT_DEV_ACTOR_TOKEN|operator-token|localStorage|hard_filters|soft_preferences|confirmed_candidates|candidate_id|demoRun|mock|admissions|广东|32000|深圳大学|fetch\\()" frontend/src
```

Expected: classify each result as `demo default`, `dev auth`, `frontend display`, `API payload`, or `risk`. Frontend may compose `hard_filters`, but report any copy or control implying unsupported filters are executed without backend evidence.

- [ ] **Step 3: Run backend and frontend smoke manually**

Terminal A:

```bash
.venv/bin/python -m uvicorn src.api.server:app --reload --port 8001
```

Terminal B:

```bash
cd frontend && npm run dev
```

Expected: backend prints a running Uvicorn server on `http://127.0.0.1:8001`; Vite prints a local URL, usually `http://localhost:5173/`.

Manual smoke path:

```text
1. Open the Vite URL.
2. Keep mode as demo and confirm demo results render without API error.
3. Switch to API mode with built-in admissions data and run the default query.
4. Verify displayed status, result count, executed filters, candidate confirmations, not-executed preferences, and evidence report match API payload fields.
5. Open 上传表格 tab and verify admin buttons are visible only as operator workflow controls, not as LLM-safe actions.
6. Stop both servers with Ctrl-C after smoke.
```

Expected: no overlapping text, no blank result table after successful API response, and no copy that says no-schema preferences were applied.

- [ ] **Step 4: Verify frontend does not invent execution evidence**

Run:

```bash
rg -n "(录取概率|已应用|已执行|筛选了|推荐|不代表|未执行|只显示后端|前端只提交)" frontend/src docs README.md
```

Expected: user-facing copy should distinguish executed filters from not-executed preferences. If a component reports unsupported preference as applied, record `P1`.

- [ ] **Step 5: Record Agent 3 findings**

Append this row if the dev token default remains present:

```markdown
| A3-001 | P2 | 前端 smoke 与 UX | `frontend/src/App.vue:47`, `frontend/src/components/DatasetIngestionPanel.vue:28` | Vite dev mode 默认发送 `operator-token` | 本地 demo 方便，但如果 operator token 被部署环境接受，会扩大前端按钮权限 | 保持 `import.meta.env.DEV` 限制；生产文档要求真实 token；后续可改为显式输入本地 token | confirmed |
```

Expected: include concrete smoke result notes in `## 已确认安全不变量` or `## 残余风险`.

- [ ] **Step 6: Commit Agent 3 review artifacts**

Run:

```bash
git add docs/risk_review/2026-06-20-program-risk-review.md
git commit -m "docs: capture frontend risk review"
```

Expected: commit includes only frontend review findings in the report.

## Task 5: Agent 4 审查文档、release readiness 和产物边界

**Agent lane:** 文档与发布。

**Files:**
- Read: `README.md`
- Read: `docs/security_model.md`
- Read: `docs/tool_contract.md`
- Read: `docs/production_deployment.md`
- Read: `RELEASE_CHECKLIST.md`
- Read: `release_manifest.json`
- Read: `sample_outputs/README.md`
- Read: `CHANGELOG.md`
- Modify: `docs/risk_review/2026-06-20-program-risk-review.md`
- Modify if stale: `README.md`
- Modify if stale: `docs/security_model.md`
- Modify if stale: `docs/tool_contract.md`
- Modify if stale: `docs/production_deployment.md`
- Modify if stale: `RELEASE_CHECKLIST.md`

- [ ] **Step 1: Search public docs for stale behavior claims**

Run:

```bash
rg -n "(Pandas|DuckDB|LLM-safe|candidate_id|permission_scopes|operator-token|AUTH_TOKENS_JSON|EvidencePack|raw Excel|outputs/data|DeepSeek|score|位次|录取概率|未执行|校企合作|中外合作)" README.md docs RELEASE_CHECKLIST.md CHANGELOG.md sample_outputs release_manifest.json
```

Expected: each doc claim matches current code and test behavior. Record stale claims as `P1` when they could mislead execution or security decisions, otherwise `P2` or `P3`.

- [ ] **Step 2: Verify release package does not include local-only artifacts**

Run:

```bash
git ls-files | rg "(^outputs/|\\.duckdb$|\\.env$|\\.venv|uploaded_datasets|tool_audit|广东省2025年志愿填报大数据)"
```

Expected: no generated output directories, `.env`, `.venv`, uploaded datasets, or DuckDB files are tracked. If the large admissions workbook is intentionally tracked, confirm `README.md` and `release_manifest.json` describe it; otherwise record `P1`.

- [ ] **Step 3: Run release validation commands**

Run:

```bash
.venv/bin/python scripts/validate_release_package.py
.venv/bin/python scripts/export_tool_manifest.py --output-path outputs/tool_manifest/review_tool_manifest.json
.venv/bin/python scripts/export_openapi.py --output-path outputs/openapi/review_openapi.json
```

Expected: validation exits with code 0; generated review manifests stay under `outputs/` and are not staged.

- [ ] **Step 4: Update stale docs in Chinese when confirmed**

If docs are stale, edit only the affected sections. Use this exact wording when documenting the dev token boundary:

```markdown
本地 Vite 开发模式会默认发送 `operator-token`，只用于配合 `make serve` 的本机演示。生产部署不得接受示例 token，必须通过服务端 `AUTH_TOKENS_JSON` 配置真实 token，并在网关或运维系统中控制 operator token 的分发。
```

Expected: docs remain Chinese except commands, identifiers, field names and protocol terms.

- [ ] **Step 5: Record Agent 4 findings**

Append doc findings to `docs/risk_review/2026-06-20-program-risk-review.md`. If no stale docs are found, add this invariant row:

```markdown
| 文档边界 | `docs/security_model.md`、`docs/tool_contract.md`、`docs/production_deployment.md` 均说明 HTTP 只信任服务端 `AUTH_TOKENS_JSON`，不信任 body `actor_context.permission_scopes` | `tests.test_security_review_regressions` |
```

Expected: every public behavior claim touched by the review is either confirmed or corrected.

- [ ] **Step 6: Commit Agent 4 review artifacts**

Run:

```bash
git add docs/risk_review/2026-06-20-program-risk-review.md README.md docs/security_model.md docs/tool_contract.md docs/production_deployment.md RELEASE_CHECKLIST.md
git diff --cached --name-only
git commit -m "docs: capture release readiness review"
```

Expected: commit includes only changed docs. If a listed doc did not change, Git does not stage it.

## Task 6: 汇总发现并生成整改路线图

**Agent lane:** 协调 agent。

**Files:**
- Modify: `docs/risk_review/2026-06-20-program-risk-review.md`
- Modify: `docs/risk_review/2026-06-20-remediation-roadmap.md`

- [ ] **Step 1: Normalize severity and deduplicate findings**

Run:

```bash
rg -n "^\\| A[1-4]-" docs/risk_review/2026-06-20-program-risk-review.md
```

Expected: each finding has one id, severity, lane, file evidence, risk, recommendation and status. Merge duplicate findings by keeping the lower id and adding extra file evidence to the same row.

- [ ] **Step 2: Fill remediation batches**

Edit `docs/risk_review/2026-06-20-remediation-roadmap.md` with batches in this order:

```markdown
| batch | 目标 | 前置条件 | 测试 | 文档 | 状态 |
|---|---|---|---|---|---|
| R1 | 修复 P0/P1 执行或权限边界问题 | 审查报告存在 P0/P1 confirmed findings | 对应 focused unittest 先失败后通过；`python -m unittest discover -s tests` | `docs/security_model.md`、`docs/tool_contract.md`、`README.md` | ready_if_needed |
| R2 | 降低 hardcoded domain 和 dev token 误用风险 | P0/P1 清零 | hardcoded regression tests；frontend build | `docs/production_deployment.md`、`RELEASE_CHECKLIST.md` | ready |
| R3 | 改善前端证据展示和 operator UX | API contract 未变或 snapshot 同步更新 | frontend build；manual smoke notes | `README.md`、`docs/demo_script.md` | ready |
| R4 | 发布包清理和 release evidence 更新 | R1-R3 已完成 | `make release-check` 或等价命令集 | release evidence 与 evaluation docs | ready |
```

Expected: if no P0/P1 findings exist, R1 status remains `ready_if_needed` and no production code is changed for R1.

- [ ] **Step 3: Add final review summary**

Append this section to the report:

```markdown
## 汇总结论

- P0 数量：
- P1 数量：
- P2 数量：
- P3 数量：
- 可以直接进入整改的批次：
- 暂不整改但需要发布说明的风险：
```

Then replace each count and line with concrete values from the findings table. If a count is zero, write `0`.

Expected: the summary contains no empty values.

- [ ] **Step 4: Run full verification**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
cd frontend && npm run build
git diff --check
```

Expected: all commands pass. If frontend dependencies are unavailable, record that in the report and still run backend tests plus `git diff --check`.

- [ ] **Step 5: Commit the consolidated roadmap**

Run:

```bash
git add docs/risk_review/2026-06-20-program-risk-review.md docs/risk_review/2026-06-20-remediation-roadmap.md
git commit -m "docs: summarize risk review roadmap"
```

Expected: commit includes only the two risk review documents.

## Task 7: Decide execution mode for remediation

**Agent lane:** 用户与协调 agent。

**Files:**
- Read: `docs/risk_review/2026-06-20-program-risk-review.md`
- Read: `docs/risk_review/2026-06-20-remediation-roadmap.md`

- [ ] **Step 1: Present the confirmed findings**

Run:

```bash
sed -n '/## 发现列表/,/## 已确认安全不变量/p' docs/risk_review/2026-06-20-program-risk-review.md
sed -n '/## 批次/,$p' docs/risk_review/2026-06-20-remediation-roadmap.md
```

Expected: user can see confirmed findings and proposed remediation batches without opening files manually.

- [ ] **Step 2: Ask user to choose remediation style**

Offer exactly these two choices:

```text
1. Subagent-Driven：每个 remediation batch 用独立 subagent 执行，主线程在每批后 review。
2. Inline Execution：当前线程按 R1、R2、R3、R4 顺序执行，每批后停下来核对 diff。
```

Expected: no production remediation starts until user chooses a style or explicitly asks to execute a specific batch.

## 自检

- Spec coverage: 本计划覆盖用户提出的四类 agent review，并补充了审查产物、基线验证、回归测试、发布文档和整改批次。
- 禁用占位词扫描：本计划没有保留空白待补项；报告中的空表是审查执行时逐条追加的结构化产物。
- Type consistency: 所有新增测试使用 `SecurityReviewRegressionTest`、`WorkbenchConfig`、`run_workbench_with_test_warehouse`、`TestClient(app)` 和现有 API 字段名；`candidate_id`、`confirmed_candidates`、`hard_filters`、`evidence_pack` 与当前 contract 一致。
