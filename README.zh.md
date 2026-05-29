# 偏好到规则验证 MVP

本仓库是一个研究工程 MVP，主题是：

```text
面向广东高考志愿填报的 Preference-to-Rule Verification Methodology
```

它不是普通的志愿推荐机器人。当前目标是验证一件更小但更关键的事情：当用户用自然语言表达志愿偏好时，系统如何判断哪些内容可以安全变成可执行规则，哪些内容必须先让用户确认，哪些内容只能作为语义说明或非可执行偏好保留。

## 当前 MVP

MVP 只支持一个固定 demo 输入：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

当前流水线：

1. 读取 Excel 工作簿。
2. 自动检测真实表头行。
3. 只基于真实 Excel 字段构建 schema registry。
4. 对该 demo 输入使用硬编码抽取结果。
5. 验证 deterministic rules。
6. 将模糊偏好保留为 candidate rules。
7. 模拟用户确认安全边际和学费阈值。
8. 只执行已验证、已确认的规则。
9. 输出规则、验证报告、筛选结果和逐行 trace。

## 文件

规划文档：

- [docs/methodology_engineering_plan.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_engineering_plan.md)
- [docs/methodology_engineering_plan.zh.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_engineering_plan.zh.md)
- [docs/mvp_demo_spec.md](/Users/tz/Desktop/Projects/SZU/docs/mvp_demo_spec.md)
- [docs/mvp_demo_spec.zh.md](/Users/tz/Desktop/Projects/SZU/docs/mvp_demo_spec.zh.md)
- [docs/methodology_report.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.md)
- [docs/methodology_report.zh.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.zh.md)

Demo 脚本：

- [scripts/run_mvp_demo.py](/Users/tz/Desktop/Projects/SZU/scripts/run_mvp_demo.py)

生成输出：

- [outputs/mvp_demo/rules.json](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/rules.json)
- [outputs/mvp_demo/verification_report.md](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/verification_report.md)
- [outputs/mvp_demo/verification_report.zh.md](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/verification_report.zh.md)
- [outputs/mvp_demo/filtered_results.csv](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/filtered_results.csv)
- [outputs/mvp_demo/result_trace.md](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/result_trace.md)
- [outputs/mvp_demo/result_trace.zh.md](/Users/tz/Desktop/Projects/SZU/outputs/mvp_demo/result_trace.zh.md)

## 运行

在项目根目录执行：

```bash
/Users/tz/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_mvp_demo.py
```

当前预期输出：

```text
Wrote outputs/mvp_demo/rules.json
Wrote outputs/mvp_demo/verification_report.md
Wrote outputs/mvp_demo/filtered_results.csv
Wrote outputs/mvp_demo/result_trace.md
Filtered rows: 93
```

## 最终可执行规则

当前 demo 执行 6 条规则：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

后两条来自模拟用户确认：

- `稳一点` -> 以排位 32000 为基准，采用 10% 安全边际。
- `太贵` -> 学费上限 20000 元/年。

## 安全边界

`中外合作` 偏好没有被执行，因为当前 Excel schema 中没有专门的 `cooperation_type` 字段。MVP 不从 `专业全称`、`专业备注`、`专业组名称` 等文本字段里推断中外合作。

这是刻意设计的。项目的核心问题不是“如何更激进地推荐”，而是“如何避免把模糊或缺少字段支撑的偏好偷偷变成可执行规则”。

## 当前限制

- 只支持一个输入。
- slot extraction 是硬编码的。
- 用户确认是模拟的。
- 代码中不使用 LLM。
- 不做外部联网搜索。
- 不生成完整志愿表。
- 不判断学校声誉或就业前景。
- 不做相关专业语义扩展。

研究解释和下一步评估计划见 [docs/methodology_report.zh.md](/Users/tz/Desktop/Projects/SZU/docs/methodology_report.zh.md)。
