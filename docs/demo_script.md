# 演示脚本

本文用于向 operator、前端开发者或 agent 集成方演示本项目。演示重点是 functional tools、schema review、confirmation loop、EvidencePack 和 Quality Gate，不展示 LLM 自动执行 SQL。

## 演示前准备

```bash
make bootstrap
make release-check
```

确认：

- `ENABLE_LLM=false`；
- 不配置 DeepSeek、Qwen、BGE 或向量库；
- `release_manifest.json`、`sample_data/`、`sample_outputs/` 校验通过；
- 当前工作区没有临时 report 或密钥文件。

## 候选发布验收顺序

`v0.1.0-rc1` 候选发布建议按以下顺序验收：

```bash
make bootstrap
make release-check
make serve
make demo
make pilot
make operator-trial
make agent-acceptance
make quality
make clean-artifacts
git status --short
```

候选证据位置：

```text
sample_outputs/release_candidate_evidence.json
sample_outputs/quality_gate_summary.json
sample_outputs/operator_trial_summary.md
outputs/demo_acceptance/report.md
outputs/demo_acceptance/report.json
outputs/real_dataset_pilot/report.md
outputs/real_dataset_pilot/report.json
outputs/operator_trial/<run_id>/report.md
outputs/operator_trial/<run_id>/report.json
outputs/agent_tool_acceptance/report.md
outputs/agent_tool_acceptance/report.json
outputs/quality_gate/tmp/latest/report.md
outputs/quality_gate/tmp/latest/report.json
```

`outputs/operator_trial/`、`outputs/agent_tool_acceptance/` 和 `outputs/quality_gate/tmp/`
是临时验收产物，发布前应由 `make clean-artifacts` 清理；`sample_outputs/` 只保留精简候选摘要。

## 1. Tool Server 启动

```bash
make serve
```

另开终端：

```bash
curl http://127.0.0.1:8001/healthz
curl http://127.0.0.1:8001/readyz
curl http://127.0.0.1:8001/version
curl "http://127.0.0.1:8001/tools/list?llm_safe_only=true"
```

讲解点：

- `/readyz` 是部署就绪探针，不替代 Quality Gate。
- `/version` 固定暴露 `api_version`、`schema_version`、`tool_contract_version`。
- `llm_safe_only=true` 只返回 `dataset.profile`、`dataset.review_summary`、`workbench.query`、`workbench.confirm`、`evidence.get`。
- admin tools 默认对 LLM 不可见。

## 2. Demo Acceptance

```bash
make demo
```

打开：

```text
outputs/demo_acceptance/report.md
outputs/demo_acceptance/report.json
```

讲解点：

- admissions、housing、products 共享统一 `items` contract。
- admissions 的 `top_results` 仍保留 `university_name`、`group_code`、`major_name` 等兼容字段。
- `needs_confirmation` 的 partial match 不进入 `executed_filters`。
- `no_results` 不编造推荐。

## 3. Operator Trial

使用 fixture：

```bash
make operator-trial
```

使用真实 Excel：

```bash
.venv/bin/python scripts/run_operator_trial.py path/to/admissions.xlsx
```

打开：

```text
outputs/operator_trial/<run_id>/report.md
outputs/operator_trial/<run_id>/report.json
```

讲解点：

- 上传后先看 sheet list、detected header row 和 warnings。
- review summary 明确 required fields、missing fields、risky fields。
- `safe_auto_suggest_approvals` 只是人工审查建议，不会自动变成 executable hard filters。
- build warehouse 后必须通过 fingerprint guard。
- 两条目标 query 分别展示 `group_detail_report` 和 `recommendation`。
- `recommendation` 的冲/稳/保来自历史最低分/最低位次 margin，`EvidencePack` 会记录 `margin_policy`、`year_weighting`、`major_match` 和 `bucket_counts`，演示时不能把它讲成录取概率。

## 4. Agent Tool Acceptance

```bash
make agent-acceptance
```

打开：

```text
outputs/agent_tool_acceptance/report.md
outputs/agent_tool_acceptance/report.json
```

讲解点：

- fake agent 可以 profile、review_summary、query、confirm 和 evidence。
- fake agent 不能调用 approve、build、quality、pilot 等 admin tools。
- `workbench.confirm` 只能引用上一轮系统生成的 `candidate_id`。
- 伪造或过期 candidate id 会被 structured rejection / blocked。

## 5. 前端演示

```bash
make serve
cd frontend
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

讲解点：

- 前端展示 API 输出，不发明推荐逻辑。
- 主列表优先读取 `items` 和 `result_sections`。
- `top_results` 只做 admissions 兼容层。
- warnings、blocked、no_results 和 no-schema preferences 必须清楚展示。

## 6. Quality Gate

```bash
make quality
```

打开：

```text
outputs/quality_gate/tmp/latest/report.md
outputs/quality_gate/tmp/latest/report.json
```

讲解点：

- regex evaluator 必须保持 `320/320`。
- API contract tests 包含在 unit tests 中，并由 gate 单独摘要。
- demo acceptance 必须全部 pass。
- approved domain 可执行，draft/needs_review 不能执行。
- warehouse fingerprint 不一致时 gate fail。
- `generated_artifact_consistency` 必须 pass，表示 gate 运行没有新增 tracked artifact diff。
- 前端 build 退出码必须为 0；既有 Vite/Rollup warning 只作为 warning 展示。

## 7. 演示收尾

```bash
make clean-artifacts
git status --short
```

确认没有临时 audit、临时 warehouse、上传原件、真实大表或本地路径 report 被准备提交。
