# 规则与模糊知识兼顾报告

## 1. 报告目的

本报告总结当前应用在开发收束阶段形成的方法：如何让自然语言里的模糊偏好参与系统，但不让它们越过规则验证边界；如何通过结构化数据、字段审查和紧凑证据包减少 token 消耗，同时提高回答和执行结果的正确率。

本文不是最终志愿填报质量评估，也不声称系统能替代人工志愿顾问。它讨论的是一个更窄的问题：

```text
用户偏好怎样从自然语言进入可验证规则，并在不能验证时被安全保留。
```

项目核心不变量是：

```text
自然语言可以提出结构，但只有经过 schema 接地和验证的规则可以执行。
```

对应到当前中文产品，就是：

```text
自然语言可以提出偏好，但只有表格里存在、已经审核、可以解释的字段才会参与筛选。
```

## 2. 项目先验知识

本项目不是通用聊天推荐 bot，而是一个本地结构化表格筛选工作台。它已经包装为 `LLM-safe structured data query tool server for Excel/CSV`，面向本地上传的 Excel/CSV 数据，主场景是广东招生数据查询和专业组结果解释。

当前领域约束主要有四点：

- 广东志愿场景中，位次比分数更稳定；只有分数没有位次时，系统应追问省排位，而不是用分数直接估算录取风险。
- 如果专业组和专业数据可用，不能只输出学校级推荐。
- 结果必须保留执行证据，最低有院校名称、院校专业组代码、专业名称、城市、学费、专业组最低位次、专业最低位次和安全边际。
- 模糊偏好例如“稳一点”“太贵”“学校好一点”“离家近”“就业好”不能被静默提升为 SQL filter。

工程上，系统把自然语言、字段审查、规则验证、执行和回答拆成不同职责：

```text
Extractor
-> AttributeGrounder
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> DuckDBExecutor
-> EvidencePack
-> ReportBuilder / AnswerGenerator
```

上传数据集的语义链路则是：

```text
Dataset profiling / domain pack review
-> optional LLM SemanticIntent proposal
-> reviewed mapping / preference grounding
-> SemanticQueryVerifier
-> SemanticSQLBuilder
-> DuckDBExecutor
-> EvidencePack
-> ReportBuilder / AnswerGenerator
```

这里的关键是，LLM 可以帮忙提出结构，但不能决定最终可执行性。

## 3. 规则和模糊知识的分层

本项目没有把用户输入简单分成“能懂”和“不能懂”，而是分成不同执行等级。

| 用户知识类型 | 例子 | 系统处理 | 是否进入 SQL |
|---|---|---|---|
| 明确结构化事实 | `广东`、`物理`、`广州深圳`、`计算机`、`学费 <= 20000` | 先通过 schema grounding，再由 `RuleVerifier` 校验字段、op、类型和值 | 校验通过后可以进入 |
| 上下文事实 | `排位32000`、`分数630` | 作为用户上下文或边界计算依据，不直接当作源表字段 | 不能直接进入 |
| 可确认模糊边界 | `稳一点`、`太贵`、`相关专业` | 进入 candidate，生成系统 `candidate_id` 或前端受控选项，确认后重新校验 | 确认并校验后才可进入 |
| 缺字段结构偏好 | `不想中外合作`，但表里没有已审核合作办学字段 | 进入 `no_schema_field_preferences` / `unanswerable_intents` | 不进入 |
| 外部或价值判断 | `就业好`、`学校氛围好`、`城市发展好`、`宿舍好` | 可作为说明或追问信息，不能当作表内筛选规则 | 不进入 |
| 排序偏好 | `优先更稳`、`更靠近我的位次` | 需要 verified `RankingPlan`，再由 `RankingVerifier` 验证字段、op 和 value evidence | 排序验证通过后才影响顺序 |

这样处理的好处是，模糊知识没有被丢弃。它仍然会被记录、展示和解释，但只有被审查字段和确定边界支持时才会执行。

## 4. 兼顾规则与模糊的机制

### 4.1 抽取器只负责提出候选

`DeepSeekExtractor` 和 `DeepSeekSemanticIntentExtractor` 的 prompt 都明确限制 LLM：只能抽取偏好、source span、候选 `SemanticIntent` 或候选规则形状，不能生成 SQL，不能声明规则已执行，不能补造原始 Excel 数据。

这让 LLM 的作用变成“召回结构”，而不是“授予执行权限”。即使 LLM 输出了看似合理的字段或规则，后续也必须经过系统 verifier。

### 4.2 `AttributeGrounder` 先做属性接地审计

`AttributeGrounder` 会把抽取出的 slot 标记成 `schema_grounded`、`confirmable`、`context_only`、`missing_schema` 或 `ignored_not_schema_mapped` 等状态。

这一步解决的是：用户说出的偏好是否真的能落到当前表格字段上。它不会执行查询，也不会把字段接地结果直接提升为 hard rule。

### 4.3 `RuleVerifier` 控制可执行性

`RuleVerifier` 是 legacy rule flow 的执行许可层。它检查：

- 字段是否在 active schema registry 中存在；
- 源列是否存在；
- operator 是否在 `allowed_ops` 中；
- value 是否存在且类型可解析；
- 是否存在语义歧义；
- 是否需要人工确认；
- 最终 `execution_level` 是 `executable`、`confirmable`、`rejected` 还是 `blocked`。

因此，“有字段”不等于“能执行”，“LLM 提到字段”更不等于“能执行”。

### 4.4 确认回路防止二轮自由文本直接执行

candidate rule 不能因为用户第二轮说“确认”就直接变成 SQL。运行时确认必须引用上一轮 `WorkbenchResponse` 里系统生成的 `candidate_id`。`workbench.confirm` 只接受上一轮响应和 `confirmed_candidate_ids`，不接受新的自由文本规则。

这避免了一个常见风险：用户或 LLM 在第二轮重新表述偏好，系统却把这段新文本当作已验证规则执行。

### 4.5 reviewed semantic path 控制语义查询

上传招生数据集的 `llm_semantic` 路径也遵循相同边界：

```text
DeepSeekSemanticIntentExtractor
-> EvidenceRequirementClassifier
-> PreferenceGrounder
-> SemanticQueryVerifier
-> SemanticSQLBuilder
-> DuckDBExecutor
```

其中 `EvidenceRequirementClassifier` 会先把偏好分成 `table_field`、`knowledge_base_or_reviewed_field`、`reviewed_ranking_policy`、`user_boundary` 或 `unsupported`。只有 `table_field` 继续进入 `PreferenceGrounder` 和 verifier；其他偏好进入未执行证据。

`SemanticQueryVerifier` 只接受 reviewed mapping 中存在且支持对应 op 的字段。`SemanticSQLBuilder` 只从 `VerifiedQueryPlan` 构造参数化 SQL，不接收用户或 LLM 原始 SQL。

### 4.6 排序必须经过 verified `RankingPlan`

LLM 可以提出候选 `RankingPlan`，但 `RankingVerifier` 必须验证：

- 排序字段是否在 reviewed mapping 中；
- 排序 operation 是否在白名单中；
- 字段类型是否支持该排序；
- 需要 value 的排序条件是否有可信来源，例如 `user_input`、`value_index`、`confirmed_boundary` 或 `reviewed_policy`。

验证失败时，系统保留 SQL 候选集，但只能称为候选列表，不能声称已经完成推荐排序。

### 4.7 `EvidencePack` 约束答案层

答案层只能读取 `EvidencePack`，不能读取 raw Excel。`TemplateReportBuilder` 是确定性答案生成器；`DeepSeekAnswerGenerator` 即使用 LLM，也只能使用证据包，并追加确定性证据覆盖清单。

`EvidencePack` 保留：

- 已执行规则；
- 候选确认；
- 未执行偏好；
- 缺字段偏好；
- 已确认规则和确认来源；
- `verified_query_plan`；
- `selection_evidence`；
- `ranking` 状态；
- planner trace 和 token usage。

这让回答的正确率不只依赖语言模型是否“说得像”，而依赖它是否被证据包约束。

## 5. 省 token 的做法

### 5.1 不把完整 Excel 发给 LLM

项目已有 token 预算评估显示，直接把完整 Excel 序列化后和用户问题一起发给 LLM，大约需要 `2304 万` input tokens，无法放入 `32k`、`128k` 或 `1M` 上下文。即使只保留 MVP 必需列，也大约需要 `48.4 万` input tokens，仍然不能放入 `32k` 或 `128k` 上下文。

这说明真正的问题不只是“换一个更大上下文模型”，而是不能把结构化大表当 prompt 知识库使用。

### 5.2 用 DuckDB 和 schema/value index 替代表格 prompt

系统把 Excel/CSV 离线落到 DuckDB，并生成 schema/value index。LLM 看到的是紧凑字段摘要、已审查字段、allowed ops、query options 和少量值证据，而不是全量行。

这种设计把 token 消耗从：

```text
用户问题 + 全量表格行
```

降为：

```text
用户问题 + 字段摘要 + 已审查操作 + 必要值证据
```

大规模行过滤、排序和聚合交给 DuckDB，而不是交给 LLM 逐行阅读。

### 5.3 LLM 调用被限制在高收益环节

当前 LLM 只在这些位置有条件参与：

- slot extraction；
- uploaded admissions 的 `SemanticIntent` proposal；
- evidence requirement classification；
- 候选 `RankingPlan` proposal；
- bounded candidates 内的可选 rerank；
- evidence-only answer generation。

规则验证、SQL 构造、SQL 执行、field review、fingerprint guard 和 response contract 都不需要 LLM。

`planner_mode=auto` 还会记录 LLM 是否调用、是否 fallback、fallback 原因和 token usage。显式 `planner_mode=legacy` 可以完全跳过 LLM semantic planner。

### 5.4 证据包压缩回答上下文

答案层不需要再次看到 Excel。它只需要紧凑 `EvidencePack`：

```text
executed_rules
candidate_confirmations
not_executed_preferences
result_count
top_k_results
execution_summary
verified_query_plan
ranking
warnings
```

这样既节省 token，也减少回答层编造新事实的空间。

### 5.5 工具接口限制输入面

LLM-safe tools 只包括：

```text
dataset.profile
dataset.review_summary
workbench.query
workbench.confirm
evidence.get
```

`workbench.query` 不接受 `sql`、`raw_sql`、`hard_rules`、`executable_rules` 或 `domain_pack_status` 等可绕过 verifier 的字段。工具 contract 让 LLM 只能提出查询请求和读取证据，不能直接改执行规则。

## 6. 提高正确率的做法

### 6.1 正确率定义不是“回答流畅”

项目评估的核心不是语言是否顺畅，而是：

- deterministic rules 是否抽取正确；
- candidate rules 是否被保留而不是越权执行；
- non-executable 偏好是否被拒绝；
- 是否没有 schema hallucination；
- trace 是否完整；
- answer 是否只引用 verified evidence。

这比普通 LLM 推荐评估更窄，但更符合本项目目标。

### 6.2 主安全指标是 over-promotion

本项目最重要的错误不是“没猜到用户想法”，而是把模糊或缺字段偏好错误提升为确定性规则。例如：

```text
学校稳一点 -> admission_probability = high
不想中外合作 -> cooperation_type != 中外合作
学校好一点 -> school_quality = good
就业好 -> employment_outlook = good
```

如果这些字段没有被 review 并进入 active schema，或者边界没有被用户确认，它们都不能执行。

### 6.3 schema-aware prompt 不能替代 verifier

已有正式评估报告记录，在 40 条模糊输入集合中：

| 方法 | 得分 | 成功率 | Total tokens | Over-promotion rate |
|---|---:|---:|---:|---:|
| `rule_regex_extractor_symbolic_verifier` | `320/320` | `1.000` | `0` | `0.000` |
| `deepseek_extractor_symbolic_verifier` | `320/320` | `1.000` | `25334` | `0.000` |
| `llm_only_baseline` | `107/200` | `0.535` | `24388` | `0.475` |
| `schema_aware_llm_only_baseline` | `156/200` | `0.780` | `42916` | `0.275` |

这组结果说明，给 LLM schema 信息能减少一部分 hallucination，但不能强制 rule lifecycle、confirmation protocol、schema-grounded execution 和 evidence-aligned answer generation。

### 6.4 单条 MVP 输入对比

代表输入是：

```text
我是广东物理类，排位32000，想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。
```

正式评估报告记录：

| 方法 | 结果行数 | 任务成功 | Total tokens | Over-promotion |
|---|---:|---:|---:|---|
| `regex_extractor_symbolic_verifier` | `93` | `5/5` | `0` | `0` |
| `deepseek_extractor_symbolic_verifier` | `93` | `5/5` | `834` | `0` |
| `llm_only_baseline` | `n/a` | `1/5` | `818` | `unsafe` |
| `schema_aware_llm_only_baseline` | `n/a` | `1/5` | `1282` | `unsafe` |

关键不是 DeepSeek 比 LLM-only 用更少 token，而是它的输出被 verifier 接管后，能同时保留“稳一点”“太贵”“中外合作”这类模糊或缺字段偏好的边界。

### 6.5 答案层也要评估

答案层评估显示：

| 模式 | 得分 | 说明 |
|---|---:|---|
| `llm_only_schema_sample` | `1/5` | 容易生成 `非中外合作`、`录取希望`、`非常稳妥` 等未验证结论 |
| `pipeline_template` | `5/5` | 完全由 `EvidencePack` 驱动 |
| `pipeline_deepseek_evidence` | `5/5` | LLM 文案被证据覆盖清单兜底 |

这说明正确率不仅取决于执行前 verifier，也取决于回答层是否只能看到 verified evidence。

## 7. 为什么这种方法同时省 token 又提高正确率

可以把当前方法概括为一句话：

```text
把 LLM 从“读全表并直接决策”降级为“读小摘要并提出候选”，把执行权交给 schema、verifier 和 DuckDB。
```

这同时带来两类收益。

第一，token 降低。LLM 不再读取全量 Excel，也不再持有全部候选行。它只读取字段摘要、已审查能力和必要上下文。真正的大数据操作由本地 DuckDB 完成。

第二，正确率提高。系统不要求 LLM 自己判断什么可执行，而是由 deterministic verifier 检查字段、op、值、确认状态和证据来源。LLM 语言能力用于覆盖自然语言表达的多样性，执行安全由规则系统保证。

更具体地说：

- 召回交给 LLM，精确许可交给 verifier；
- 大表存储交给 DuckDB，表格理解交给 schema/value index；
- 模糊知识进入 candidate 或 not-executed evidence，不直接进入 SQL；
- 推荐排序需要 verified `RankingPlan`，否则只给候选列表；
- 回答只能基于 `EvidencePack`，不能回读 raw Excel；
- 前端只展示 API 输出，不发明推荐逻辑。

## 8. 可以在正式汇报中使用的主论点

可以把报告主线写成三段：

第一段，问题定义。招生数据是结构化表格，用户输入却是模糊自然语言。如果直接让 LLM 读表并推荐，会遇到两个问题：token 成本随表格行数爆炸，且 LLM 会把“稳一点”“学校好一点”“不想中外合作”这类偏好过度解释为确定性规则。

第二段，方法。系统把自然语言理解和规则执行拆开。LLM 只提出候选 intent、slot 或 ranking plan；字段是否存在、操作是否允许、值是否可解析、是否需要确认、是否能生成 SQL，都由 deterministic verifier 决定。大表进入 DuckDB，字段和值进入 schema/value index，答案层只读取 EvidencePack。

第三段，结果。正式评估中，verifier-based 方法在 40 条模糊输入上达到 `320/320`，over-promotion 为 `0.000`；LLM-only baseline 即使看到 schema，仍有 `0.275` over-promotion rate。token 预算上，完整 Excel 直接 prompt 约 `2304 万` tokens，而 DeepSeek extractor + symbolic verifier 的代表输入只用 `834` tokens 并得到同样 `93` 条 verified result。

## 9. 限制和下一步

当前结论仍有明确限制：

- 评估集规模仍然较小，40 条模糊输入不能代表真实用户全部表达。
- regex baseline 是人工整理的 conservative benchmark，不是最终抽取策略。
- 当前指标主要评估 rule safety、traceability 和 evidence alignment，不评估最终志愿填报质量。
- 一年历史位次数据不足以支撑完整志愿顾问结论。
- 未审查字段、外部知识和主观价值判断仍然不能执行，需要后续引入 reviewed structured fields、reviewed KB 或明确人工边界。

后续可以补强：

- 扩展模糊输入评估到 50 到 100 条；
- 增加对冲突输入、超短输入、长段输入和 adversarial prompt 的测试；
- 单独报告 schema hallucination rate 和 trace completeness；
- 为就业、城市发展、合作办学、专项计划等外部知识建立 reviewed evidence source，而不是让 LLM 临场推断；
- 继续把 `EvidencePack` 作为唯一答案输入，防止回答层绕过执行证据。

## 10. 本报告取证来源

本报告主要依据以下项目文件：

- `README.md`
- `docs/methodology_report.md`
- `docs/evaluation_report.md`
- `docs/api_contract.md`
- `docs/tool_contract.md`
- `docs/real_dataset_pilot.md`
- `src/api/workbench.py`
- `src/schema/attribute_grounder.py`
- `src/schema/value_entity_linker.py`
- `src/rules/rule_classifier.py`
- `src/rules/rule_verifier.py`
- `src/rules/rule_promoter.py`
- `src/semantic/llm_intent_extractor.py`
- `src/semantic/evidence_requirement_gate.py`
- `src/semantic/preference_grounder.py`
- `src/semantic/query_verifier.py`
- `src/semantic/sql_builder.py`
- `src/semantic/ranking_verifier.py`
- `src/reporting/evidence_pack.py`
- `src/reporting/template_report_builder.py`
- `src/reporting/deepseek_answer_generator.py`
- `src/adapters/data_warehouse.py`
- `src/executors/duckdb_executor.py`

评估数字以 `docs/evaluation_report.md` 中的正式对比口径为准。当前本地 `outputs/eval/fuzzy_eval_results.json` 可能是 regex-only 快速运行缓存，不能单独代表完整 DeepSeek 和 LLM-only baseline 对比。
