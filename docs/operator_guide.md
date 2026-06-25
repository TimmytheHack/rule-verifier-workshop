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

生产服务端只信任 `AUTH_TOKENS_JSON` 中配置的 token 映射。浏览器、LLM 或请求体传来的
`permission_scopes`、`actor_id` 不授予权限。`make serve` 会提供本地开发 token，本地 Vite 开发模式会默认发送 `operator-token`，只用于配合 `make serve` 的本机演示。生产部署不得接受示例 token，必须通过服务端 `AUTH_TOKENS_JSON` 配置真实 token，并在网关或运维系统中控制 operator token 的分发。也可以把其他本地 token 放入 `localStorage.actor_token` 覆盖默认值；生产前端应由真实登录态或网关注入 token，不能把 admin token 暴露给普通 LLM/agent。

## 上传与 profile

HTTP 上传：

```bash
curl -X POST \
  "http://127.0.0.1:8001/datasets/upload?filename=admissions.xlsx" \
  -H "Authorization: Bearer <operator-token>" \
  --data-binary @admissions.xlsx
```

tool invoke 上传只接受 HTTP/body/base64 内容，不读取服务端本地 `source_path`：

```json
{
  "payload": {
    "filename": "admissions.xlsx",
    "content_base64": "<base64 encoded file bytes>"
  }
}
```

返回的 `dataset_id` 和 `source_fingerprint` 是后续所有步骤的主键。`dataset_id` 只允许字母、数字、下划线和连字符，不能覆盖内置 `admissions`、`housing`、`products`。

查看 profile：

```bash
curl \
  -H "Authorization: Bearer <operator-token>" \
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
  -H "Authorization: Bearer <operator-token>" \
  http://127.0.0.1:8001/datasets/<dataset_id>/generate-domain-pack \
  -d '{"domain_name":"admissions","template_id":"admissions_schema_v1","llm":"off"}'
```

`template_id=admissions_schema_v1` 只复用已审查的招生字段模板、规则模板和展示映射；
数据行仍然只来自上传文件，不读取内置 admissions 表格。旧 `base_domain=admissions`
仅保留为兼容入口，新流程不再要求 operator 填写。生成结果仍是 `needs_review`。
seed aliases、seed ops、seed templates 只能作为审查输入，不会自动成为可执行 hard filter。

## 审查 summary

```bash
curl \
  -H "Authorization: Bearer <operator-token>" \
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
  -H "Authorization: Bearer <operator-token>" \
  http://127.0.0.1:8001/datasets/<dataset_id>/approve-field \
  -d '{"field_id":"city","note":"城市字段已核对"}'
```

批准单个 op：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <operator-token>" \
  http://127.0.0.1:8001/datasets/<dataset_id>/approve-op \
  -d '{"field_id":"city","op":"in","note":"低基数字段，可执行 in"}'
```

阻断字段：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <operator-token>" \
  http://127.0.0.1:8001/datasets/<dataset_id>/block-field \
  -d '{"field_id":"phone","note":"PII 字段"}'
```

批准 domain：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <operator-token>" \
  http://127.0.0.1:8001/datasets/<dataset_id>/approve-domain \
  -d '{"title_field":"university_name","primary_fields":["group_code","major_name","city"],"sort_field":"min_rank"}'
```

## 构建 warehouse

```bash
curl -X POST \
  -H "Authorization: Bearer <operator-token>" \
  http://127.0.0.1:8001/datasets/<dataset_id>/build-warehouse
```

`build-warehouse` 会加 dataset 级锁，原子发布 DuckDB、schema/value index 和 ingestion
summary，并校验 source fingerprint。fingerprint 不一致时状态为 `blocked`，不能 query。

## 查询

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  http://127.0.0.1:8001/workbench/query \
  -d '{"dataset_id":"<dataset_id>","domain_name":"admissions","user_input":"列出25年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数","extractor":"regex"}'
```

或者通过 tool server：

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <agent-token>" \
  http://127.0.0.1:8001/tools/workbench.query/invoke \
  -d '{"payload":{"dataset_id":"<dataset_id>","domain":"admissions","natural_language":"我今年高考分数630，想读计算机，想留在广东省","deterministic_fields":{"user_score":630}}}'
```

前端等价路径：上传表格页完成 approve 和 build 后，如果数据集进入 `queryable`，主查询页会把
该 `dataset_id` 作为 admissions 数据源调用同一个 `/workbench/query`。如果本地
`DATA_ROOT` 被清理，浏览器里保存的 uploaded 数据源会失效，需要切回内置 admissions 或重新上传。

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
检测、missing/risky fields、`manual_checkpoints`、常见失败处理、审批记录、warehouse fingerprint、两条目标 admissions query、
warnings 和 failures。trial 通过后仍需继续执行 demo acceptance、real dataset pilot 和
Quality Gate。

候选发布前还应阅读 `RELEASE_CHECKLIST.md`，确认 `sample_data/`、`sample_outputs/`、
`release_manifest.json` 和 `docs/demo_script.md` 已更新。只有完整 checklist 通过后，才创建
候选 tag。
