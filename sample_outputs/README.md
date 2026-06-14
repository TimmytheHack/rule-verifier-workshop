# 样例输出

本目录保存小型、稳定的 release demo 输出示例。它们用于说明响应形状，不替代实时运行结果。

| 文件 | 用途 |
|---|---|
| `workbench_response_admissions_group_detail.json` | `group_detail_report` 的精简 `WorkbenchResponse` 示例。 |
| `quality_gate_summary.json` | `Quality Gate` 报告的精简结构示例。 |
| `operator_trial_summary.md` | operator trial 人工报告摘要示例。 |

正式验收仍以以下命令生成的当前报告为准：

```bash
make demo
make pilot
make operator-trial
make agent-acceptance
make quality
```
