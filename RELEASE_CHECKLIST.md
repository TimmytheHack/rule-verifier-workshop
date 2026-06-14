# 发布检查清单

本文用于 `LLM-safe structured data query tool server for Excel/CSV` 候选发布。所有步骤都应由 operator 或 maintainer 执行，LLM/agent 不应自动调用 admin tools。

## 1. 环境

- [ ] 当前分支干净，未混入临时 report、DuckDB、上传原件、密钥或 `.venv`。
- [ ] `.env.example` 不包含真实密钥。
- [ ] `ENABLE_LLM=false` 为默认值。
- [ ] 已确认不会接入 Qwen、BGE、向量库或外部 LLM API。

## 2. 静态发布包

```bash
make release-check
```

必须确认：

- [ ] `release_manifest.json` 可读取。
- [ ] `sample_data/` 只包含小型脱敏 CSV 和说明。
- [ ] `sample_outputs/` 只包含稳定示例，不包含真实大表或本机绝对路径。
- [ ] `CHANGELOG.md`、`RELEASE_CHECKLIST.md` 和 `docs/demo_script.md` 已更新。

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

## 4. Demo 与 Agent 验收

```bash
make demo
make agent-acceptance
```

必须确认：

- [ ] demo acceptance admissions / housing / products 全部通过。
- [ ] uploaded dataset acceptance 两条 admissions 目标查询通过。
- [ ] fake agent 只能 list/profile/review/query/confirm/evidence。
- [ ] fake agent 调用 admin tools 被权限拒绝。

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

必须确认：

- [ ] sheet list、detected header row、重复列、空行空列、合并单元格、隐藏行列、公式单元格 warning 已审查。
- [ ] required admissions fields 无缺失，或已记录 blocker。
- [ ] risky fields 已人工 approve/block。
- [ ] warehouse fingerprint 与 source fingerprint 一致。
- [ ] `group_detail_report` 写入 query_type、SQL、params、metric、group_by、sort 和 nested_result_count。
- [ ] recommendation 只有分数没有位次时保留 warning，不声称录取概率。
- [ ] `不想去国外`、中外合作、国际班、境外培养、校企合作等偏好只有 approved schema 字段存在时才执行。

## 6. Quality Gate

```bash
make quality
```

必须确认：

- [ ] Python 语法检查通过。
- [ ] unit tests 通过。
- [ ] regex evaluator 为 `320/320`。
- [ ] demo acceptance 全部 pass。
- [ ] domain pack validate 和 review workflow smoke 通过。
- [ ] warehouse fingerprint guard smoke 通过。
- [ ] `git diff --check` 通过。
- [ ] 前端 build 退出码为 0；既有 Vite/Rollup warning 只记录为 warning。

## 7. 清理与提交

```bash
make clean-artifacts
rm -f outputs/eval/fuzzy_eval_results.audit_tmp.json
git status --short
```

必须确认：

- [ ] 没有临时 audit、临时 uploaded dataset、临时 warehouse 或本机 report 进入 commit。
- [ ] 只 stage 本次 release package 相关文件。
- [ ] commit message 简洁明确。

## 8. Tag

只有在以上所有步骤通过后，再创建候选 tag：

```bash
git tag -a v0.1.0-rc1 -m "v0.1.0-rc1"
```

如果 release 前又修改了 contract、sample data、docs 或 Quality Gate 行为，必须重新跑本 checklist。
