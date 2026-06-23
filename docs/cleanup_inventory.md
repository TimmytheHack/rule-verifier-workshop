# 临时、占位与无用项盘点

更新时间：2026-06-23

本文只锁定清理对象，不直接要求删除。后续删除前应按本清单逐项确认引用关系、测试影响和发布证据边界。

## 可直接清理的本地产物

这些文件或目录不应进入版本库，当前也没有被 `git status` 报为待提交内容：

| 路径 | 类型 | 依据 | 建议动作 |
| --- | --- | --- | --- |
| `src/**/__pycache__/`、`scripts/**/__pycache__/`、`tests/**/__pycache__/` | Python 缓存 | `.gitignore` 已覆盖；`make clean-artifacts` 已覆盖 | 可随时清理 |
| `*.pyc` | Python 缓存 | `.gitignore` 已覆盖；`make clean-artifacts` 已覆盖 | 可随时清理 |
| `frontend/dist/` | 前端构建产物 | `frontend/.gitignore` 已覆盖 | 可随时清理 |
| `frontend/node_modules/` | 前端依赖目录 | `frontend/.gitignore` 已覆盖 | 不提交；缺空间时可删除后重装 |
| `outputs/data/*.duckdb` | 本地 DuckDB 仓库 | 根 `.gitignore` 已覆盖；可由脚本重建 | 可清理，清理后需重建仓库再跑内置 admissions |
| `outputs/demo_acceptance/uploaded_datasets/` | demo acceptance 临时上传数据 | 根 `.gitignore` 与 `make clean-artifacts` 已覆盖 | 可随时清理 |
| `outputs/demo_acceptance/uploaded_sources/` | demo acceptance 临时源文件 | 根 `.gitignore` 与 `make clean-artifacts` 已覆盖 | 可随时清理 |
| `outputs/demo_acceptance/warehouses/` | demo acceptance 临时仓库 | 根 `.gitignore` 与 `make clean-artifacts` 已覆盖 | 可随时清理 |
| `outputs/real_dataset_pilot/fixtures/` | pilot fixture 生成目录 | 根 `.gitignore` 已覆盖 | 可随时清理 |
| `outputs/real_dataset_pilot/uploaded_datasets/` | pilot 临时上传数据 | 根 `.gitignore` 已覆盖 | 可随时清理 |
| `outputs/uploaded_datasets/` | 本地上传数据 | 根 `.gitignore` 已覆盖 | 可随时清理 |
| `outputs/tool_audit/` | 本地 tool audit | 根 `.gitignore` 与 `make clean-artifacts` 已覆盖 | 可随时清理 |
| `outputs/eval/deepseek_fuzzy_cache.json` | DeepSeek evaluator 缓存 | 根 `.gitignore` 已覆盖 | 可清理 |
| `outputs/eval/fuzzy_quick_*.json` | 快速 eval 临时结果 | 根 `.gitignore` 已覆盖 | 可清理 |
| `outputs/eval/fuzzy_deepseek_extractor_results.json` | DeepSeek fuzzy 临时结果 | 根 `.gitignore` 已覆盖 | 若不是当前报告证据，可清理 |

## 需要产品或发布决策的候选项

这些不是普通本地垃圾；删除会影响内置 demo、文档、测试或 release evidence。

| 路径 | 当前状态 | 风险 | 决策建议 |
| --- | --- | --- | --- |
| `广东省2025年志愿填报大数据（24-25）0523.xlsx` | tracked，大约 8.3MB；`domains/admissions/domain.json` 和 README 引用 | 真实大表直接进仓，与“大文件和本地数据默认不提交”的边界有张力 | 高优先级：替换为小型脱敏 fixture，或明确写入 release policy |
| `outputs/data/schema_value_index.json` | tracked；内置 admissions value index | 指向根目录真实 Excel；删除会影响内置 admissions 能力 | 与上面的 Excel 一起处理，不能单独删 |
| `outputs/data/ingestion_summary.json` | tracked；内置 admissions 摄取摘要 | 同样指向根目录真实 Excel | 与上面的 Excel 一起处理，不能单独删 |
| `outputs/demo_acceptance/report.json`、`outputs/demo_acceptance/report.md` | tracked；demo acceptance 证据 | 体积较大，但 release evidence 引用 | 保留或改成 `sample_outputs/` 摘要；不要当普通临时文件删 |
| `outputs/real_dataset_pilot/report.json`、`outputs/real_dataset_pilot/report.md` | tracked；pilot 证据 | release evidence 和文档引用 | 保留或改成精简摘要 |
| `outputs/eval/deepseek_token_usage.jsonl` | tracked；LLM token 证据 | API-backed run 后会增长，容易混入无关 token 记录 | 只在作为报告证据时保留；否则转为本地忽略 |
| `outputs/eval/eval_modes.json`、`outputs/eval/fuzzy_eval_results.json`、`outputs/eval/pipeline_token_budget.json` | tracked；评估证据 | 删除会影响评估报告可追溯性 | 当前保留 |
| `sample_outputs/*` | tracked；release package 样例输出 | release manifest 和 release check 依赖 | 当前保留 |

## 看起来像占位但仍被使用

这些名称包含 `demo`、`mock`、`legacy` 或 toy domain，但当前仍有明确用途，不应在未改测试和文档前删除。

| 路径或概念 | 用途 | 结论 |
| --- | --- | --- |
| `frontend/src/mock/demo_run.json` | 前端显式“查看演示数据”使用；测试要求 mock 不默认展示 | 保留 |
| `frontend/src/mock/eval_summary.json` | 前端评估摘要展示 mock | 保留，除非去掉对应 UI |
| `domains/housing/`、`domains/products/` | 多领域 demo acceptance、release check、generic domain 测试 | 保留 |
| `sample_data/` | release package 的小型脱敏样例 | 保留 |
| `scripts/run_mvp_demo.py` | 旧 MVP demo 可重跑；`docs/next_route.md` 已说明产物不再提交 | 暂保留 |
| `scripts/run_answer_demo.py` | 回答生成对比 demo，可本地重跑 | 暂保留 |
| `planner_mode="legacy"` | 受控 planner 模式，不是废弃代码 | 保留 |
| `PandasExecutor` | legacy MVP demo、评估对比和 focused tests 仍需要 | 保留 |

## 已发现的文档口径问题

- `docs/risk_review/2026-06-20-program-risk-review.md` 曾记录 tracked 文件未命中真实大表；当前 `git ls-files` 已能命中 `广东省2025年志愿填报大数据（24-25）0523.xlsx`。如果决定保留该文件，需要更新风险文档；如果决定移除，需要同步更新 `domains/admissions/domain.json`、README、schema profile 和相关输出证据。
- `make clean-artifacts` 已覆盖多数 outputs 临时目录，但还没有清理 `frontend/dist/` 和 `outputs/data/*.duckdb`。如果希望一条命令清完本地垃圾，可扩展该目标。

## 建议清理顺序

1. 先只清理本地产物：缓存、`frontend/dist/`、临时上传目录、临时 DuckDB、quick eval 缓存。
2. 再处理真实招生 Excel 和 `outputs/data/*.json` 的边界：要么替换为脱敏 fixture，要么明确声明它是仓库内置数据资产。
3. 最后再评估 tracked `outputs/` 报告是否缩减为 `sample_outputs/` 摘要，避免 release evidence 和测试同时断裂。
