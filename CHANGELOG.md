# 变更日志

## 未发布（2026-06-28）

### 新增

- 新增独立本地用户 Web：普通用户先上传本机 Excel/CSV，再基于本机生成的 queryable 数据源进入查询页，不加载旧 mock/demo 数据源。
- 新增 macOS 本机 `.app` 构建入口，`make macos-app` 会打包本地用户 Web 静态产物、必要后端源码快照和 Library runtime。
- 新增 OpenAI-compatible LLM provider 模板：`deepseek`、`qwen`、`kimi`、`zhipu`、`qianfan` 和 `hunyuan`；本地设置页可选择 provider 并保存本机密钥。
- Admissions recommendation 增加 career guidance 证据层：保留家庭资源、就业目标、考公/稳定就业等偏好，但在缺少 reviewed schema 字段时只进入 `EvidencePack` 和前端提示，不生成 hard rule。
- 新增 `career_decision_policy.json`、`career_guidance` reporting 和相关前端展示，支持解释资源行业、资源城市、就业目标等待补充信息。
- `/api/workbench/options` 增加受控 `rank_windows` 和 `sort_modes`；前端必须从后端白名单选择排位窗口和排序方式后才能提交 admissions 查询。
- 新增 `decision_option_suggestions` evidence-only 建议：后端可以建议 `rank_window` / `sort_mode` 选项，前端只展示“建议先确认”，不自动改写表单或触发查询。
- DuckDBExecutor 和 admissions recommendation planner 增加受控排序策略，支持 `rank_asc`、`rank_desc` 和 `school_rank_asc`，排序字段均来自 reviewed schema/helper 白名单。

### 变更

- DeepSeek runtime hardcode 改为通用 OpenAI-compatible client；旧 `DEEPSEEK_*` 环境变量继续兼容，新的 `LLM_PROVIDER`、`LLM_API_KEY`、`LLM_MODEL` 和 `LLM_API_URL` 为通用配置入口。
- Uploaded dataset 的 LLM planner 默认模型改为走本机 LLM 设置，不再在 service 层固定旧 DeepSeek model alias。
- Admissions recommendation 严格执行“有分数但无位次时先追问省排位”，不再用分数单独估计录取风险。
- 前端显式提交的 `rank_window_*` 改为只使用上界执行；例如排位 `1000` 且 `rank_window_upper_percent=15` 生成 `专业组最低位次1 <= 1150`，`rank_window_lower_percent` 仅作为 UI 档位提示。
- 旧兼容字段 `safety_margin_percent` 继续表示对称窗口；新受控 `rank_window_*` 必须匹配后端 `rank_windows` 白名单，上界不在白名单或小数百分比会返回 Workbench `error` contract。
- Admissions recommendation 的 `items`、`top_results`、`EvidencePack.top_k_results` 改为来自同一批 section-selected rows，避免与 `result_sections` 在分桶截断时不一致。
- 前端输入面板将排位窗口和排序从可选偏好改为必选受控项，并阻止自由文本排序值进入 API payload。

### 修复

- 修复本地用户数据源列表重复展示同一上传文件的问题，按文件 fingerprint 折叠并保留最新可查询版本。
- 修复高排位考生在“稳一点”等窗口下因百分比下界过窄导致结果被错误筛空的问题。
- 修复 `school_rank_asc` 在 recommendation 路径中已暴露但未执行的问题；缺少 reviewed `school_rank` 时保持安全回退。
- 修复 career guidance 中否定表达、模糊就业偏好和 DeepSeek slot 的边界，避免把“不要求好就业”等文本误提为可执行偏好。
- 修复 rank-only / score-only recommendation intent routing，确保强制 recommendation 也遵守排位优先规则。
- 修复前端 rank window 文案、warning 识别、mock/demo 文本和 API contract 描述，统一为“只执行后向上界”。

### 验证

- 已跑通真实 DeepSeek 全流程：slot adapter 有真实 token usage；上传 96335 行、17 列 admissions Excel 后，`llm_semantic` preflight 为 `ready`，query 为 `ok`，planner 记录 `provider=deepseek`、`fallback_used=false`，缺 schema 的“不想去国外”保持未执行。
- 已运行 `make release-check`，release package 静态校验通过。
- 新增和更新 `tests/test_admissions_query_types.py`、`tests/test_workbench_api_contract.py`、`tests/test_rule_verifier.py`、`tests/test_duckdb_executor.py`、`tests/test_api_workbench.py`、`tests/test_career_guidance.py` 等回归覆盖。
- 本轮 release refresh 已运行 `.venv/bin/python -m unittest discover -s tests`，结果为 `598 tests OK (expected failures=1)`。
- 本轮 release refresh 已运行 `make frontend-user-build` 和 `make macos-app`，独立本地用户 Web 与 macOS `.app` 构建通过；主前端 build 在 Quality Gate 中退出码为 0，仅保留既有 Vite/Rollup warning。

## v0.1.0-rc1 候选

本候选版本把项目包装为 `LLM-safe structured data query tool server for Excel/CSV`，面向前端、LLM/agent 和 operator 提供受控 functional tools。

### 新增

- 多领域 `WorkbenchResponse` contract，固定 `items`、`top_results`、`result_sections`、`EvidencePack` 和 status enum。
- `DomainConfig` + domain pack 抽象，admissions、housing、products 共用同一套 schema grounding、RuleVerifier、DuckDB execution 和 answer contract。
- `scripts/generate_domain_pack.py` 和 `scripts/review_domain_pack.py`，支持 CSV/Excel 生成 draft pack、人工 review、approve/block 和 audit history。
- Uploaded dataset flow：上传、profile、draft generation、review、approve、build warehouse、query。
- Real dataset pilot 和 operator trial，覆盖真实招生 Excel 的 sheet/header/profile/review/build/query 试运行；operator trial 报告包含 `manual_checkpoints` 和常见失败处理建议。
- Functional tool contracts：`dataset.profile`、`dataset.review_summary`、`workbench.query`、`workbench.confirm`、`evidence.get` 等。
- OpenAI-compatible tools export、MCP adapter 和 fake agent 黑盒 acceptance。
- HTTP tool server 部署层：`/tools/list`、`/tools/{tool_name}/schema`、`/tools/{tool_name}/invoke`、`/healthz`、`/readyz`、`/version`。
- 生产部署基础：`Dockerfile`、`docker-compose.yml`、生产部署说明、安全模型和备份恢复文档。
- 统一 Quality Gate：语法检查、unit tests、regex evaluator、demo acceptance、domain review、warehouse fingerprint guard、前端 build。
- Release package：`release_manifest.json`、`sample_data/`、`sample_outputs/`、`RELEASE_CHECKLIST.md` 和 `docs/demo_script.md`。
- 前端主查询页支持选择已 build 且 `queryable` 的 uploaded admissions 数据源；上传页完成后只传递 `dataset_id` / `domain_name`，不在前端生成推荐规则。

### 安全边界

- LLM-safe tools 默认只暴露读取、查询、确认和 EvidencePack 读取能力。
- admin/review/warehouse/diagnostics tools 必须由 operator/admin 权限触发。
- HTTP 鉴权只信任服务端 `AUTH_TOKENS_JSON` token 映射，不信任浏览器或 LLM payload 的 `permission_scopes`。
- `dataset.upload` tool 只接受 `content_base64`，默认禁用服务端 `source_path` 读取。
- warehouse build 使用 dataset 级锁和原子发布，避免并发读写造成不一致。
- audit log 使用固定路径、文件锁、大小限制和轮转策略。
- draft、needs_review、blocked domain pack 不能执行 SQL。
- confirmed candidate 只能引用上一轮系统生成的 `candidate_id`。
- `no_schema_field_preferences` 永远不能执行。
- SQL 必须参数化；LLM 不能生成 SQL、hard rules 或 approved ops。
- 结构化 Excel/CSV 走 DuckDB warehouse、schema profile 和 schema/value index，不把大表全量 embedding。

### 发布前必须运行

```bash
make release-check
make demo
make pilot
make operator-trial
make agent-acceptance
make quality
```

最终 release tag 建议使用 `v0.1.0-rc1`，但只有在 Quality Gate、operator trial 和真实数据 pilot 均通过后再创建。
