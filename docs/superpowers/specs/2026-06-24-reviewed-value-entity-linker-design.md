# Reviewed Value Entity Linker 设计

## 背景

当前 Workbench 可以通过 `SchemaValueIndex` 审计抽取值是否存在于已审核字段的值索引中，
也可以通过 `AttributeGrounder` 阻止没有 value evidence 的 hard filter。但它还没有一个
专门处理“同一段文本命中多个字段值”的 runtime 层。

典型问题是：

```text
我想进深圳大学，目前排位15000，帮我看看有什么专业可以选
```

现有流程会把 `深圳大学` 中的子串 `深圳` 接地为 `city=深圳`，但没有把完整实体
`深圳大学` 接地为 `university_name=深圳大学`。结果返回所有深圳城市高校，而不是深圳大学。

这个问题不能用硬编码学校名单解决。安全边界仍然是：

```text
Natural language may propose structure, but only verified schema-grounded rules may execute.
```

因此需要的是一个通用、数据集驱动、reviewed-field 驱动的 value entity linker：
自然语言和 LLM 只能提出候选 span；系统只能基于当前 `schema/value index`、reviewed field
metadata 和通用冲突规则生成可执行候选。

## 目标

新增 `ReviewedValueEntityLinker` 规划为 runtime grounding aid，用于在 rule construction 前处理
已审核字段值实体：

- 从用户原文和 LLM/regex 抽取结果中识别候选 span。
- 使用当前数据集的 `SchemaValueIndex` 查找 reviewed field 的 exact value evidence。
- 对重叠命中做通用冲突解析，避免把完整实体内部子串提升为另一条 hard rule。
- 在证据充分时生成可执行候选 filter。
- 在证据不足、字段索引不完整、多个完整实体冲突或表达需要用户确认时，进入
  `candidates_to_confirm`、`not_executed_preferences` 或 `unanswerable_intents`。
- 在 `EvidencePack` 中记录 entity linking evidence，让回答解释“按院校名称=深圳大学理解”，
  但不声称未执行的地理泛化。

## 非目标

- 不写死任何大学、城市、专业或别名名单。
- 不把所有大学维护成代码里的先验知识。
- 不自动把 `深圳大学` 改写成 `深圳的大学`。
- 不让 LLM 直接决定实体字段、最终 filter 或 SQL。
- 不替代 `AttributeGrounder`、`RuleVerifier`、`SemanticQueryVerifier` 或
  `EvidenceRequirementClassifier`。
- 不实现 reviewed KB ingestion。
- 不实现复杂别名图谱。第一版只预留 reviewed alias table 的接口，不默认引入别名执行。

## 适用范围

第一版优先接入 legacy verified admissions Workbench flow，因为 bug 出现在默认内置 admissions
流程中：

```text
Extractor
-> AttributeGrounder
-> ReviewedValueEntityLinker
-> RuleClassifier
-> RuleVerifier
-> RulePromoter
-> Executor
```

后续可把同一个 linker 接入 uploaded semantic flow：

```text
DeepSeekSemanticIntentExtractor
-> EvidenceRequirementClassifier
-> ReviewedValueEntityLinker
-> PreferenceGrounder
-> SemanticQueryVerifier
```

第一版不强制覆盖 uploaded semantic flow，避免和刚接入的 evidence gate 同时扩大运行面。

## 组件设计

### EntityLinkableFieldPolicy

在 domain config 或 schema field metadata 中声明哪些 reviewed 字段可参与实体链接。第一版可从
现有 `schema_registry.json` 派生，不新增大规模配置：

- 字段必须 active。
- 字段类型必须是文本、枚举或 category。
- 字段必须有完整 `lookup_values`，或该字段明确标记允许 partial index 仅产生 confirmation。
- 字段必须支持 `eq`，或显式声明 entity linking 可生成的操作。

admissions 第一版建议启用：

- `university_name`：生成 `eq`。
- `city`：只在地理表达模式下生成 `contains` / `in_contains`，不能从完整院校实体内部子串生成。
- `major_name`：保守处理，只对用户明确“专业是 X”或 LLM 已抽取专业 span 时参与。

这个 policy 是字段能力，不是字段值名单。

### ReviewedValueEntityLinker

输入：

- `user_text`；
- `SchemaRegistry`；
- `SchemaValueIndex`；
- domain field policy；
- 可选的 extractor slots / LLM preferences，用作候选 span source；
- 可选 reviewed alias records。

输出：

- `accepted_links`：已解析且可进入后续 rule construction 的实体链接。
- `suppressed_links`：因为被更长完整实体覆盖而不执行的子串命中。
- `ambiguous_links`：多个同等级命中或意图不清，不能自动执行。
- `not_executed_preferences`：证据不足或需要确认的用户偏好。
- `trace`：字段、值、span、match type、index fingerprint、resolution reason。

### Entity Link 记录

每个 link 至少包含：

```json
{
  "link_id": "entity_link_001",
  "source_text": "深圳大学",
  "span": [3, 7],
  "field_id": "university_name",
  "source_column": "院校名称",
  "value": "深圳大学",
  "op": "eq",
  "match_type": "exact_full_span",
  "value_evidence": {
    "source": "schema_value_index",
    "status": "exact_match",
    "lookup_complete": true,
    "matched_values": ["深圳大学"]
  },
  "resolution": "accepted_longest_exact_entity"
}
```

被抑制的城市子串记录为：

```json
{
  "source_text": "深圳",
  "field_id": "city",
  "value": "深圳",
  "match_type": "substring_inside_exact_entity",
  "executable": false,
  "resolution": "suppressed_by_university_name_exact_full_span"
}
```

## 匹配策略

### Span 生成

第一版使用保守 span 来源：

- 用户原文中与 `lookup_values` 完整相等的连续 substring。
- extractor / LLM 已给出的 `source_text`。
- reviewed alias 命中后映射出的 canonical value。

不使用模糊向量召回，不使用拼音纠错，不使用未审核外部百科。

### 值查找

对每个候选 span 和 linkable field：

- exact value match 才能直接产生 executable candidate。
- contains match 不能直接执行，只能作为 confirmation candidate 或 diagnostic。
- `lookup_complete=false` 时，exact match 可以产生候选，但必须标记 index incomplete；
  是否执行取决于 field policy。默认不执行，要求确认或降级 not executed。

### 冲突解析

通用优先级：

1. exact full-span match 优先于 substring match。
2. 更长 span 优先于更短 span。
3. reviewed alias canonical match 优先于裸 substring match，但不优先于用户原文 exact full-span。
4. 地理字段命中若完全位于另一个 accepted entity span 内，默认 suppress。
5. 两个同长度、同等级、不同字段的 exact full-span match 同时存在时，不自动执行，进入
   confirmation candidate。

这些规则只比较 match evidence，不包含任何具体学校、城市或专业 hardcode。

## 意图表达边界

`深圳大学`：

- 若 `university_name=深圳大学` 在 value index exact 命中，执行院校名称。
- 抑制内部 `city=深圳`。
- 回答中说明“我按院校名称=深圳大学理解；如果你想查深圳市高校，请说深圳的大学或深圳市高校。”

`深圳的大学`、`深圳市高校`、`在深圳读大学`：

- 这是地理表达模式。
- 若 `city=深圳` 存在 reviewed value evidence，执行城市。
- 不自动执行 `university_name=深圳大学`。

`深圳大学附近`、`深圳大学那边`：

- 不等同院校筛选，也不等同城市筛选。
- 进入 `not_executed_preferences`，原因是需要地理距离或用户确认边界。

`深大`：

- 只有 reviewed alias table 存在 `深大 -> 深圳大学` 时，才可转成院校实体。
- 没有 alias evidence 时不能执行，进入 candidate 或 not executed。

## 和现有链路的关系

### Legacy verified flow

`ReviewedValueEntityLinker` 不直接执行 SQL。它只生成 verified-rule 候选需要的结构：

- 可执行 entity links 转为 slots 或 proposed rules；
- ambiguous links 转为 confirmation candidates；
- suppressed links 进入 EvidencePack trace；
- not executed links 进入 `non_executable_preferences`。

`RuleVerifier` 仍是 hard rule 的最终边界。

### Uploaded semantic recommendation

未来接入时，linker 只处理 gate 后仍属于 `table_field` 的 preferences。需要 reviewed KB、
ranking policy 或用户边界的偏好仍由 `EvidenceRequirementClassifier` 分流，不进入 linker。

`PreferenceGrounder` 仍负责 reviewed mapping 和 allowed operation。

## EvidencePack 与回答

新增或扩展 `EvidencePack` 中的 trace 节点：

```json
{
  "entity_linking": {
    "status": "applied",
    "accepted_links": [],
    "suppressed_links": [],
    "ambiguous_links": [],
    "not_executed_links": []
  }
}
```

回答层只能基于这个 evidence 解释：

- 哪个实体被执行；
- 哪些重叠命中被抑制；
- 用户如何改写才能表达另一个意图。

回答不能把 suppressed city 当作已执行 filter，也不能推荐 EvidencePack 之外的新行。

## 错误与降级

- `SchemaValueIndex` 缺失：linker 不运行，记录 `status=value_index_unavailable`，不产生 hard rule。
- field 未 active：不产生 hard rule。
- lookup incomplete：默认不产生 hard rule，只产生 confirmation candidate，除非 field policy 明确允许。
- 多字段 exact full-span 冲突：不执行，要求确认。
- 运行异常：fail closed，不新增 rule；legacy flow 可继续使用原有抽取规则，但必须记录 linker failure
  trace，避免误以为 entity linking 生效。

## 测试策略

### 单元测试

- `深圳大学` 命中 `university_name=深圳大学`，抑制 `city=深圳`。
- `深圳的大学` 命中 `city=深圳`，不命中 `university_name=深圳大学`。
- `深圳大学附近` 不执行院校或城市，进入 not executed。
- 同一 span 同时 exact 命中两个字段时进入 ambiguous。
- `lookup_complete=false` 时默认不执行。
- 缺少 value index 时 fail closed。

### 集成测试

- Workbench prompt `我想进深圳大学，目前排位15000，帮我看看有什么专业可以选`：
  `executed_filters` 必须包含 `院校名称=深圳大学`，不能只包含 `城市=深圳`。
- top results 的 `university_name` 必须全为 `深圳大学`。
- warnings 必须保留缺少科类、再选科目和未确认位次窗口。
- prompt `我想去深圳的大学，目前排位15000`：
  `executed_filters` 包含 `城市=深圳`，不包含 `院校名称=深圳大学`。

## 文档同步

实现时需要同步更新：

- `README.md` 的语义能力或 Workbench 行为说明；
- `docs/api_contract.md` 的 EvidencePack trace 字段；
- `docs/methodology_report.md` 的 verifier 边界说明；
- 如果 API payload snapshot 有相关断言，需要同步更新。

## 验收标准

- 不新增硬编码学校名单。
- 不扩大 LLM 的执行权限。
- `深圳大学` 不再被误执行为 `city=深圳`。
- `深圳的大学` 仍可执行为地理筛选。
- 模糊或附近类表达不自动执行。
- 所有新增 hard rule 都可追溯到 reviewed field、value index 和 verifier。
