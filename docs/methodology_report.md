# 方法论报告：偏好到规则验证

## 1. 项目定位

本项目是一个 research-engineering 方法论项目，不是普通的高考志愿推荐 bot。当前工程形态已经包装为 `LLM-safe structured data query tool server for Excel/CSV`：LLM/agent/前端可以调用稳定 tool contracts，但执行权仍由 schema grounding、RuleVerifier、confirmation loop 和 DuckDB fingerprint guard 控制。

当前案例是基于结构化 Excel 数据的广东高考志愿填报场景。核心研究问题是：

```text
当用户用自然语言表达偏好时，系统如何判断哪些部分可以安全编译为 deterministic executable rules，哪些部分需要人类确认，哪些部分只能保留为语义信息或由 LLM 辅助解释？
```

主要贡献是防止把模糊自然语言偏好不安全地提升为确定性可执行规则。

实现层已把招生场景抽象为 `DomainConfig` + domain pack。默认 domain pack 位于
`domains/admissions/`，其中配置 schema mapping、字段别名、值别名、rule taxonomy、
排序策略、answer templates、`top_results` 字段映射和 golden cases。核心 Workbench、
AttributeGrounder、RuleVerifier 与 DuckDBExecutor 不直接硬编码招生源列名，只读取
domain pack 中的 canonical fields。`domains/housing/` 和 `domains/products/` 提供 20 行 CSV
toy fixture，用于验证同一套 grounding -> verification -> DuckDB execution -> EvidencePack ->
template answer pipeline 可以替换 domain 运行。

现在还提供 `scripts/generate_domain_pack.py`，可从 CSV/Excel 根据 schema profile 自动生成
draft domain pack：`domain.yaml`、`schema_mapping.yaml`、seed aliases、seed taxonomy、seed
sort policy、seed answer templates、seed golden cases，以及 `<domain>.duckdb`、
`schema_profile.json`、`schema_value_index.json` 和 `ingestion_summary.json`。自动生成结果只
标记为 `draft` 或 `needs_review`，默认不给字段写入可执行 `allowed_ops`；人工 approve 后才
能进入 RuleVerifier hard rules。`domains/products/fixtures/products.csv` 和 housing fixture
一起覆盖了同一套 generator -> DomainConfig -> DuckDB smoke query。

新增的 `scripts/review_domain_pack.py` 把人工审查显式纳入流程：`summarize` 先读取
draft 文件、schema profile 和 schema/value index；`validate` 校验 DomainConfig、API
contract、`top_result_mapping`、`rule_taxonomy` 和 `sort_policy` 结构；`approve-field`、
`approve-op`、`block-field` 和 `block-op` 都写入审计记录；`approve-domain` 只有在 title
mapping、primary attributes、sort policy/default safe sort 和字段安全检查都通过后，才会把
pack 改为 `approved`。CLI 默认 dry-run，只有 `--write` 会写入 `review.yaml` 和 runtime
配置。正式接入顺序是：

```text
generate draft
-> review
-> approve
-> demo acceptance
-> real dataset pilot
-> quality gate
-> commit / release
```

其中 PII、高基数字段、自由文本 contains/keyword filter、未通过数值 sanity check 的字段
不会自动成为 hard filter。`draft` / `needs_review` 即使包含 seed allowed ops，也仍然在
Workbench 中返回 `blocked`，不执行 SQL。

交付前必须运行 `scripts/run_quality_gate.py`。该门禁统一覆盖 Python 语法检查、unit
tests、regex evaluator、API contract tests、demo acceptance、domain pack validate、domain
review workflow smoke、warehouse fingerprint guard、`git diff --check` 和前端 build。报告
写入 `outputs/quality_gate/tmp/latest/report.md` 与
`outputs/quality_gate/tmp/latest/report.json`，并检查运行期间是否新增未跟踪或被改脏的
tracked artifact，防止 gate 通过但工作区被产物污染。

上传数据集产品流没有绕过这些边界。`POST /datasets/upload` 只保存 CSV/Excel 并生成
路径安全的 `dataset_id`；`generate-domain-pack` 仍调用同一个 schema profiling 和 draft
generator；`approve-field`、`approve-op`、`block-field`、`approve-domain` 仍调用 review
workflow 并写审计记录；`build-warehouse` 仍复用 DuckDB ingestion 和 fingerprint guard；
`POST /workbench/query` 返回同一个 `WorkbenchResponse` contract。未 approved 的
`draft` / `needs_review` pack、stale warehouse fingerprint、非法 `dataset_id` 或缺失
warehouse 都必须返回 `blocked`，不能执行 SQL。Excel ingestion 现在会显式返回 sheet
list、detected header row、重复列安全映射、空行空列清理、合并单元格/隐藏行列/公式单元格
warning，以及行列规模 warning/error。前端上传页面只展示 profile、review summary、
required/missing/risky fields、`items`、`top_results`、`result_sections`、`EvidencePack`
和 warnings，不生成推荐规则。上传页 build 成功并进入 `queryable` 后，主查询页可以把该
`dataset_id` 作为 admissions 数据源调用同一个 `/workbench/query`；这只是后端数据源选择，
不改变规则抽取、schema grounding、RuleVerifier 或 EvidencePack 边界。operator UI 现在会把
`items` 与 `result_sections` 放在主展示层，把 `top_results` 保留为兼容 JSON；
`needs_confirmation` 只允许选择上一轮系统返回的 `candidate_id` 重跑；`blocked`、
`no_results`、warnings 和前端操作审计记录单独展示。

`scripts/run_real_dataset_pilot.py` 是真实招生 Excel 上线前的验收脚本。它把上传、profile、
draft pack、review summary、safe auto-suggest approvals、manual approval fixture、warehouse
构建和两条目标 admissions query 串成一个报告。目标 query 缺少必要 canonical fields 时必须
返回 `blocked` 或 needs-review warning；“25年深圳大学录取最高专业组”会把最终使用的
metric 和参数化 SQL 写入 EvidencePack；“630 分人工智能/计算机、广东、不想去国外”在没有
位次时，`recommendation` 必须返回 `status=needs_confirmation` 和
`score_without_rank` warning，`execution_summary.sql` 为空，`result_count=0`。
系统应要求用户补充广东省排位/位次，不能仅凭分数执行 SQL，也不能把分数 margin
解释成录取概率。

`scripts/run_operator_trial.py` 是面向 operator 的真实 Excel 人工试运行入口。它复用同一套
DatasetService、review workflow、DuckDB warehouse、WorkbenchResponse 和 EvidencePack，不复制
执行逻辑；输出按 `outputs/operator_trial/<run_id>/` 分目录保存。报告额外记录
`operation_cards`、`manual_checkpoints`、常见失败处理、missing/risky fields、review blockers、safe auto-suggest approvals、人工
approval fixture、warehouse fingerprint 和两条目标查询结果，用于 operator 在正式 Quality Gate
前记录卡点和人工结论。

functional tool layer 位于 `src/api/tool_registry.py`，机器可读契约位于
`schemas/tools/*.json`。LLM-safe tools 只包括 `dataset.profile`、`dataset.review_summary`、
`workbench.query`、`workbench.confirm` 和 `evidence.get`。review/admin/warehouse/
diagnostics tools 需要显式权限并写入 audit event，不能暴露给 LLM 自动调用。`workbench.query`
不接受 SQL、hard rules、executable rules 或 domain status override；`workbench.confirm`
只能引用上一轮系统生成的 `candidate_id`。

这次抽象仍然坚持结构化存储优先：招生主数据使用 DuckDB 和 schema/value index；toy
domain 使用 CSV fixture。系统没有接入 Qwen、BGE、向量库或全文表格 embedding。可选
`--llm deepseek` 只接收 schema profile 和少量脱敏样例，输出只能作为候选 aliases/templates，
不能直接提升为可执行规则。

系统不应该直接给出推荐列表，除非它能解释：

- 哪些用户偏好变成了可执行规则；
- 哪些偏好需要确认；
- 哪些偏好因为 schema 不支持而不能执行；
- 每条返回结果为什么满足已验证规则。

## 2. 为什么这不是推荐 Bot

普通推荐 bot 的目标是直接给出有用建议。本项目研究的是推荐之前的步骤：

```text
natural-language preference -> verified executable rule set
```

当前系统不生成完整志愿表，不按学校声誉排序，不预测就业结果，也不做宽泛的录取判断。它关注的是：一个偏好是否能落到真实数据字段上，并被安全执行。

这个区别很重要，因为模糊表达一旦被静默转换成精确过滤条件，就可能产生误导。例如：

```text
学校稳一点
```

不应该自动变成：

```text
录取概率 = 高
```

或：

```text
safety_level = 稳妥
```

除非系统有 schema-grounded rule，并且用户确认了这种解释。

## 3. 最低可执行信息

志愿填报系统的第一步不是推荐，而是检查是否具备最低可执行信息：考生位次、科类、批次、目标数据字段和用户偏好边界。缺少这些信息时，系统应该追问或标记不可执行，而不是让 LLM 直接生成建议。

对广东场景，最小 user gate 是：

```text
生源地 = 广东
科类 = 物理 / 历史
位次 = user_rank
批次 = 本科 / 专科 / 提前批等
```

其中位次比分数更重要。不同年份分数线波动大，位次更适合和往年录取数据比较。如果用户只给分数没有给位次，系统应该追问：

```text
请提供你的省排名/位次。仅凭分数无法稳定判断风险。
```

数据集的最低可执行字段包括：

```text
院校名称
院校代码
院校专业组代码
专业名称
专业代码
科类
批次
城市
计划人数
学费
往年最低分
往年最低位次
专业组最低位次
选科要求
本科/专科
公私性质
院校标签 / 院校水平
```

广东尤其不能只输出学校名，因为很多判断发生在“院校专业组 + 专业”层面。合格输出至少应包含：

```text
院校名称
院校专业组代码
专业名称
城市
学费
专业组最低位次
专业最低位次 / 如果有
安全边际
```

风险判断需要 `user_rank`、往年专业组最低位次、专业最低位次、招生计划人数、是否新增专业或专业组、以及近两年/三年录取趋势。当前 MVP 只使用 `专业组最低位次1`，这可以演示 rule verification，但方法论必须承认限制：只用一年位次不够稳，更完整系统应该使用 2-3 年最低位次、计划人数变化、是否新增等信息。

用户偏好分三类处理：

| 类型 | 示例 | 处理方式 |
|---|---|---|
| Deterministic | `学费两万以内`、`城市在广州深圳`、`专业名称包含计算机` | 字段存在且值边界明确时可以执行。 |
| Candidate | `稳一点`、`太贵`、`计算机相关`、`学校好一点`、`离家近` | 需要确认阈值、集合、代理指标或家庭城市。 |
| LLM/external/reference only | `就业前景好`、`学校氛围好`、`宿舍条件好`、`专业未来趋势`、`城市发展潜力` | 没有对应字段时不能执行，只能解释、标记外部信息需求或保留为参考。 |

最终自然语言答案也有最低要求：说明执行了哪些规则、哪些规则需要确认、哪些偏好没有执行、筛选出多少结果、展示前若干结果、每个结果为什么保留、风险提醒，以及下一步需要用户补充什么。

这些分类被记录在 `rules/information_requirements.json` 中，作为方法论和可执行规则之间的审查边界。

## 4. 方法论 Pipeline

当前方法论是：

```text
Natural-language input
-> preference decomposition
-> rule class assignment
-> schema grounding
-> rule verification
-> human confirmation
-> candidate promotion or rejection
-> executable rule set
-> backend-specific query execution
-> result trace
-> evidence pack
-> answer/report generation
-> evaluation
```

核心原则：

```text
No schema grounding, no deterministic execution.
No human confirmation, no candidate rule promotion.
No trace, no verified result.
No evidence pack, no final answer.
Neural proposes; symbolic verifies and executes.
```

升级后的实现还在 `rules/rule_lifecycle_schema.json` 中记录了 rule lifecycle 边界：

```text
extracted_preference
-> proposed_rule
-> schema_grounded_rule
-> verified_rule
-> confirmed_rule
-> executable_rule
-> executed_rule
-> traced_result
-> evidence_pack
-> generated_answer
```

这个 lifecycle 很重要，因为它区分了 extractor 提出了什么，以及 verifier 最终允许什么执行。

答案层必须位于 trace 之后。它不读取 raw Excel，也不判断 executability。它只接收
evidence pack，字段包括：

- `user_request`；
- `executed_rules`；
- `candidate_confirmations`；
- `not_executed_preferences`；
- `result_count`；
- `top_k_results`；
- `trace_summary`。

`TemplateReportBuilder` 根据 evidence pack 确定性生成中文答案。可选的
`DeepSeekAnswerGenerator` 也只能接收同一个 evidence pack。由于 LLM 可能省略
必要字段，DeepSeek 路径会追加一段确定性的证据覆盖清单，补齐已执行规则、前若干
专业组结果、未执行偏好和安全说明。

答案层的最小结果形状包括 `院校名称`、`院校专业组代码`、`专业代码`、`专业名称`、
`专业全称`、`城市`、`学费`、`专业组最低位次`、可用时的 `专业最低位次` 和
safety margin。`专业代码` 与 `专业全称` 必须保留，因为两条结果可能共享同一学校、
同一专业组代码和同一个短专业名，但实际对应不同培养方向。

实现中还增加了 attribute-level grounding audit，放在 rule construction 之前：

```text
extracted attributes
-> attribute grounding audit
-> rule construction
-> rule verification
```

这意味着抽取出来的 attributes 默认不等于可执行。它们必须先被标记为：

| Attribute status | 含义 |
|---|---|
| `schema_grounded` | 能映射到当前 Excel schema 字段，但仍需要 rule verification。 |
| `confirmable` | 能映射到字段，但表达模糊或语义化，需要用户确认。 |
| `context_only` | 只作为上下文或公式输入，不能作为 Excel filter。 |
| `missing_schema` | 当前没有对应 Excel 字段，不能执行。 |
| `ignored_not_schema_mapped` | extractor 输出了未知属性，rule construction 会忽略。 |

这样可以补上一个重要缺口：extractor 可以提到 `公办`、`学校名气`、`偏远城市` 等属性，但只要它们没有 grounded 到 Excel schema，就不能成为 executable rules。

## 5. 规则分类

### 确定性规则

确定性规则是明确的、schema-grounded、类型安全、可直接执行的规则。

MVP 示例：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
学费 <= 20000
```

当字段存在、操作符允许，并且用户表达足够明确时，exact keyword match 或明确数值边界可以作为 deterministic rule。比如 `学费两万以内` 可以归一化为 `学费 <= 20000`；但 `太贵` 没有明确阈值，仍然是 candidate。

### 候选规则

候选规则是对模糊偏好的可能操作化解释。它们必须在用户确认后才能执行。

示例：

```text
稳一点 -> 选择 safety margin：5%、10% 或 15%
太贵 -> 选择学费上限
计算机相关 -> 确认是否包含 软件工程、人工智能、数据科学、网络安全
学校好一点 -> 确认是否使用某个排名/标签来源，或不执行
```

候选规则在 promotion 之前必须被阻止执行。

### 需要 LLM 或不可执行的部分

这类部分是当前 schema 无法安全支持的偏好。

示例：

```text
不要中外合作
```

当前 Excel schema 没有专门的 `cooperation_type` 字段。因此系统会保留这个偏好，但不会执行它。

MVP 也不会从自由文本字段中推断 `cooperation_type`。未来可以考虑这种派生字段，但前提是先建立并验证结构化字段。

## 6. 当前 Demo

输入：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

抽取偏好：

```json
{
  "source_province": "广东",
  "subject_type": "物理",
  "user_rank": 32000,
  "major_keyword": "计算机",
  "preferred_cities": ["广州", "深圳"],
  "risk_preference_raw": "稳一点",
  "tuition_preference_raw": "太贵",
  "cooperation_preference_raw": "不想去太贵的中外合作"
}
```

模拟确认：

```text
稳一点 -> safety margin = 10%
太贵 -> tuition cap = 20000
计算机相关扩展 -> false
```

最终可执行规则：

```text
生源地 == 广东
科类 == 物理
专业名称 contains 计算机
城市 contains 广州 or 深圳
专业组最低位次1 >= 35200
学费 <= 20000
```

阈值 `35200` 来自：

```text
32000 * 1.10 = 35200
```

当前 workbook 运行结果是 93 条过滤结果。

## 7. Schema Registry 是系统边界

Schema registry 定义系统可以执行什么。一个规则只有在字段存在于 registry 且通过 verification 后，才能成为 deterministic rule。

Attribute extraction 可以比 executable schema 更宽，但 execution 不可以。每个 extracted slot 都必须先经过 schema boundary audit，再进入 rule construction。

当前 MVP 使用的真实 Excel 字段包括：

```text
生源地
科类
专业名称
城市
专业组最低位次1
学费
```

当前还没有进入 MVP active schema registry 的字段包括：

```text
cooperation_type
school_ownership
school_reputation
employment_outlook
distance_from_home
major_family
major_popularity
city_remoteness
```

其中一部分概念已经在 schema profile 中找到了 Excel 候选列：

- `school_ownership` 可能映射到 `公私性质`。
- `school_reputation` 可能部分映射到 `院校水平`、`院校标签`、`院校排名` 或 `软科排名`。
- `city_remoteness` 或城市质量可能部分映射到 `城市水平标签`。
- `major_popularity` 需要额外策略判断；`专业类` 或 `专业水平` 不等同于“热门/冷门”。

这些字段不能自动执行。它们需要人工 schema review、allowed operators、语义说明和测试后，才能进入 active schema registry。

## 8. 后端抽象

Excel 只是第一个 case study。方法论将 rule verification 和 data execution 分离。

后端抽象是：

| 组件 | 职责 |
|---|---|
| Data Adapter | 加载数据源，并暴露真实字段。 |
| Schema Registry | 定义字段、类型、别名、允许操作符、nullable 和 notes。 |
| Backend-specific Query Compiler | 将 verified rules 编译成 pandas、SQL、MongoDB 或 API 查询形式。 |
| Executor | 在对应 backend 上执行规则。 |
| Result Trace | 解释每条结果由哪些规则产生。 |
| Evidence Pack | 将已验证规则、确认记录、未执行偏好、top results 和 trace summary 打包给答案层。 |
| Report Builder / Answer Generator | 只根据 evidence pack 生成最终答案。 |

当前 executor：

```text
DuckDB executor for verified hard rules
pandas executor for legacy MVP demos, evaluation comparison, and focused tests
```

未来 executor 可以包括：

```text
SQL / DuckDB compiler
MongoDB compiler
API executor for tool-backed data
```

非结构化文本和 PDF 不能被确定性执行，除非先抽取并验证结构化 schema。

Workbench API 启动执行前会先做 data warehouse fingerprint guard：

- DuckDB `__metadata` 必须存在，并记录源 Excel fingerprint。
- `schema_value_index.json` 必须记录同一个源 Excel fingerprint。
- 当前源 Excel 的 fingerprint 必须同时匹配 DuckDB metadata 和 schema/value index metadata。
- row count / column count metadata 不一致时也会阻断执行。
- guard 未通过时返回 structured warning，不静默回退到 raw Excel / pandas execution。

`scripts/build_data_warehouse.py` 负责重建 DuckDB、schema/value index，并输出 `outputs/data/ingestion_summary.json`，其中包含 source path、fingerprint、row/column count、field profiles 和 created_at。

Workbench 的 confirmation loop 也属于执行边界：

- `value_index_audit` 为 `partial_match` 的候选只返回系统生成的 `candidate_id` 和已审查候选值。
- 用户确认只能引用上一轮返回的 `candidate_id`，不能把二次输入文本直接变成 SQL 条件。
- 后端会根据当前 query 重新生成候选；伪造、过期或不属于当前 query 的 `candidate_id` 会被拒绝。
- 已确认 candidate 会重新经过规则形状检查，然后才编译成参数化 DuckDB SQL。
- `no_schema_field` 偏好即使被用户确认也不执行，例如当前没有合作办学类型字段时，`校企合作` / `中外合作` 只能保留为未执行偏好。
- EvidencePack 会记录 `confirmed_rules`、`confirmation_source`、`executed_after_confirmation`、`unconfirmed_candidates` 和 `no_schema_field_preferences`。

Workbench API 返回固定的 `WorkbenchResponse` contract：

- `status` 只能是 `ok`、`needs_confirmation`、`no_results`、`blocked`、`error`。
- 顶层固定包含 `schema_version`、`domain`、`domain_version`、`domain_pack_status`、
  `query_type`、`query`、`items`、`top_results`、`result_sections`、`evidence_pack`
  和 `debug_trace` 等字段。
- `domain_pack_status` 至少支持 `draft`、`needs_review`、`approved`、`blocked`；
  `draft` / `needs_review` 默认返回 `blocked`，不执行 SQL。
- `needs_confirmation` 表示存在未确认的 `partial_match` 偏好，这些偏好不能声称已执行；当前结果只能作为已执行规则下的 provisional results。
- `blocked` 用于 fingerprint guard、未 approved 的 domain pack、伪造/过期/不属于当前 query 的 `candidate_id` 等安全阻断；此状态下 `execution.sql` 为空，不执行 DuckDB SQL。
- `no_results` 表示 SQL 正常执行但 `filtered_row_count = 0`；答案不得编造推荐。
- 前端主列表优先读取跨领域 `items`。`top_results` 只作为 domain-specific 兼容层，
  由 `domains/<domain>/top_result_mapping.yaml` 生成；招生 domain 继续保留
  `university_name`、`group_code`、`major_code`、`major_name`、`full_major_name`、
  `city`、`tuition`、`rank_2024`、`plan_count` 等英文 key。
  EvidencePack 内部继续保留中文原始字段用于 trace。
- admissions 新增 `AdmissionsQueryPlanner`，只在招生 domain 内识别
  `group_detail_report` 和 `recommendation`。前者按 domain pack 配置的默认
  `group_min_score_2024` 指标生成专业组聚合和组内专业明细；后者基于历史最低分/
  最低位次生成 `reach`、`match`、`safety`（冲/稳/保）分组。如果用户只有分数没有
  位次，`recommendation` 必须返回 `status=needs_confirmation` 和
  `score_without_rank` warning，`execution_summary.sql` 为空，`result_count=0`。
  系统应要求用户补充广东省排位/位次，不能仅凭分数执行 SQL，也不能把分数 margin
  解释成录取概率。有位次时优先按 `rank_margin` 排序。推荐 EvidencePack 会记录
  `margin_policy`、`year_weighting`、`major_match` 和 `bucket_counts`，当前只执行
  `latest_available_year`，不把多年度权重作为 SQL 条件。`不想去国外`、`不要中外合作`
  只有在 domain pack 启用对应已审核字段时才执行，否则保留在
  `no_schema_field_preferences`。这些分组是历史数据 margin 解释，不是录取概率。
- 完整字段和 JSON 示例见 `docs/api_contract.md`。

## 9. LLM 边界

可选 DeepSeek extractor 只用于 preference extraction 和 source spans。

允许的 LLM 角色：

- 抽取 user context；
- 抽取 preference slots；
- 保留 source spans；
- 提出 candidate interpretations。
- 根据 verified evidence pack 生成答案文案。

不允许的 LLM 角色：

- 提升 candidate rules；
- 验证 schema 是否存在；
- 决定最终 executability；
- 编译查询；
- 执行 deterministic filters；
- 声称缺失字段存在。
- 在答案生成阶段读取 raw Excel；
- 添加 evidence pack 中没有的录取、就业、中外合作、宿舍或学校质量事实。

所有 DeepSeek 输出都必须经过和 regex 输出相同的 rule classifier 和 symbolic verifier。

对于答案生成，DeepSeek 输出只被视为 prose。系统会追加确定性的 evidence
coverage，保证最终答案即使在模型省略字段时，仍包含 verified rules、top
results、未执行偏好和安全说明。

## 10. 规则验证协议

每条可执行规则必须通过：

- field existence check；
- source column existence check；
- type check；
- operator check；
- value normalization check；
- ambiguity check；
- data coverage check；
- conflict check；
- dry-run check；
- traceability check。

Verification output 必须解释规则为什么可执行、被阻止、或等待确认。

现在 verifier 输出的是 verification profile，而不只是 pass/fail：

```json
{
  "schema_grounded": true,
  "field_exists": true,
  "source_column_exists": true,
  "operator_allowed": true,
  "type_valid": true,
  "value_present": true,
  "value_normalized": true,
  "ambiguity_level": "none",
  "requires_human_confirmation": false,
  "execution_level": "executable",
  "executable": true
}
```

关键 execution levels：

| Execution level | 含义 |
|---|---|
| `executable` | deterministic、schema-grounded，可以执行。 |
| `confirmable` | schema-grounded，但模糊或需要确认。 |
| `context_only` | 只是上下文，不是数据过滤规则。 |
| `blocked` | 已 grounded，但当前不能执行。 |
| `rejected` | 没有 schema grounding。 |

## 11. 评估摘要

当前评估比较的是 token budget 下的 task success。

单条 MVP 输入：

| 方法 | 结果行数 | Task success | Total tokens | Over-promotion |
|---|---:|---:|---:|---:|
| `regex_extractor_symbolic_verifier` | 93 | 5/5 | 0 | 0 |
| `deepseek_extractor_symbolic_verifier` | 93 | 5/5 | 834 | 0 |
| `llm_only_baseline` | n/a | 1/5 | 818 | unsafe |
| `schema_aware_llm_only_baseline` | n/a | 1/5 | 1282 | unsafe |

40 条模糊输入评估：

| 方法 | 得分 | 成功率 | Total tokens | Over-promotion rate |
|---|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | 320/320 | 1.000 | 0 | 0.000 |
| `deepseek_extractor_symbolic_verifier` | 320/320 | 1.000 | 25334 | 0.000 |
| `llm_only_baseline` | 107/200 | 0.535 | 24388 | 0.475 |
| `schema_aware_llm_only_baseline` | 156/200 | 0.780 | 42916 | 0.275 |

当前 benchmark 文件包含 40 条分层输入，覆盖 clear、vague、unsupported、mixed、adversarial、contradictory 和 end-to-end demo cases。DeepSeek extractor 上一轮是 `314/320`；加入多专业词、更多城市归一化和学校性质偏好保留后，达到 `320/320`。这个提升来自更好的 slot representation，不是放宽 verifier。

当前 baseline comparison 包括：

| 方法 | 目的 |
|---|---|
| `llm_only_baseline` | 朴素 LLM-only rule proposal。 |
| `schema_aware_llm_only_baseline` | 更强的 LLM-only baseline，能看到 schema context，但仍没有 symbolic verifier。 |
| `deepseek_extractor_symbolic_verifier` | LLM extraction + symbolic verification。 |
| `regex_extractor_symbolic_verifier` | 保守 symbolic extraction baseline。 |

Pipeline token budget 对比：

| 方案 | 估算/输入 tokens | 结果 |
|---|---:|---|
| Direct LLM with full Excel | 23,040,523 | 未执行；超过现实上下文预算。 |
| Direct LLM with MVP columns only | 483,922 | 仍然很大，并且缺少 deterministic verification。 |
| DeepSeek extractor + symbolic verifier | 834 | 93 rows, 5/5。 |
| Regex extractor + symbolic verifier | 0 | 93 rows, 5/5。 |
| Schema-aware LLM-only baseline | 1282 | 1/5；仍然 unsafe。 |

答案层评估：

| 答案模式 | 输入边界 | 预期结果 |
|---|---|---|
| `llm_only_schema_sample` | 用户请求、schema summary、sample projected rows | 对照组；因为没有 verified executed rules、未执行偏好状态和 trace summary，通常失败。 |
| `pipeline_template` | 只使用 verified evidence pack | 5/5 evidence alignment；不使用 LLM。 |
| `pipeline_deepseek_evidence` | 只使用 verified evidence pack | 追加确定性 evidence coverage 后达到 5/5 evidence alignment。 |

答案层 scoring 检查结果总数、已执行规则、top projected professional-group
results、未执行偏好，以及 unsupported claims。Unsupported 指没有 verified
evidence pack 支持，不等于 raw Excel workbook 中一定不存在。

目前最强的证据不是 LLM 没有用，而是：当 symbolic verification 控制执行时，LLM extraction 会更安全。

## 11.5 Tool Server 发布边界

当前工程已经包装为 `LLM-safe structured data query tool server for Excel/CSV`。发布层新增的是稳定调用面，而不是新的执行策略：

- `schemas/tools/*.json` 定义机器可读 tool contracts；
- `src/api/tool_registry.py` 组合 DatasetService、Workbench、EvidencePack、Quality Gate 和 Real Dataset Pilot；
- `GET /tools/list`、`GET /tools/{tool_name}/schema`、`POST /tools/{tool_name}/invoke` 作为 HTTP tool server 入口；
- `GET /healthz`、`GET /readyz`、`GET /version` 支持部署探针；
- `scripts/export_openapi.py`、`scripts/export_tool_manifest.py` 和 `scripts/export_openai_tools.py` 支持前端、agent 网关、OpenAI-compatible tool calling 和 operator 控制台读取契约；
- `src/api/openai_tool_adapter.py` 和 `src/api/mcp_tool_adapter.py` 默认只暴露 LLM-safe tools，`scripts/run_agent_tool_acceptance.py` 做 fake agent 黑盒验收；
- `Makefile`、`.env.example`、`docs/local_deployment.md`、`docs/operator_guide.md`、`docs/troubleshooting.md` 说明本地部署、权限、审计和故障排查。
- `release_manifest.json`、`CHANGELOG.md`、`RELEASE_CHECKLIST.md`、`docs/demo_script.md`、`sample_data/` 和 `sample_outputs/` 组成候选 release demo package；
- `scripts/validate_release_package.py` 和 `make release-check` 校验发布包静态完整性，但不替代 Quality Gate。

这个发布层仍遵守同一条不变量：LLM-safe tools 只能读取 profile/review summary、调用 Workbench query/confirm 或取净化 EvidencePack；`approve-*`、`build-warehouse`、`quality.run` 和 `pilot.run` 必须由 operator/admin 权限触发。tool invoke audit 只记录 actor、tool、dataset、status、duration、side effects 和 error code，不记录完整上传文件内容、环境变量或密钥。

## 11.6 非结构化资料 reference-only 层

Phase F 增加的是最小化的 admissions policy reference 层，而不是结构化大表 RAG。
`domains/admissions/policy_references/*.md` 保存已审核 Markdown 资料，domain pack 中的
`policy_references` 配置列出允许触发 lexical 命中的关键词。Workbench 在生成
EvidencePack 时追加 `policy_references`，每条命中都标记为 `reference_only` 和
`does_not_change_sql_or_results`。

该层只能解释和引用，例如说明“没有合作办学类型字段时，不想去国外/中外合作不能执行”
或“专项计划需要已审核字段”。它不进入 AttributeGrounder、RuleVerifier、
RulePromoter 或 DuckDBExecutor，不改变 SQL、params、`result_count`、
`result_sections` 或冲/稳/保 bucket。后续如果引入政策文档检索，也必须保持这个
EvidencePack 边界。

## 12. 当前局限性

当前系统仍然很窄。

局限性：

- 评估集规模较小。
- Regex extraction 针对当前 examples 人工整理。
- DeepSeek extraction 还没有大规模 stress test。
- Human confirmation 是模拟的。
- 系统只使用一个广东招生数据集；Workbench hard rules 通过 DuckDB executor 执行，pandas executor 仅保留为 MVP demo、评估对照和测试工具。
- Workbench 依赖 DuckDB metadata、schema/value index metadata 和源 Excel fingerprint 一致性校验，校验失败时阻断执行并返回 structured warning。
- DeepSeek slot adapter 已可选接入，但默认关闭；启用时只补 deterministic extractor 缺失的 slots，并在进入 Workbench 前做 JSON schema 校验和禁止字段检查。
- 不生成完整志愿表。
- 不评价学校声誉。
- 不预测就业结果。
- 不从文本字段推断 `cooperation_type`。
- Direct Excel prompting 的 token 估算是近似值。

这些限制在当前研究阶段是可以接受的，因为目标是 rule verification methodology，不是完整 advisor 产品。

## 13. 下一步方法论工作

下一步应聚焦评估和安全性：

- 如果继续收集到新的真实表达，将 `eval_inputs.jsonl` 从当前 40 条继续扩展。
- 增加 safety、cost、major family、location、school quality、employment 等表达的 paraphrases。
- 将 deterministic over-promotion rate 作为主要安全指标。
- 单独统计 schema hallucination rate。
- 增加 per-rule trace completeness scoring。
- 增加 unsupported but tempting fields 的 adversarial inputs。
- 测试 DeepSeek extraction 在不完整、矛盾输入中的稳定性。
- 单独压测 DeepSeek slot adapter：确认不覆盖 deterministic slots、不返回 executable rules、不改变 RuleVerifier 边界。
- 将 40-case benchmark 继续扩展到 50-100 条真实改写表达。
- 压测 `320/320` DeepSeek 结果在更长、更乱、矛盾输入下是否仍然稳定。
- 将 recommendation quality evaluation 和 rule verification evaluation 分开。

## 14. 泛化意义

该方法论可以泛化到其他用户用自然语言表达结构化偏好的决策系统：

- 选课；
- 租房筛选；
- 求职筛选；
- 商品推荐；
- 投资筛选；
- 奖学金或项目匹配。

可复用的不是广东高考的具体规则，而是这个边界：

```text
自然语言可以提出结构，但只有通过验证且基于 schema 接地的规则可以执行。
```
