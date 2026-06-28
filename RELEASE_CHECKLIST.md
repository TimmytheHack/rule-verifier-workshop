# 发布检查清单

本文用于 `LLM-safe structured data query tool server for Excel/CSV` 候选发布。所有步骤都应由 operator 或 maintainer 执行，LLM/agent 不应自动调用 admin tools。

## 0. 当前候选证据

候选 tag：`v0.1.0-rc1`。精简证据见：

```text
sample_outputs/release_candidate_evidence.json
sample_outputs/quality_gate_summary.json
sample_outputs/operator_trial_summary.md
```

必须确认：

- [ ] `make bootstrap` 通过，`.venv` 和 requirements 可用。
- [ ] `make serve` 通过，`/healthz`、`/readyz`、`/version` 可访问，`llm_safe_only=true` 只返回五个 LLM-safe tools。
- [ ] `make demo` 通过：29/29 pass；admissions 19、housing 5、products 5；uploaded dataset acceptance 2。
- [ ] `make pilot` 通过：`ds_real_pilot_real_like_admissions_pil` 的 source fingerprint 与 warehouse fingerprint 一致。
- [ ] `make operator-trial` 通过：`20260615_071741` fixture 覆盖 sheet/header/profile/review/approve/build/query 卡点。
- [ ] `make agent-acceptance` 通过：fake agent 调用 `dataset.approve_op` 被 `tool_not_allowed` 拒绝。
- [ ] `make quality` 通过：11 pass、0 fail、1 warning；唯一 warning 是既有前端 build warning。
- [ ] `make frontend-user-build` 通过，本地用户 Web 静态产物已更新。
- [ ] `make macos-app` 通过，重新生成本机 `.app` 和 Library runtime 快照。
- [ ] DeepSeek live flow smoke 通过：slot adapter 有真实 token usage，uploaded admissions `llm_semantic` preflight/query 记录 `provider=deepseek`、`fallback_used=false`，且缺 schema 的偏好保持未执行。
- [ ] `make clean-artifacts` 后没有临时 quality/operator/agent/audit/warehouse/upload 产物留在工作区。
- [ ] 内置 admissions 覆盖：`make demo` admissions 19/19 pass。
- [ ] uploaded admissions 覆盖：`make demo` uploaded 2/2 pass，`make pilot` real-like admissions fixture pass。
- [ ] housing/products 覆盖：`make demo` housing 5/5 pass，products 5/5 pass。
- [ ] draft blocked 覆盖：Quality Gate `domain_pack_validate`、`tests/test_uploaded_dataset_flow.py` 和 `tests/test_workbench_api_contract.py`。
- [ ] stale fingerprint 覆盖：Quality Gate `warehouse_fingerprint_guard`、`tests/test_data_warehouse_guard.py` 和 `tests/test_uploaded_dataset_flow.py`。
- [ ] `no_schema_field` 不执行覆盖：`tests/test_workbench_api_contract.py` 和 `tests/test_workbench_confirmation_loop.py`。
- [ ] agent 不能调用 admin tools 覆盖：`make agent-acceptance` 的 `admin_permission_denied` case。

## 1. 环境

- [ ] 当前分支干净，未混入临时 report、DuckDB、上传原件、密钥或 `.venv`。
- [ ] `.env.example` 不包含真实密钥。
- [ ] `ENABLE_LLM=false` 为默认值。
- [ ] 生产环境已配置 `AUTH_TOKENS_JSON`，且不会信任浏览器传来的 `permission_scopes`。
- [ ] `DATA_ROOT`、`OUTPUT_ROOT`、`TOOL_AUDIT_LOG_PATH` 和 audit 轮转参数已指向持久化目录。
- [ ] 生产默认 `ENABLE_LLM=false`；如启用 LLM，只使用已配置的 OpenAI-compatible provider 模板和本机密钥，不提交密钥。
- [ ] 已确认不接入 BGE 或向量库；结构化 Excel/CSV 仍走 DuckDB warehouse、schema/value index 和 reviewed semantic verifier。

## 2. 静态发布包

```bash
make release-check
```

必须确认：

- [ ] `release_manifest.json` 可读取。
- [ ] `sample_data/` 只包含小型脱敏 CSV 和说明。
- [ ] `sample_outputs/` 只包含稳定示例，不包含真实大表或本机绝对路径。
- [ ] `Dockerfile`、`docker-compose.yml`、`docs/production_deployment.md`、`docs/security_model.md` 和 `docs/backup_restore.md` 已更新。
- [ ] `CHANGELOG.md`、`RELEASE_CHECKLIST.md` 和 `docs/demo_script.md` 已更新。
- [ ] 多 provider LLM 模板、DeepSeek live smoke、本地用户 Web 和 macOS `.app` 口径已同步到 release docs。

## 3. Functional Tool Server

```bash
make serve
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
```

必须确认：

- [ ] `/readyz` 通过 data root、tool schemas、DomainConfig 和 Quality Gate 基础依赖检查。
- [ ] `/version` 返回 `api_version=api.v1`、`schema_version=workbench_response.v1`、`tool_contract_version=tools.v1`。
- [ ] `/tools/list?llm_safe_only=true` 只返回五个 LLM-safe tools。
- [ ] admin tool 调用必须使用 `Authorization: Bearer <operator-token>` 或 `X-Actor-Token`，旧 `X-Permission-Scopes` 与 body `actor_context.permission_scopes` 不授予权限。
- [ ] `dataset.upload` tool 只接受 `content_base64`，不接受服务端 `source_path` 读取。

## 4. Demo 与 Agent 验收

```bash
make demo
make agent-acceptance
make frontend-user-build
make macos-app
```

必须确认：

- [ ] demo acceptance admissions / housing / products 全部通过。
- [ ] uploaded dataset acceptance 两条 admissions 目标查询通过。
- [ ] fake agent 只能 list/profile/review/query/confirm/evidence。
- [ ] fake agent 调用 admin tools 被权限拒绝。
- [ ] 本地用户 Web 不展示旧 mock/demo 数据源；设置页支持 DeepSeek、通义千问 / DashScope、Kimi / Moonshot、智谱 GLM、百度千帆和腾讯混元 provider 模板。
- [ ] `.app` 包不复制仓库 `.env`、上传原件、outputs 临时产物、内置 demo domain pack 或质量/pilot 诊断工具。

## 5. 真实数据试运行

使用 fixture：

```bash
make pilot
make operator-trial
```

使用真实招生 Excel：

```bash
.venv/bin/python scripts/run_operator_trial.py path/to/admissions.xlsx
.venv/bin/python scripts/run_real_dataset_pilot.py path/to/admissions.xlsx
```

使用真实 DeepSeek：

```bash
ENABLE_LLM=true .venv/bin/python scripts/run_deepseek_slot_probe.py
```

必须确认：

- [ ] sheet list、detected header row、重复列、空行空列、合并单元格、隐藏行列、公式单元格 warning 已审查。
- [ ] required admissions fields 无缺失，或已记录 blocker。
- [ ] risky fields 已人工 approve/block。
- [ ] warehouse fingerprint 与 source fingerprint 一致。
- [ ] `group_detail_report` 写入 query_type、SQL、params、metric、group_by、sort 和 nested_result_count。
- [ ] recommendation 只有分数没有位次时保留 warning，不声称录取概率。
- [ ] `不想去国外`、中外合作、国际班、境外培养、校企合作等偏好只有 approved schema 字段存在时才执行。
- [ ] DeepSeek 只提出 slots、`SemanticIntent`、evidence requirement 分类或候选 `RankingPlan`；不能生成 SQL、hard rules、approved ops 或最终推荐结论。

## 6. Quality Gate

```bash
make quality
```

必须确认：

- [ ] Python 语法检查通过。
- [ ] unit tests 通过。
- [ ] regex evaluator 为 `320/320`。
- [ ] unit tests 和 API contract tests 摘要以本轮 `outputs/quality_gate/tmp/latest/report.json` 为准，且均为 pass。
- [ ] demo acceptance 全部 pass。
- [ ] domain pack validate 和 review workflow smoke 通过。
- [ ] warehouse fingerprint guard smoke 通过。
- [ ] `git diff --check` 通过。
- [ ] 前端 build 退出码为 0；既有 Vite/Rollup warning 只记录为 warning。
- [ ] gate 报告写入 `outputs/quality_gate/tmp/latest/`，且 gate 会在运行中新产物改脏工作区时失败。

## 7. 清理与提交

```bash
make clean-artifacts
git status --short
```

必须确认：

- [ ] 没有临时 audit、临时 uploaded dataset、临时 warehouse 或本机 report 进入 commit。
- [ ] 没有 `outputs/quality_gate/tmp/latest/`、tool audit 轮转文件或临时 upload 原件进入 commit。
- [ ] `make quality` 后 `git status --short` 仍为空，说明 gate 未把干净工作区改脏。
- [ ] 只 stage 本次 release package 相关文件。
- [ ] commit message 简洁明确。

## 8. Tag

只有在以上所有步骤通过后，再创建候选 tag：

```bash
git tag -a v0.1.0-rc1 -m "v0.1.0-rc1"
```

如果 release 前又修改了 contract、sample data、docs 或 Quality Gate 行为，必须重新跑本 checklist。
