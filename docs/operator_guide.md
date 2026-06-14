# Operator 操作指南

本文面向拥有 `dataset_write`、`review_admin`、`warehouse_admin` 或 `diagnostics` 权限的 operator。LLM/agent 不应自动调用管理类工具。

## 权限边界

| permission_scope | 可执行操作 |
|---|---|
| `read_only` | 查看 profile、review summary、EvidencePack。 |
| `query` | 调用 `workbench.query`。 |
| `confirm` | 调用 `workbench.confirm`。 |
| `dataset_write` | 上传文件、生成 draft domain pack。 |
| `review_admin` | approve/block 字段、op、domain。 |
| `warehouse_admin` | build warehouse。 |
| `diagnostics` | run quality gate 或 real dataset pilot。 |

所有 tool invoke 都写入 audit event，字段包括 `actor_id`、`tool_name`、`dataset_id`、`status`、`duration_seconds`、`side_effects` 和 `error_code`。audit log 不记录原始上传内容、环境变量或密钥。

本地前端的 uploaded dataset 面板是 operator demo 面板，会带 `frontend_operator` 和所需管理权限 header 调用后端。生产前端应改为由真实登录态或网关注入权限，不能把 admin 权限暴露给普通 LLM/agent。

## 上传与 profile

HTTP 上传：

```bash
curl -X POST \
  "http://127.0.0.1:8001/datasets/upload?filename=admissions.xlsx" \
  -H "X-Actor-Id: operator" \
  -H "X-Permission-Scopes: dataset_write" \
  --data-binary @admissions.xlsx
```

tool invoke 上传：

```json
{
  "payload": {
    "filename": "admissions.xlsx",
    "source_path": "/safe/path/admissions.xlsx"
  },
  "actor_context": {
    "actor_id": "operator",
    "permission_scopes": ["dataset_write"]
  }
}
```

返回的 `dataset_id` 和 `source_fingerprint` 是后续所有步骤的主键。`dataset_id` 只允许字母、数字、下划线和连字符，不能覆盖内置 `admissions`、`housing`、`products`。

查看 profile：

```bash
curl \
  -H "X-Actor-Id: operator" \
  -H "X-Permission-Scopes: read_only" \
  http://127.0.0.1:8001/datasets/<dataset_id>/profile
```

profile 应重点检查：

- sheet list 和 selected sheet；
- `detected_header_row` 和 header detection warning；
- 字段 dtype、空值率、唯一值数量、样例值；
- PII、高基数、自由文本、特殊计划相关风险；
- 重复列名和原始列名映射。

## 生成 draft domain pack

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: operator" \
  -H "X-Permission-Scopes: dataset_write" \
  http://127.0.0.1:8001/datasets/<dataset_id>/generate-domain-pack \
  -d '{"base_domain":"admissions","llm":"off"}'
```

生成结果仍是 `needs_review`。seed aliases、seed ops、seed templates 只能作为审查输入，不会自动成为可执行 hard filter。

## 审查 summary

```bash
curl \
  -H "X-Actor-Id: reviewer" \
  -H "X-Permission-Scopes: read_only" \
  http://127.0.0.1:8001/datasets/<dataset_id>/review-summary
```

审查时必须确认：

- 至少一个 item title mapping；
- 至少一个 primary attribute mapping；
- sort policy 非空，或显式使用 default safe sort；
- admissions 必需字段是否 present；
- “中外合作 / 国际班 / 境外培养 / 合作办学 / 校企合作 / 地方专项 / 专项计划”等字段是否存在且经过批准。

## approve / block

批准字段：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: reviewer" \
  -H "X-Permission-Scopes: review_admin" \
  http://127.0.0.1:8001/datasets/<dataset_id>/approve-field \
  -d '{"field_id":"city","note":"城市字段已核对"}'
```

批准单个 op：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: reviewer" \
  -H "X-Permission-Scopes: review_admin" \
  http://127.0.0.1:8001/datasets/<dataset_id>/approve-op \
  -d '{"field_id":"city","op":"in","note":"低基数字段，可执行 in"}'
```

阻断字段：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: reviewer" \
  -H "X-Permission-Scopes: review_admin" \
  http://127.0.0.1:8001/datasets/<dataset_id>/block-field \
  -d '{"field_id":"phone","note":"PII 字段"}'
```

批准 domain：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: reviewer" \
  -H "X-Permission-Scopes: review_admin" \
  http://127.0.0.1:8001/datasets/<dataset_id>/approve-domain \
  -d '{"title_field":"university_name","primary_fields":["group_code","major_name","city"],"sort_field":"min_rank"}'
```

## 构建 warehouse

```bash
curl -X POST \
  -H "X-Actor-Id: warehouse_admin" \
  -H "X-Permission-Scopes: warehouse_admin" \
  http://127.0.0.1:8001/datasets/<dataset_id>/build-warehouse
```

`build-warehouse` 会生成 DuckDB、schema/value index、ingestion summary，并校验 source fingerprint。fingerprint 不一致时状态为 `blocked`，不能 query。

## 查询

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: agent" \
  -H "X-Permission-Scopes: query" \
  http://127.0.0.1:8001/workbench/query \
  -d '{"dataset_id":"<dataset_id>","domain_name":"admissions","user_input":"列出25年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数","extractor":"regex"}'
```

或者通过 tool server：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  http://127.0.0.1:8001/tools/workbench.query/invoke \
  -d '{"payload":{"dataset_id":"<dataset_id>","domain":"admissions","natural_language":"我今年高考分数630，想读计算机，想留在广东省","deterministic_fields":{"user_score":630}},"actor_context":{"actor_id":"agent","permission_scopes":["query"]}}'
```

前端和 agent 应优先读取 `items`、`result_sections`、`warnings` 和 `evidence_pack`。`top_results` 只作为 domain-specific 兼容层。

## 发布流程

正式发布前按顺序执行：

```text
generate draft
-> review / approve
-> run operator trial
-> run release package check
-> run demo acceptance
-> run real dataset pilot
-> run quality gate
-> commit / release
```

命令入口：

```bash
make release-check
make demo
make operator-trial
make pilot
make quality
```

真实招生 Excel 首次接入时，建议先运行 operator trial：

```bash
.venv/bin/python scripts/run_operator_trial.py path/to/admissions.xlsx
```

报告输出到 `outputs/operator_trial/<run_id>/report.md` 和 `report.json`。operator 应结合
`docs/operator_trial_checklist.md` 和 `docs/operator_feedback_template.md` 检查 sheet/header
检测、missing/risky fields、审批记录、warehouse fingerprint、两条目标 admissions query、
warnings 和 failures。trial 通过后仍需继续执行 demo acceptance、real dataset pilot 和
Quality Gate。

候选发布前还应阅读 `RELEASE_CHECKLIST.md`，确认 `sample_data/`、`sample_outputs/`、
`release_manifest.json` 和 `docs/demo_script.md` 已更新。只有完整 checklist 通过后，才创建
候选 tag。
