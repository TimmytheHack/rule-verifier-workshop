# 安全模型

本项目的安全边界是：自然语言、前端和 LLM tool call 都只能提出结构化意图；是否执行由 schema grounding、RuleVerifier、confirmation loop、DuckDB executor 和 EvidencePack 边界控制。

## 权限模型

HTTP 服务端只信任 `AUTH_TOKENS_JSON` 中配置的 token 映射。每个 token 映射到一个 `actor_id` 和一组 `permission_scopes`。

| scope | 能力 |
|---|---|
| `read_only` | 读取 profile、review summary、EvidencePack。 |
| `query` | 调用 Workbench query。 |
| `confirm` | 使用上一轮系统生成的 `candidate_id` 重跑确认。 |
| `dataset_write` | 上传文件、生成 draft domain pack。 |
| `review_admin` | approve/block field 或 op，approve domain。 |
| `warehouse_admin` | 构建 DuckDB warehouse 和 schema/value index。 |
| `diagnostics` | 运行质量门禁或 pilot 类诊断工具。 |

浏览器或 LLM 传来的 `permission_scopes` 不授予权限。进程内测试和维护脚本可以直接调用 `ToolRegistry` 并传入受信任 `actor_context`，但 HTTP 层不会接受这些字段作为授权依据。

本地 Vite 开发模式会默认发送 `operator-token`，只用于配合 `make serve` 的本机演示。生产部署不得接受示例 token，必须通过服务端 `AUTH_TOKENS_JSON` 配置真实 token，并在网关或运维系统中控制 operator token 的分发。

## LLM-safe Tools

默认暴露给 LLM/agent 的工具只有：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

`dataset.upload`、`dataset.generate_domain_pack`、`approve-*`、`dataset.build_warehouse`、`quality.run` 和 `pilot.run` 不属于 LLM-safe tools。即使用户提示要求“直接批准字段”或“直接执行 SQL”，agent 也不能把这些工具加入默认工具集。

## 执行边界

- draft、needs_review、blocked domain pack 不执行 SQL。
- `confirmed_candidate_ids` 只能引用当前 query 生成的 `candidate_id`。
- `no_schema_field_preferences` 永远不能执行。
- `partial_match` 只有在 candidate_id 被确认并再次通过 RuleVerifier 后才能执行。
- DeepSeek slot adapter 默认关闭；启用时只补缺失 slots，不覆盖 deterministic slots，不生成 SQL、hard rules 或 executable rules。
- `EvidencePack` 是答案生成唯一输入；答案不能读取 raw Excel。

## 文件与路径边界

- 上传数据只能写入 `DATA_ROOT`。
- tool audit 只能写入服务端固定 `TOOL_AUDIT_LOG_PATH`。
- `dataset.upload` tool 只接受 `content_base64`，不读取服务端 `source_path`。
- DuckDB warehouse 构建使用 dataset 级文件锁和 atomic publish。
- 大型原始文件、DuckDB、本地上传目录、`.env` 和 `.venv` 不进入提交。

## 仍需外部系统承担的边界

本仓库提供 token 到 scope 的服务端映射，但不实现完整用户目录、OIDC、MFA、审计查询后台或网关级 rate limit。生产环境应在反向代理或 API 网关层补充：

- TLS；
- 用户登录和 token 签发；
- IP / 用户 / token 级 rate limit；
- 访问日志和告警；
- secret 管理；
- 只允许 operator 控制台访问 admin token。
