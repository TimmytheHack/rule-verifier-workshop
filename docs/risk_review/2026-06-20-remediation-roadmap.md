# 程序风险整改路线图（2026-06-20）

## 整改原则

- 不为提升命中率放松 RuleVerifier、confirmation loop 或 DuckDBExecutor 检查。
- 先补 guard test，再改生产代码。
- 每个批次只提交同一类风险，避免把文档、前端 UX 和执行管线混在一个提交里。
- 大表、DuckDB、本地 upload、`.env`、`.venv` 和临时 outputs 不进入提交。

## 批次

| 批次 | 目标 | 前置条件 | 测试 | 文档 | 状态 |
|---|---|---|---|---|---|
| R1 | 修复 P0/P1 执行或权限边界问题：A2-002、A1-002 | 审查报告存在 confirmed P0/P1 findings | 对应 expected-failure unittest 先失败后通过；`.venv/bin/python -m unittest discover -s tests` | `docs/security_model.md`、`docs/tool_contract.md`、`README.md`、`docs/risk_review/2026-06-20-program-risk-review.md` | ready |
| R2 | 降低 hardcoded domain 和 dev token 误用风险：A1-001、A1-003、A2-001、A3-001 | R1 完成或风险接受有书面记录 | hardcoded regression tests；`cd frontend && npm run build` | `docs/production_deployment.md`、`docs/local_deployment.md`、`RELEASE_CHECKLIST.md` | ready |
| R3 | 改善前端证据展示和 operator UX | API contract 未变或 snapshot 同步更新 | frontend build；rendered smoke notes；必要时补前端 e2e | `README.md`、`docs/demo_script.md`、`docs/operator_guide.md` | ready |
| R4 | 发布包清理和 release evidence 更新：A4-002 | R1-R3 已完成，或 release owner 确认 tracked evidence 范围 | `make release-check` 或等价命令集；release artifact scan | `release_manifest.json`、`RELEASE_CHECKLIST.md`、release evidence 与 evaluation docs | ready |

## 暂不整改项

| 风险 | 暂不整改原因 | 重新评估触发条件 |
|---|---|---|
| A4-001 | 文档已补充 dev token 生产边界，本轮不需要代码变更 | 生产环境仍接受 `operator-token`，或前端 dev token 改为非显式本地输入 |
| 前端 rendered smoke 未形成自动化 e2e | 本轮目标是风险审查，已记录 smoke 证据；自动化 e2e 属于后续 UX/QA 批次 | 前端开始承载更多 operator workflow，或 API contract/UI copy 再次变更 |
