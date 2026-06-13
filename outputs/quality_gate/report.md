# Quality Gate 报告

- 总体状态：`pass`
- 当前 git commit：`03c2e56`
- 工作区 dirty：`True`
- 开始时间：`2026-06-13T15:38:55.557727Z`
- 结束时间：`2026-06-13T15:40:21.223368Z`
- 耗时秒数：`85.666`
- regex score：`320/320`
- unittest：`131 tests`
- API contract：`10 tests`
- demo acceptance：`29` / `29`

## 检查列表

| check | status | exit_code | duration_seconds |
|---|---|---:|---:|
| git_state | warning | 0 | 0.0 |
| python_syntax | pass | 0 | 0.252 |
| unit_tests | pass | 0 | 34.219 |
| api_contract_tests | pass | 0 | 14.323 |
| regex_evaluator | pass | 0 | 1.173 |
| demo_acceptance | pass | 0 | 20.949 |
| domain_pack_validate | pass | 0 | 11.125 |
| domain_review_workflow | pass | 0 | 0.082 |
| warehouse_fingerprint_guard | pass | 0 | 0.115 |
| git_diff_check | pass | 0 | 0.104 |
| frontend_build | warning | 0 | 3.164 |

## 失败原因摘要

- 无失败项。

## Domain Pack 状态

- `admissions`: status=`approved`, review_validate=`True`, can_execute=`True`
- `housing`: status=`approved`, review_validate=`True`, can_execute=`True`
- `products`: status=`approved`, review_validate=`True`, can_execute=`True`

## 生成 artifacts

- `/Users/tz/Desktop/Projects/SZU/outputs/quality_gate/report.md`
- `/Users/tz/Desktop/Projects/SZU/outputs/quality_gate/report.json`
- `/Users/tz/Desktop/Projects/SZU/outputs/quality_gate/tmp/domain_review_smoke/reports/quality_gate_review_smoke_review.json`
- `/Users/tz/Desktop/Projects/SZU/outputs/quality_gate/tmp/domain_review_smoke/reports/quality_gate_review_smoke_review.md`
