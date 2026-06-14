# Quality Gate 报告

- 总体状态：`pass`
- 当前 git commit：`14f1b8d`
- 工作区 dirty：`True`
- 开始时间：`2026-06-14T04:51:21.596252Z`
- 结束时间：`2026-06-14T04:52:44.734823Z`
- 耗时秒数：`83.139`
- regex score：`320/320`
- unittest：`140 tests`
- API contract：`10 tests`
- demo acceptance：`29` / `29`

## 检查列表

| check | status | exit_code | duration_seconds |
|---|---|---:|---:|
| git_state | warning | 0 | 0.0 |
| python_syntax | pass | 0 | 0.246 |
| unit_tests | pass | 0 | 35.368 |
| api_contract_tests | pass | 0 | 13.41 |
| regex_evaluator | pass | 0 | 0.939 |
| demo_acceptance | pass | 0 | 19.809 |
| domain_pack_validate | pass | 0 | 9.925 |
| domain_review_workflow | pass | 0 | 0.089 |
| warehouse_fingerprint_guard | pass | 0 | 0.111 |
| git_diff_check | pass | 0 | 0.099 |
| frontend_build | warning | 0 | 2.992 |

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
