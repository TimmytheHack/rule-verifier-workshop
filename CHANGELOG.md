# 变更日志

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
