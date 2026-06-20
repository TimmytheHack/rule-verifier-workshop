# 程序风险审查报告（2026-06-20）

## 审查目标

本次审查检查硬编码、规则边界绕过、API/tool 权限伤害、前端误导风险、发布文档缺口。核心不变量保持不变：自然语言、前端和 LLM tool call 只能提出结构化意图，只有经过 schema grounding、RuleVerifier、confirmation loop、DuckDB executor 和 EvidencePack 边界的规则可以执行。

## 审查范围

| 审查线 | 范围 | 负责人 |
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

备注：该命令会扫描 `docs`，因此本报告内命令文本导致的 `docs/risk_review` 自匹配属于预期误报，分诊时忽略。

## 发现列表

| 编号 | 严重级别 | 审查线 | 文件 | 证据 | 风险 | 建议 | 状态 |
|---|---|---|---|---|---|---|---|
| A1-001 | P2 | 后端规则管线 | `src/api/workbench.py:90` | 内置 admissions warehouse 路径默认指向 `outputs/data/guangdong_admissions.duckdb` | 非内置 domain 或生产部署可能被误读为同一数据源 | 保持内置路径但在部署文档和 readiness 中明确需要构建 warehouse；不要静默 fallback 到 Excel/Pandas | confirmed |
| A1-002 | P1 | 后端规则管线 | `src/api/admissions_query_planner.py:852` | `.venv/bin/python -m unittest tests.test_security_review_regressions tests.test_workbench_confirmation_loop tests.test_workbench_api_contract` 显示 `test_score_only_query_is_blocked_from_recommendation_execution` 为 expected failure；score-only recommendation 仍生成 `score_margin` SQL 并返回结果 | 用户只有分数没有省排时，系统可执行推荐 SQL，违反“只给分数应要求省排”的 domain rule，且容易被解读为风险评估 | planned recommendation 在缺少 `user_rank` 时应返回 blocked/needs_confirmation，并保留“需要省排” warning；修复前保留 expected-failure regression | confirmed |
| A1-003 | P2 | 后端规则管线 | `src/api/workbench.py:54`、`src/api/workbench.py:107`、`src/api/workbench.py:109` | 硬编码扫描命令命中 admissions 中文默认 query 和 `model="deepseek-v4-flash"`；代码审查同时确认 `domain_name="admissions"` | API/server 默认值带有 admissions 演示语境，非 admissions domain 或生产调用若未显式传参会产生领域歧义 | 部署文档和 readiness 明确生产必须显式配置 domain、dataset、model；必要时将 demo default 与生产 API default 分离 | confirmed |
| A2-001 | P2 | API/tool 权限 | `Makefile:5` | 本地 `DEV_AUTH_TOKENS_JSON` 包含 operator-token 全权限 | 本地开发方便但 operator token 名称容易被误用于非本地环境 | 文档继续要求生产配置真实 `AUTH_TOKENS_JSON`；前端 dev token 保持 `import.meta.env.DEV` 限制；发布 checklist 检查生产 token | confirmed |
| A2-002 | P0 | API/tool 权限 | `src/api/tool_registry.py:347`、`scripts/run_quality_gate.py:62`、`scripts/run_quality_gate.py:215` | `quality.run` 从 payload 读取 `output_dir`，`run_quality_gate` 将该路径插入 shell command，`SubprocessRunner` 使用 `shell=True` | diagnostics 权限 actor 提供的 `output_dir` 可进入 shell command 字符串；当前仅拒绝 `..`，不足以阻断 shell metacharacters | 改为 argv list 执行或对所有 shell 参数做严格 allowlist/quoting；修复前不要向不可信 actor 授予 `diagnostics` | confirmed |

## 已确认安全不变量

| 安全不变量 | 证据 | 覆盖测试 |
|---|---|---|
| legacy Workbench 路径在执行前完成 extraction、AttributeGrounder、candidate_id confirmation、RuleVerifier、RulePromoter | `nl -ba src/api/workbench.py | sed -n '240,335p;1667,1823p'`：`_extract_slots` 后进入 `AttributeGrounder.ground`，`_resolve_confirmed_candidates` 只接受当前 `candidate_id`，`verifier.attach_verification` 通过后才加入 `confirmed_rules`，最后 `_execute_verified_hard_rules` 执行 | `tests.test_workbench_confirmation_loop`、`tests.test_workbench_api_contract`、`tests.test_security_review_regressions` |
| no-schema preference 即使带 `candidate_id` 确认也不会进入 executed filters 或 SQL params | `src/api/workbench.py:1694` 对 `executable=False` candidate 返回 `candidate_not_executable`；回归测试确认“不要校企合作”不进入 `executed_filters` 和 execution params | `tests.test_security_review_regressions.SecurityReviewRegressionTest.test_no_schema_preference_never_becomes_executed_filter` |
| DuckDB SQL 使用受控字段引用和参数绑定，不拼接用户值 | `nl -ba src/api/admissions_query_planner.py | sed -n '720,895p;1140,1270p'` 与 `nl -ba src/executors/duckdb_executor.py | sed -n '44,180p;220,320p'`：表/列经 `_quote` 或 `_quote_identifier`，用户值进入 `?` placeholders 和 `params` | `tests.test_admissions_query_types` 已覆盖“深圳大学”在 params 而不在 SQL；本轮 focused suite 覆盖 confirmation 后参数不含 no-schema 文本 |
| HTTP tool 权限只信任服务端 token map，不信任请求体 `actor_context` 提权 | `nl -ba src/api/server.py | sed -n '405,469p;472,516p'`：`_actor_context_from_request` 丢弃 `body_context`，actor 与 scopes 只来自 `AUTH_TOKENS_JSON` token map；无 token 时为 anonymous 空权限 | `tests.test_security_review_regressions.SecurityReviewRegressionTest.test_http_body_actor_context_cannot_grant_admin_scope`、`tests.test_security_review_regressions.SecurityReviewRegressionTest.test_http_token_map_is_only_server_side_authority` |
| LLM-safe adapters 只暴露白名单 tool，review/admin、warehouse、diagnostics tool 不进入默认 LLM tool surface | `nl -ba src/api/tool_registry.py | sed -n '40,72p;436,529p'` 与 `rg -n '"llm_safe"|"permission_scope"|"executes_sql"|"writes_files"' schemas/tools`：`LLM_SAFE_TOOL_NAMES` 只含 profile/review/query/confirm/evidence，admin/write/diagnostics contracts 标为 `llm_safe=false` | `.venv/bin/python -m unittest tests.test_security_review_regressions tests.test_tool_contract tests.test_mcp_tool_adapter tests.test_openai_tool_adapter` |
| tool audit log 路径默认限制在 `OUTPUT_ROOT` 内 | `src/api/tool_registry.py:516` 到 `src/api/tool_registry.py:529` 对非 trusted internal audit path 做 traversal 检查、相对路径归一到 repo root，并校验 resolved path 位于 `OUTPUT_ROOT` 下 | `tests.test_security_review_regressions.SecurityReviewRegressionTest.test_tool_audit_path_rejects_location_outside_output_root` |

## 残余风险

| 风险 | 原因 | 后续动作 |
|---|---|---|
| score-only recommendation 仍可执行 | planned query path 在 `inputs.rank` 缺失但 `inputs.score` 存在时使用 `score_margin` 窗口执行 SQL；本轮回归测试以 expected failure 固化该缺陷 | 下一任务修复 planner 阻断逻辑后移除 `expectedFailure` |
| 内置 admissions 默认值需要生产显式覆盖 | `DEFAULT_USER_INPUT`、warehouse path、value index path、default domain/model 都偏演示环境 | 发布文档、readiness 和部署配置中声明必须预构建并显式选择 domain/dataset/model |
| diagnostics quality runner 存在 shell command 注入面 | `quality.run` payload 的 `output_dir` 可进入 `scripts/run_quality_gate.py` 中的 shell command 字符串 | 修复 A2-002 前将 `diagnostics` 权限视为高危内部权限，不暴露给浏览器、LLM-safe adapter 或不可信自动化 |
