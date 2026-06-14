# 下一阶段路线

本文记录当前清理后的执行路线。项目定位保持不变：`LLM-safe structured data query tool server for Excel/CSV`。LLM 只能辅助自然语言交互和候选解释，不能生成 SQL、不能 approve、不能绕过 RuleVerifier。

## 已清理范围

- 旧版 `outputs/answer_demo/` 静态回答对比产物已从版本库移除。
- 旧版 `outputs/mvp_demo/` 生成文件已从版本库移除，只保留 `AGENTS.override.md`。
- Python cache、`.pyc` 和 `.DS_Store` 属于本地运行缓存，由 `.gitignore` 和 `make clean-artifacts` 覆盖。
- `scripts/run_answer_demo.py`、`scripts/run_mvp_demo.py` 和相关测试仍保留；需要旧演示时本地重跑，不把产物作为当前交付基线。

## 当前交付基线

交付前以这些入口为准：

```bash
make demo
make pilot
make agent-acceptance
make release-check
make quality
```

`outputs/demo_acceptance/`、`outputs/real_dataset_pilot/`、`outputs/quality_gate/tmp/latest/` 和 `sample_outputs/` 仍保留为当前验收与发布证据。`outputs/data/*.duckdb`、demo acceptance warehouse、quality gate warehouse、uploaded dataset 和 audit scratch 继续保持本地生成、默认不提交。

## 接下来优先路线

1. Production Hardening 收尾：在现有 Docker、持久化目录、服务端 token 鉴权、audit log rotation、warehouse build lock / atomic publish 和生产文档基础上，继续补 rate-limit stub、反向代理 TLS/CORS 策略和生产观测。
2. Operator Trial 收敛：用真实招生 Excel 继续跑 `scripts/run_operator_trial.py`，记录 sheet/header/profile/review/approve/build/query 的人工卡点，补齐 operator checklist 中的失败样例和处理建议。
3. Frontend Operator UI 收敛：强化 audit log、review required/risky/missing fields、warehouse status、EvidencePack 展示和 `needs_confirmation` 交互；继续要求前端只展示 `items`、`result_sections` 和 evidence，不生成推荐逻辑。
4. Release Readiness：稳定 `make bootstrap`、`make serve`、`make demo`、`make pilot`、`make quality`、`make clean-artifacts`；更新 release manifest、demo script 和 sample outputs，准备 release tag。
5. Final Acceptance：覆盖内置 admissions、uploaded admissions、messy real-like Excel、housing/products、draft blocked、stale fingerprint blocked、needs_confirmation、no_schema_field not executed、agent cannot call admin tools、quality gate pass、frontend build pass。

## 暂停边界

DeepSeek slot adapter 已作为第一步适配：默认仍由 `ENABLE_LLM=false` 禁用，显式开启后只补 missing slots，并在进入 Workbench 前做 schema 校验和禁止字段检查。

以下事项进入前需要单独确认：

- OpenAI-compatible local endpoint、Qwen via vLLM 或其他 provider adapter。
- 任何 embedding、BGE、向量库或结构化大表 RAG。
- 让 LLM 输出 executable rules、hard filters、approved ops 或 SQL。

即使未来扩展更多 LLM provider，也必须保持 `ENABLE_LLM=false` 默认，LLM 输出只补 missing slot 或 candidate explanation，并通过 jsonschema、AttributeGrounder、RuleVerifier 和 confirmation loop。
