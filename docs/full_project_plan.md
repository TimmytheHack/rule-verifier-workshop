# 完整项目规划

本文档保留项目的设计边界和后续研究方向。它不是产品路线图承诺，也不把当前 MVP 描述成完整志愿填报顾问。

## 项目定位

工作标题：

```text
Preference-to-Rule Verification for Structured Decision Systems
```

当前案例：

```text
基于一个 Excel 数据集的广东高考志愿填报场景。
```

主要贡献：

```text
防止模糊或缺少 schema 支持的自然语言偏好被不安全地提升为确定性可执行规则。
```

## 运行时核心

运行时路径保持小而清晰：

```text
Extractor
-> AttributeGrounder
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> Executor
-> TraceGenerator
```

必须保留的边界：

- `RegexExtractor` 只是 benchmark baseline。
- `DeepSeekExtractor` 只能抽取偏好和 source span。
- Attribute grounding 在 rule construction 之前审查抽取出的 attributes。
- Rule verifier 是 schema 接地和 executability 的唯一执行门。
- Candidate rules 需要确认后才能 promotion。
- Executor 只接收已验证的可执行规则。
- Workbench hard rules 由 DuckDB executor 执行；pandas executor 只作为 MVP demo、评估对照和测试工具。
- Workbench 执行前必须通过 DuckDB metadata、schema/value index metadata 和源 Excel fingerprint 一致性校验；校验失败时返回 structured warning，不静默回退。
- Confirmation loop 只能使用上一轮系统生成的 `candidate_id`；确认后也只能执行该 candidate 对应的已审查字段和值，不能执行用户二次输入的自由文本。

## 离线工具

这些工具支持研究、评估和 schema review，不属于运行时执行路径：

| 工具 | 作用 |
|---|---|
| `scripts/profile_excel_schema.py` | 扫描 Excel 列并生成字段目录。 |
| `scripts/build_data_warehouse.py` | 构建本地 DuckDB 数据仓库、schema/value index 和 ingestion summary。 |
| `schemas/excel_schema_profile.json` | 供 schema review 使用的机器可读 profile。 |
| `docs/excel_schema_profile.md` | 供人工阅读的 schema profile。 |
| `outputs/data/ingestion_summary.json` | 记录数据摄取 source path、fingerprint、行列数、field profiles 和 created_at。 |
| `scripts/eval_modes.py` | 单条输入的方法对比。 |
| `scripts/eval_fuzzy_inputs.py` | 40-case benchmark 对比。 |
| `scripts/eval_pipeline_token_budget.py` | token budget 对比。 |

## 主要文档

项目保留以下中文 canonical 文档：

| 文档 | 用途 |
|---|---|
| `docs/methodology_report.md` | 当前方法论和安全边界。 |
| `docs/evaluation_report.md` | 当前实验结果。 |
| `docs/excel_schema_profile.md` | 从 Excel 数据集生成的字段目录。 |
| `docs/end_to_end_demo_cases.md` | demo case matrix 和预期规则处理方式。 |

## 当前评估计划

Benchmark 继续保持分层：

- 清晰 deterministic 输入；
- 模糊 candidate-rule 输入；
- 缺少 schema 支持的输入；
- 混合输入；
- adversarial 输入；
- 矛盾输入；
- 端到端 demo 输入。

对比方法：

1. `regex_extractor_symbolic_verifier`
2. `deepseek_extractor_symbolic_verifier`
3. `llm_only_baseline`
4. `schema_aware_llm_only_baseline`

主要安全指标：

```text
deterministic over-promotion rate
```

辅助指标：

- schema hallucination rate；
- candidate holding accuracy；
- non-executable rejection accuracy；
- trace completeness；
- token budget 下的 task success。

## 当前主线优先级

当前主线按以下顺序推进：

| 优先级 | 任务 | 状态 |
|---|---|---|
| P0 | confirmation loop：`partial_match` 通过 `candidate_id` 确认后才可进入 hard filter | 已实现基础闭环 |
| P1 | API response contract freeze + snapshot tests | 已实现基础 contract |
| P2 | demo acceptance script，导出多领域 Markdown/JSON 验收报告 | 已实现，当前覆盖内置 domain 27 条和 uploaded dataset 2 条 |
| P3 | 多数据源 ingestion 规范，支持新 Excel / CSV 进入同一 warehouse schema | 已实现 draft generator、Domain Pack Review / Approval workflow、uploaded dataset API/service flow 和 real dataset pilot |
| P4 | 统一 Quality Gate，交付前运行测试、评估、demo acceptance、domain/warehouse guard 和前端 build | 已实现 |
| P4.5 | 真实招生 Excel 上传、profile、审查、建仓、目标查询 pilot | 已实现，输出 `outputs/real_dataset_pilot/report.md` 与 `report.json` |
| P4.6 | LLM/agent/前端可调用 functional tool layer 和机器可读 tool contracts | 已实现，见 `src/api/tool_registry.py`、`schemas/tools/*.json`、`docs/tool_contract.md` |
| P4.7 | release packaging + tool server deployment hardening | 已实现，包含 `Makefile`、`.env.example`、`/tools/*`、`/healthz`、`/readyz`、`/version`、OpenAPI/tool manifest 导出和 operator/troubleshooting 文档 |
| P4.8 | Agent Adapter + Black-box Tool-use Acceptance | 已实现，包含 OpenAI-compatible tools export、MCP adapter 和 `scripts/run_agent_tool_acceptance.py` |
| P5 | 非结构化政策/章程小型知识库，只做解释和候选，不进执行 | 待做 |
| P6 | 可选模型/embedding 接入 | 暂不接入 |

## 后续研究方向

这些方向仍然有价值，但不应被理解为已经完成的能力：

1. Review `docs/excel_schema_profile.md`。
2. 通过 `scripts/review_domain_pack.py` 将可信 candidate fields promotion 到 approved domain pack。
3. 为每个 promotion field 和 approved op 增加测试。
4. 将 40-case benchmark 扩展到 50-100 条更真实的改写表达。
5. 在更长、更乱、不完整和矛盾输入上 stress-test DeepSeek extraction。
6. 将 recommendation quality evaluation 与 rule-verification evaluation 分开。
7. 在不改变执行边界的前提下，把 uploaded dataset review UI 从当前 sheet/header/risk 摘要面板演进为更完整的人工审查工作台。
8. 如需接入外部 agent runtime，可以基于当前 `/tools/list`、`/tools/{tool_name}/schema`、`/tools/{tool_name}/invoke`、OpenAI-compatible tools export 或 MCP adapter 做集成；adapter 必须复用 `schemas/tools/*.json` 和现有权限模型。

当前 benchmark snapshot：

| 方法 | 得分 | Over-promotion |
|---|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.275 |

## 暂不建设的内容

以下内容如果没有新的 schema、规则策略和测试，不应作为当前系统能力描述：

- 完整志愿表 generation。
- 没有 reviewed schema 的学校声誉排序逻辑。
- 就业预测。
- Web-search augmentation。
- 多轮 advisor UI。
- 通用 symbolic AI。
- 只为提高 benchmark 分数而增加更多 regex special cases。
