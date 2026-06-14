# Quality Gate 报告

- 总体状态：`pass`
- 当前 git commit：`4c3c5b4`
- 工作区 dirty：`True`
- 开始时间：`2026-06-14T06:08:54.189300Z`
- 结束时间：`2026-06-14T06:10:22.144747Z`
- 耗时秒数：`87.956`
- regex score：`320/320`
- unittest：`150 tests`
- API contract：`10 tests`
- demo acceptance：`29` / `29`

## 检查列表

| check | status | exit_code | duration_seconds |
|---|---|---:|---:|
| git_state | warning | 0 | 0.0 |
| python_syntax | pass | 0 | 0.303 |
| unit_tests | pass | 0 | 38.428 |
| api_contract_tests | pass | 0 | 14.155 |
| regex_evaluator | pass | 0 | 1.08 |
| demo_acceptance | pass | 0 | 20.201 |
| domain_pack_validate | pass | 0 | 10.252 |
| domain_review_workflow | pass | 0 | 0.093 |
| warehouse_fingerprint_guard | pass | 0 | 0.117 |
| git_diff_check | pass | 0 | 0.1 |
| frontend_build | warning | 0 | 3.069 |

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
