# 语义能力系统重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目从固定 admissions schema 的推荐工具升级为 LLM 辅助的 reviewed semantic capability system，并先交付“新招生 Excel 按专业最低位次生成冲稳保”的可验证后端垂直切片。

**Architecture:** 新增通用能力层：上传数据先形成字段事实、语义候选、已审核映射、能力图和候选 `QueryAST`；只有通过 `FieldGrounder`、`OperationVerifier`、`AnswerabilityGate` 的查询计划才能由 `SQLBuilder` 生成参数化 SQL。admissions 作为第一个 domain recipe，只在已审核字段支持 `major_min_rank` 时执行专业最低位次冲稳保；LLM 只能提出字段语义和查询意图候选，执行与回答仍由 deterministic verifier 和 `EvidencePack` 约束。

**Tech Stack:** Python `unittest`、DuckDB、Pandas/OpenPyXL、Pydantic v2、现有 `DatasetService` / `DomainConfig` / `EvidencePack` / Workbench contract、可选 DeepSeek/OpenAI structured-output candidate provider、`git diff --check`。

---

## 范围检查

这是一个后端垂直切片计划，不一次性完成所有领域和完整前端重构。它必须完成：

- 任意上传表可生成能力图，说明字段、可执行操作、可回答 query type 和不可回答原因。
- 语义映射必须经过 review seed 或明确 approve 才能执行。
- 自然语言只能生成候选 `QueryAST`，不能直接执行 raw SQL。
- 对新招生表结构支持 `专业`、`最低位次`、`最低分数`、`学校所在`、`所属专业组` 等字段的已审核映射。
- 对提示词 `广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名` 生成可复现的专业最低位次冲稳保结果。
- `EvidencePack` 明确记录 `answerable_intents` 与 `unanswerable_intents`。

本计划不完成：

- 通用多领域推荐算法。
- 任意 SQL 文本执行。
- 前端完整 redesign。
- 将大 Excel 原件、DuckDB 或上传目录提交进版本库。
- 使用 LLM 绕过 reviewer 批准字段语义。

## 外部资源研究结论

本计划采用可本地验证的最小依赖。已安装或现有代码已经使用、且本阶段直接采用：

- `duckdb`: 继续作为 verified plan 的参数化 SQL 执行层，参考 DuckDB prepared statements 与 Python DB API 文档。
- `pandas` / `openpyxl`: 继续用于 Excel/CSV 读取、profile 和测试夹具。
- `pydantic`: 用于 `QueryAST`、LLM 候选输出和 verifier 输入的结构化校验。现有 API 已通过 FastAPI 间接使用 Pydantic；实现 Task 1 时如果 `requirements.txt` 仍未显式声明，应补充 `pydantic>=2.0,<3.0`。

本阶段只作为设计参考，不新增依赖：

- `SQLGlot`: 适合后续解析 SQL-like 用户输入；当前阶段仍拒绝 raw SQL。
- Frictionless Table Schema: 可参考 portable table metadata 设计；不引入 runtime dependency。
- dbt Semantic Layer / MetricFlow、LookML、Malloy、Cube: 参考“semantic model -> governed SQL”思想，不替换本项目 verifier。
- Spider、BIRD、DIN-SQL、CHESS: 参考 text-to-SQL 的 schema linking、分解式生成和验证步骤；不把 LLM 生成 SQL 作为执行路径。

研究来源：

- DuckDB prepared statements: <https://duckdb.org/docs/current/sql/query_syntax/prepared_statements.html>
- DuckDB Python DB API: <https://duckdb.org/docs/lts/clients/python/dbapi.html>
- Pydantic JSON Schema / validation: <https://pydantic.dev/docs/validation/latest/concepts/json_schema/>
- OpenAI Agents structured output reference: <https://openai.github.io/openai-agents-python/ref/agent_output/>
- SQLGlot: <https://sqlglot.com/>
- Frictionless Table Schema: <https://frictionlessdata.io/specs/table-schema/>
- dbt Semantic Layer / MetricFlow: <https://docs.getdbt.com/docs/use-dbt-semantic-layer/dbt-sl>
- LookML: <https://docs.cloud.google.com/looker/docs/what-is-lookml>
- Malloy: <https://docs.malloydata.dev/>
- Cube semantic layer: <https://docs.cube.dev/docs/introduction>
- Spider: <https://arxiv.org/abs/1809.08887>
- BIRD: <https://arxiv.org/abs/2305.03111>
- DIN-SQL: <https://arxiv.org/abs/2304.11015>
- CHESS: <https://arxiv.org/abs/2405.16755>

## 文件结构

- Modify: `requirements.txt`
  - 显式声明 `pydantic>=2.0,<3.0`，避免只依赖 FastAPI 的传递依赖。
- Create: `src/semantic/__init__.py`
  - 暴露语义能力系统的公共类型和服务。
- Create: `src/semantic/query_ast.py`
  - 定义 `QueryAST`、`QueryFilter`、`QuerySort`、`VerifiedQueryPlan`、`QueryVerificationIssue`。
- Create: `src/semantic/capability_graph.py`
  - 定义 `DatasetCapabilityGraph`、`CapabilityField`，并从 dataset/profile 构建能力图。
- Create: `src/semantic/semantic_candidates.py`
  - 规则优先生成字段语义候选；保留 `LLMSemanticCandidateProvider` protocol，测试使用 fake provider。
- Create: `src/semantic/reviewed_mapping.py`
  - 读取 domain pack 中的 reviewed mapping seed，并校验字段存在、类型和 op。
- Create: `src/semantic/query_verifier.py`
  - 实现 `FieldGrounder`、`OperationVerifier`、`AnswerabilityGate`。
- Create: `src/semantic/sql_builder.py`
  - 从 `VerifiedQueryPlan` 生成参数化 DuckDB SQL，不接受 raw SQL。
- Create: `src/semantic/admissions_major_rank.py`
  - admissions 专业最低位次冲稳保 recipe：物化生选科、特殊限制标记/排除、冲稳保分层、结果投影。
- Modify: `domains/admissions/domain.json`
  - 增加 `semantic_capabilities` 配置路径和 admissions 新表 reviewed mapping seed。
- Create: `domains/admissions/semantic_capabilities.json`
  - 保存 admissions reviewed semantic mapping、query recipes、unsupported capability 文案。
- Modify: `src/domains/domain_config.py`
  - 增加 `semantic_capabilities_path` 和 `semantic_capabilities` 读取入口。
- Modify: `src/api/dataset_service.py`
  - 在 profile/review/build/query 流程中暴露 capability graph；query 时优先尝试 capability-aware planned query。
- Modify: `src/api/workbench.py`
  - `run_workbench` 在旧 admissions planner 前尝试 semantic capability path；失败必须返回 `blocked` 或 `needs_confirmation`，不能隐藏成 `error`。
- Modify: `src/reporting/evidence_pack.py`
  - 增加 `answerable_intents`、`unanswerable_intents`、`verified_query_plan`、`capability_graph_summary`。
- Modify: `src/reporting/template_report_builder.py`
  - 使用 EvidencePack 生成“已执行依据 / 未执行依据 / 结果表”。
- Create: `tests/semantic_test_utils.py`
  - 构造不提交大 Excel 的新招生表小样本。
- Create: `tests/test_semantic_capability_graph.py`
  - 验证字段能力和 reviewed mapping。
- Create: `tests/test_semantic_query_verifier.py`
  - 验证 `QueryAST` 接地、op 校验、raw SQL 拒绝、unsupported intent。
- Create: `tests/test_semantic_sql_builder.py`
  - 验证参数化 SQL 与排序。
- Create: `tests/test_semantic_admissions_major_rank.py`
  - 验证 10000 名冲稳保分层和特殊限制排除。
- Modify: `tests/test_uploaded_dataset_flow.py`
  - 增加 uploaded admissions 新表结构的 queryable 端到端测试。
- Modify: `tests/test_workbench_api_contract.py`
  - 验证新增 EvidencePack 字段不改变 top-level contract。
- Modify: `docs/api_contract.md`
  - 记录 capability-aware query、EvidencePack 新字段和 raw SQL 边界。
- Modify: `docs/methodology_report.md`
  - 记录 LLM proposes / System verifies / SQL executes / EvidencePack constrains answer。
- Modify: `README.md`
  - 说明上传表能力判断、能答/不能答、以及新招生表专业最低位次模式。

---

### Task 1: 增加 QueryAST 基础类型和 raw SQL 拒绝测试

**Files:**
- Modify: `requirements.txt`
- Create: `src/semantic/__init__.py`
- Create: `src/semantic/query_ast.py`
- Create: `tests/test_semantic_query_verifier.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_semantic_query_verifier.py` with this initial content:

```python
from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.semantic.query_ast import (
    QueryAST,
    QueryFilter,
    QuerySort,
    QueryVerificationIssue,
)


class QueryASTTest(unittest.TestCase):
    def test_query_ast_rejects_raw_sql_payload(self) -> None:
        with self.assertRaises(ValidationError):
            QueryAST.from_candidate(
                {
                    "raw_sql": "SELECT * FROM admissions",
                    "filters": [],
                    "sort": [],
                }
            )

    def test_query_ast_normalizes_filters_and_sort(self) -> None:
        ast = QueryAST.from_candidate(
            {
                "intent": "table_filter",
                "select": ["university_name", "major_name"],
                "filters": [
                    {"field_id": "year", "op": "eq", "value": 2025},
                    {
                        "field_id": "major_min_rank",
                        "op": "between",
                        "value": [10000, 15000],
                    },
                ],
                "sort": [{"field_id": "major_min_rank", "direction": "asc"}],
                "limit": 30,
            }
        )

        self.assertEqual(ast.intent, "table_filter")
        self.assertEqual(ast.select, ["university_name", "major_name"])
        self.assertEqual(
            ast.filters,
            [
                QueryFilter(field_id="year", op="eq", value=2025),
                QueryFilter(
                    field_id="major_min_rank",
                    op="between",
                    value=[10000, 15000],
                ),
            ],
        )
        self.assertEqual(
            ast.sort,
            [QuerySort(field_id="major_min_rank", direction="asc")],
        )
        self.assertEqual(ast.limit, 30)

    def test_verification_issue_serializes(self) -> None:
        issue = QueryVerificationIssue(
            code="missing_field",
            severity="error",
            message="字段不存在。",
            field_id="city",
        )

        self.assertEqual(
            issue.to_dict(),
            {
                "code": "missing_field",
                "severity": "error",
                "message": "字段不存在。",
                "field_id": "city",
            },
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_query_verifier.QueryASTTest
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.semantic'`.

- [ ] **Step 3: 创建 QueryAST 类型**

If `requirements.txt` does not explicitly list Pydantic, add:

```text
pydantic>=2.0,<3.0
```

Create `src/semantic/query_ast.py`:

```python
"""受控查询计划的数据结构。

自然语言和 LLM 只能产生候选 QueryAST；SQLBuilder 只接受 verifier
确认后的 VerifiedQueryPlan。
"""

from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ALLOWED_SORT_DIRECTIONS = {"asc", "desc"}


class QueryFilter(BaseModel):
    """候选查询过滤条件。"""

    model_config = ConfigDict(frozen=True)

    field_id: str
    op: str
    value: Any

    @field_validator("field_id", "op")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("QueryFilter field_id and op are required.")
        return normalized


class QuerySort(BaseModel):
    """候选查询排序条件。"""

    model_config = ConfigDict(frozen=True)

    field_id: str
    direction: str = "asc"

    @field_validator("field_id")
    @classmethod
    def _field_id_required(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("QuerySort field_id is required.")
        return normalized

    @field_validator("direction")
    @classmethod
    def _direction_allowed(cls, value: str) -> str:
        direction = str(value or "asc").lower()
        if direction not in ALLOWED_SORT_DIRECTIONS:
            raise ValueError(f"Unsupported sort direction: {direction}")
        return direction


class QueryAST(BaseModel):
    """LLM 或规则生成的候选查询计划。"""

    model_config = ConfigDict(frozen=True)

    intent: str = "table_filter"
    select: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[QuerySort] = Field(default_factory=list)
    limit: int = 30
    requested_output: list[str] = Field(default_factory=list)
    source: str = "candidate"
    raw_sql: str | None = Field(default=None, exclude=True)

    @classmethod
    def from_candidate(cls, payload: dict[str, Any]) -> "QueryAST":
        return cls.model_validate(payload)

    @model_validator(mode="after")
    def _reject_raw_sql(self) -> "QueryAST":
        if self.raw_sql:
            raise ValueError("Raw SQL is not accepted; use verified QueryAST.")
        return self

    @field_validator("intent", "source", mode="before")
    @classmethod
    def _non_empty_string(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("QueryAST intent and source are required.")
        return normalized

    @field_validator("limit", mode="before")
    @classmethod
    def _limit_bounds(cls, value: Any) -> int:
        normalized = int(value or 30)
        if normalized < 1:
            raise ValueError("QueryAST limit must be positive.")
        return min(normalized, 100)


class QueryVerificationIssue(BaseModel):
    """查询计划验证问题。"""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str
    field_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = self.model_dump(exclude={"details"}, exclude_none=True)
        payload.update(self.details)
        return payload


class VerifiedQueryPlan(BaseModel):
    """已验证、可生成参数化 SQL 的查询计划。"""

    model_config = ConfigDict(frozen=True)

    intent: str
    table_name: str
    select_columns: list[dict[str, str]]
    filters: list[dict[str, Any]]
    sort: list[dict[str, str]]
    limit: int
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]
```

Create `src/semantic/__init__.py`:

```python
"""Semantic capability system public API."""

from src.semantic.query_ast import (
    QueryAST,
    QueryFilter,
    QuerySort,
    QueryVerificationIssue,
    VerifiedQueryPlan,
)

__all__ = [
    "QueryAST",
    "QueryFilter",
    "QuerySort",
    "QueryVerificationIssue",
    "VerifiedQueryPlan",
]
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_query_verifier.QueryASTTest
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add requirements.txt src/semantic/__init__.py src/semantic/query_ast.py tests/test_semantic_query_verifier.py
git commit -m "feat: add verified query ast primitives"
```

---

### Task 2: 增加新招生表小样本和能力图

**Files:**
- Create: `tests/semantic_test_utils.py`
- Create: `src/semantic/capability_graph.py`
- Create: `tests/test_semantic_capability_graph.py`

- [ ] **Step 1: 写测试夹具**

Create `tests/semantic_test_utils.py`:

```python
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

import pandas as pd

from scripts.generate_domain_pack import load_source_dataset
from src.adapters.excel_adapter import ExcelDataSet


NEW_ADMISSIONS_ROWS = [
    {
        "年份": 2025,
        "院校名称": "中山大学",
        "院校代码": "10558",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "预防医学",
        "专业代码": "095",
        "所属专业组": "（219）",
        "专业备注": "（深圳校区）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 5,
        "最低分数": 630,
        "最低位次": 9850,
        "学校所在": "广东",
        "学校性质": "公办",
        "是否985": "是",
        "是否211": "是",
    },
    {
        "年份": 2025,
        "院校名称": "深圳大学",
        "院校代码": "10590",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "计算机科学与技术",
        "专业代码": "080901",
        "所属专业组": "（230）",
        "专业备注": "（粤海校区）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 24,
        "最低分数": 628,
        "最低位次": 10257,
        "学校所在": "广东",
        "学校性质": "公办",
        "是否985": "否",
        "是否211": "否",
    },
    {
        "年份": 2025,
        "院校名称": "暨南大学",
        "院校代码": "10559",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "软件工程",
        "专业代码": "080902",
        "所属专业组": "（222）",
        "专业备注": "（番禺校区）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 42,
        "最低分数": 616,
        "最低位次": 16212,
        "学校所在": "广东",
        "学校性质": "公办",
        "是否985": "否",
        "是否211": "是",
    },
    {
        "年份": 2025,
        "院校名称": "电子科技大学",
        "院校代码": "19614",
        "科类": "物理类",
        "批次": "本科批",
        "专业": "电子信息类",
        "专业代码": "008",
        "所属专业组": "（204）",
        "专业备注": "（中外合作办学）",
        "选科要求": "首选物理，再选化学",
        "录取人数": 10,
        "最低分数": 630,
        "最低位次": 9850,
        "学校所在": "四川",
        "学校性质": "公办",
        "是否985": "是",
        "是否211": "是",
    },
]


def write_new_admissions_excel(path: Path) -> Path:
    pd.DataFrame(NEW_ADMISSIONS_ROWS).to_excel(path, index=False)
    return path


def new_admissions_dataset() -> Iterator[ExcelDataSet]:
    with TemporaryDirectory() as directory:
        workbook = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
        yield load_source_dataset(workbook)
```

- [ ] **Step 2: 写能力图失败测试**

Create `tests/test_semantic_capability_graph.py`:

```python
from __future__ import annotations

import unittest

from src.semantic.capability_graph import DatasetCapabilityGraph
from tests.semantic_test_utils import new_admissions_dataset


class SemanticCapabilityGraphTest(unittest.TestCase):
    def test_graph_profiles_new_admissions_columns(self) -> None:
        dataset = next(new_admissions_dataset())

        graph = DatasetCapabilityGraph.from_dataset(dataset)

        self.assertEqual(graph.row_count, 4)
        self.assertIn("专业", graph.fields)
        self.assertEqual(graph.fields["最低位次"].inferred_type, "number")
        self.assertIn("between", graph.fields["最低位次"].candidate_ops)
        self.assertIn("contains", graph.fields["专业"].candidate_ops)
        self.assertIn("sort", graph.fields["最低分数"].candidate_ops)

    def test_graph_records_missing_common_admissions_columns(self) -> None:
        dataset = next(new_admissions_dataset())

        graph = DatasetCapabilityGraph.from_dataset(dataset)

        self.assertIn("学费", graph.missing_source_columns)
        self.assertIn("城市", graph.missing_source_columns)
        self.assertIn("专业组最低位次1", graph.missing_source_columns)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_capability_graph
```

Expected: FAIL with `ModuleNotFoundError` or missing `DatasetCapabilityGraph`.

- [ ] **Step 4: 实现能力图**

Create `src/semantic/capability_graph.py`:

```python
"""数据集能力图。

能力图只记录字段事实和候选操作，不代表字段语义已经可执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.adapters.excel_adapter import ExcelDataSet, cell_text
from src.adapters.data_warehouse import _parse_number


COMMON_ADMISSIONS_SOURCE_COLUMNS = {
    "生源地",
    "专业名称",
    "专业组最低位次1",
    "专业组最低分1",
    "最低位次1",
    "最低分1",
    "城市",
    "学费",
}


@dataclass(frozen=True)
class CapabilityField:
    """单个源列的字段事实。"""

    source_column: str
    inferred_type: str
    non_null_count: int
    distinct_count: int
    sample_values: list[str]
    numeric_min: float | None = None
    numeric_max: float | None = None
    candidate_ops: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "inferred_type": self.inferred_type,
            "non_null_count": self.non_null_count,
            "distinct_count": self.distinct_count,
            "sample_values": self.sample_values,
            "numeric_min": self.numeric_min,
            "numeric_max": self.numeric_max,
            "candidate_ops": self.candidate_ops,
        }


@dataclass(frozen=True)
class DatasetCapabilityGraph:
    """数据集字段能力图。"""

    source_path: str
    sheet_name: str
    row_count: int
    column_count: int
    fields: dict[str, CapabilityField]
    missing_source_columns: list[str]

    @classmethod
    def from_dataset(cls, dataset: ExcelDataSet) -> "DatasetCapabilityGraph":
        fields = {}
        for column in dataset.headers:
            if not column or column not in dataset.dataframe.columns:
                continue
            fields[column] = _field_profile(column, dataset.dataframe[column])
        missing = sorted(
            column
            for column in COMMON_ADMISSIONS_SOURCE_COLUMNS
            if column not in fields
        )
        return cls(
            source_path=str(dataset.workbook_path),
            sheet_name=dataset.sheet_name,
            row_count=len(dataset.dataframe),
            column_count=len(dataset.headers),
            fields=fields,
            missing_source_columns=missing,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "sheet_name": self.sheet_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "fields": {
                key: value.to_dict()
                for key, value in self.fields.items()
            },
            "missing_source_columns": self.missing_source_columns,
        }


def _field_profile(column: str, series: pd.Series) -> CapabilityField:
    cleaned = [cell_text(value) for value in series.dropna().tolist()]
    cleaned = [value for value in cleaned if value]
    distinct = list(dict.fromkeys(cleaned))
    numbers = [_parse_number(value) for value in cleaned]
    numeric_values = [value for value in numbers if value is not None]
    numeric_ratio = len(numeric_values) / len(cleaned) if cleaned else 0
    if cleaned and numeric_ratio >= 0.95:
        inferred = "number"
    elif len(distinct) <= 50:
        inferred = "enum_or_category"
    elif max((len(item) for item in distinct[:20]), default=0) > 60:
        inferred = "long_text"
    else:
        inferred = "string"
    return CapabilityField(
        source_column=column,
        inferred_type=inferred,
        non_null_count=len(cleaned),
        distinct_count=len(distinct),
        sample_values=distinct[:8],
        numeric_min=min(numeric_values) if numeric_values else None,
        numeric_max=max(numeric_values) if numeric_values else None,
        candidate_ops=_candidate_ops(inferred),
    )


def _candidate_ops(inferred_type: str) -> list[str]:
    if inferred_type == "number":
        return ["eq", "<=", ">=", "between", "sort"]
    if inferred_type == "enum_or_category":
        return ["eq", "in", "not_in", "sort"]
    if inferred_type in {"string", "long_text"}:
        return ["contains", "eq", "sort"]
    return []
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_capability_graph
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add src/semantic/capability_graph.py tests/semantic_test_utils.py tests/test_semantic_capability_graph.py
git commit -m "feat: build dataset capability graph"
```

---

### Task 3: 增加语义候选和 reviewed mapping registry

**Files:**
- Create: `src/semantic/semantic_candidates.py`
- Create: `src/semantic/reviewed_mapping.py`
- Create: `domains/admissions/semantic_capabilities.json`
- Modify: `domains/admissions/domain.json`
- Modify: `src/domains/domain_config.py`
- Modify: `tests/test_semantic_capability_graph.py`

- [ ] **Step 1: 写 reviewed mapping 测试**

Append to `tests/test_semantic_capability_graph.py`:

```python
from src.domains import DomainConfig
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.semantic_candidates import RuleBasedSemanticCandidateGenerator


class SemanticMappingTest(unittest.TestCase):
    def test_rule_based_candidates_for_new_admissions_headers(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)

        candidates = RuleBasedSemanticCandidateGenerator().generate(graph)
        by_field = {
            candidate["canonical_field_id"]: candidate
            for candidate in candidates
        }

        self.assertEqual(by_field["major_name"]["source_column"], "专业")
        self.assertEqual(by_field["major_min_rank"]["source_column"], "最低位次")
        self.assertEqual(by_field["major_min_score"]["source_column"], "最低分数")
        self.assertEqual(by_field["school_province"]["source_column"], "学校所在")

    def test_reviewed_mapping_registry_activates_only_existing_columns(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        domain = DomainConfig.load("admissions")

        registry = ReviewedMappingRegistry.from_domain(domain, graph)

        self.assertEqual(registry.source_column("major_name"), "专业")
        self.assertEqual(registry.source_column("major_min_rank"), "最低位次")
        self.assertTrue(registry.has_op("major_min_rank", "between"))
        self.assertFalse(registry.has_field("tuition_yuan_per_year"))
        self.assertIn("tuition_yuan_per_year", registry.unsupported_field_ids())
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_semantic_capability_graph.SemanticMappingTest
```

Expected: FAIL because mapping modules and config path do not exist.

- [ ] **Step 3: 创建语义候选生成器**

Create `src/semantic/semantic_candidates.py`:

```python
"""字段语义候选生成器。

候选生成器可以使用规则或 LLM，但输出永远不是可执行 schema。
"""

from __future__ import annotations

from typing import Any, Protocol

from src.semantic.capability_graph import DatasetCapabilityGraph


class LLMSemanticCandidateProvider(Protocol):
    """LLM 字段语义候选提供者接口。"""

    def propose(self, headers: list[str], samples: dict[str, list[str]]) -> list[dict[str, Any]]:
        """返回候选字段语义，不返回可执行规则。"""


RULE_BASED_HEADER_MAP = {
    "专业": "major_name",
    "专业名称": "major_name",
    "最低位次": "major_min_rank",
    "最低位次1": "major_min_rank",
    "最低分数": "major_min_score",
    "最低分1": "major_min_score",
    "学校所在": "school_province",
    "所在省": "school_province",
    "院校名称": "university_name",
    "所属专业组": "group_code",
    "院校专业组代码": "group_code",
    "选科要求": "subject_requirement",
    "科类": "subject_type",
    "年份": "year",
    "录取人数": "plan_count",
    "是否985": "school_is_985",
    "是否211": "school_is_211",
    "学校性质": "school_ownership",
    "专业备注": "major_notes",
}


class RuleBasedSemanticCandidateGenerator:
    """基于已审查表头词典生成语义候选。"""

    def generate(self, graph: DatasetCapabilityGraph) -> list[dict[str, Any]]:
        candidates = []
        for source_column, field in graph.fields.items():
            field_id = RULE_BASED_HEADER_MAP.get(source_column)
            if not field_id:
                continue
            candidates.append(
                {
                    "source_column": source_column,
                    "canonical_field_id": field_id,
                    "confidence": "rule_exact_header",
                    "inferred_type": field.inferred_type,
                    "candidate_ops": field.candidate_ops,
                    "reason": f"表头 `{source_column}` 命中 reviewed header map。",
                }
            )
        return candidates
```

- [ ] **Step 4: 创建 reviewed mapping 配置**

Create `domains/admissions/semantic_capabilities.json`:

```json
{
  "status": "approved",
  "version": "1",
  "reviewed_mappings": {
    "year": {
      "source_columns": ["年份"],
      "type": "number",
      "allowed_ops": ["eq", "in", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "subject_type": {
      "source_columns": ["科类"],
      "type": "string",
      "allowed_ops": ["contains", "eq", "in"],
      "required_for": ["admissions_major_rank"]
    },
    "subject_requirement": {
      "source_columns": ["选科要求"],
      "type": "string",
      "allowed_ops": ["satisfies_subject_requirement", "contains"],
      "required_for": ["admissions_major_rank"]
    },
    "university_name": {
      "source_columns": ["院校名称"],
      "type": "string",
      "allowed_ops": ["contains", "eq", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "group_code": {
      "source_columns": ["院校专业组代码", "所属专业组"],
      "type": "string",
      "allowed_ops": ["eq", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "major_name": {
      "source_columns": ["专业名称", "专业"],
      "type": "string",
      "allowed_ops": ["contains", "contains_any", "eq", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "major_code": {
      "source_columns": ["专业代码"],
      "type": "string",
      "allowed_ops": ["eq", "sort"],
      "required_for": []
    },
    "major_notes": {
      "source_columns": ["专业备注"],
      "type": "long_text",
      "allowed_ops": ["contains"],
      "required_for": ["admissions_major_rank"]
    },
    "major_min_rank": {
      "source_columns": ["最低位次", "最低位次1"],
      "type": "number",
      "allowed_ops": ["eq", "<=", ">=", "between", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "major_min_score": {
      "source_columns": ["最低分数", "最低分1"],
      "type": "number",
      "allowed_ops": ["eq", "<=", ">=", "between", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "school_province": {
      "source_columns": ["学校所在", "所在省"],
      "type": "string",
      "allowed_ops": ["eq", "in", "sort"],
      "required_for": ["admissions_major_rank"]
    },
    "school_ownership": {
      "source_columns": ["学校性质", "公私性质"],
      "type": "enum_or_category",
      "allowed_ops": ["eq", "in", "not_in", "sort"],
      "required_for": []
    },
    "school_is_985": {
      "source_columns": ["是否985"],
      "type": "enum_or_category",
      "allowed_ops": ["eq", "in", "sort"],
      "required_for": []
    },
    "school_is_211": {
      "source_columns": ["是否211"],
      "type": "enum_or_category",
      "allowed_ops": ["eq", "in", "sort"],
      "required_for": []
    },
    "plan_count": {
      "source_columns": ["计划人数", "录取人数"],
      "type": "number",
      "allowed_ops": ["eq", "<=", ">=", "between", "sort"],
      "required_for": []
    },
    "tuition_yuan_per_year": {
      "source_columns": ["学费"],
      "type": "number_from_string",
      "allowed_ops": ["<=", ">=", "between"],
      "required_for": [],
      "unsupported_reason": "当前源表没有学费字段时，不能执行费用筛选。"
    },
    "city": {
      "source_columns": ["城市"],
      "type": "string",
      "allowed_ops": ["contains", "in_contains"],
      "required_for": [],
      "unsupported_reason": "当前源表没有城市字段时，不能执行城市筛选；学校所在省份不能替代城市。"
    },
    "group_min_rank": {
      "source_columns": ["专业组最低位次1"],
      "type": "number",
      "allowed_ops": ["between", "<=", ">=", "sort"],
      "required_for": [],
      "unsupported_reason": "当前源表没有专业组最低位次字段时，不能声称按专业组最低位次推荐。"
    }
  },
  "query_recipes": {
    "admissions_major_rank": {
      "description": "按专业最低位次生成冲稳保。",
      "required_field_ids": [
        "year",
        "subject_type",
        "subject_requirement",
        "university_name",
        "group_code",
        "major_name",
        "major_min_rank",
        "major_min_score",
        "school_province"
      ],
      "optional_field_ids": [
        "major_code",
        "major_notes",
        "school_is_985",
        "school_is_211",
        "school_ownership",
        "plan_count"
      ]
    }
  },
  "special_limit_terms": [
    "中外合作",
    "合作办学",
    "军检",
    "公安专业",
    "教师专项",
    "地方专项",
    "免费",
    "只招男生",
    "定向"
  ]
}
```

- [ ] **Step 5: 注册 domain path**

Modify `domains/admissions/domain.json` under `"paths"` by adding:

```json
"semantic_capabilities": "semantic_capabilities.json"
```

The `"paths"` object must remain valid JSON with commas between every item.

Modify `src/domains/domain_config.py` by adding:

```python
    @property
    def semantic_capabilities_path(self) -> Path | None:
        paths = self.payload.get("paths") or {}
        if "semantic_capabilities" not in paths:
            return None
        return self.resolve_path(paths["semantic_capabilities"])

    @property
    def semantic_capabilities(self) -> dict[str, Any]:
        path = self.semantic_capabilities_path
        if not path or not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 6: 实现 reviewed mapping registry**

Create `src/semantic/reviewed_mapping.py`:

```python
"""已审核字段语义映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph


@dataclass(frozen=True)
class ReviewedFieldMapping:
    """已审核 canonical field 到源列的映射。"""

    field_id: str
    source_column: str
    field_type: str
    allowed_ops: list[str]
    required_for: list[str]
    unsupported_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "source_column": self.source_column,
            "type": self.field_type,
            "allowed_ops": self.allowed_ops,
            "required_for": self.required_for,
            "unsupported_reason": self.unsupported_reason,
        }


class ReviewedMappingRegistry:
    """只暴露当前数据集中真实存在且已审核的字段。"""

    def __init__(
        self,
        active_mappings: dict[str, ReviewedFieldMapping],
        configured_mappings: dict[str, dict[str, Any]],
    ) -> None:
        self.active_mappings = active_mappings
        self.configured_mappings = configured_mappings

    @classmethod
    def from_domain(
        cls,
        domain_config: DomainConfig,
        graph: DatasetCapabilityGraph,
    ) -> "ReviewedMappingRegistry":
        payload = domain_config.semantic_capabilities
        configured = payload.get("reviewed_mappings") or {}
        active = {}
        for field_id, spec in configured.items():
            source_column = _first_existing_column(
                spec.get("source_columns") or [],
                graph,
            )
            if not source_column:
                continue
            field = graph.fields[source_column]
            allowed_ops = [
                op
                for op in spec.get("allowed_ops") or []
                if op in field.candidate_ops or op == "satisfies_subject_requirement"
            ]
            if not allowed_ops:
                continue
            active[field_id] = ReviewedFieldMapping(
                field_id=field_id,
                source_column=source_column,
                field_type=str(spec.get("type") or field.inferred_type),
                allowed_ops=allowed_ops,
                required_for=[str(item) for item in spec.get("required_for") or []],
                unsupported_reason=spec.get("unsupported_reason"),
            )
        return cls(active, configured)

    def has_field(self, field_id: str) -> bool:
        return field_id in self.active_mappings

    def source_column(self, field_id: str) -> str:
        return self.active_mappings[field_id].source_column

    def source_column_or_none(self, field_id: str) -> str | None:
        mapping = self.active_mappings.get(field_id)
        return mapping.source_column if mapping else None

    def has_op(self, field_id: str, op: str) -> bool:
        mapping = self.active_mappings.get(field_id)
        return bool(mapping and op in mapping.allowed_ops)

    def unsupported_field_ids(self) -> list[str]:
        return sorted(
            field_id
            for field_id in self.configured_mappings
            if field_id not in self.active_mappings
        )

    def unsupported_reason(self, field_id: str) -> str:
        spec = self.configured_mappings.get(field_id) or {}
        return str(
            spec.get("unsupported_reason")
            or "当前数据缺少该已审核字段，不能执行对应查询。"
        )

    def active_field_dicts(self) -> list[dict[str, Any]]:
        return [
            mapping.to_dict()
            for mapping in self.active_mappings.values()
        ]


def _first_existing_column(
    source_columns: list[str],
    graph: DatasetCapabilityGraph,
) -> str | None:
    for column in source_columns:
        if column in graph.fields:
            return str(column)
    return None
```

- [ ] **Step 7: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_capability_graph
```

Expected: PASS.

- [ ] **Step 8: 验证 JSON**

Run:

```bash
.venv/bin/python -m json.tool domains/admissions/domain.json >/tmp/domain.json.check
.venv/bin/python -m json.tool domains/admissions/semantic_capabilities.json >/tmp/semantic_capabilities.json.check
```

Expected: both commands exit 0.

- [ ] **Step 9: 提交**

```bash
git add \
  src/semantic/semantic_candidates.py \
  src/semantic/reviewed_mapping.py \
  domains/admissions/domain.json \
  domains/admissions/semantic_capabilities.json \
  src/domains/domain_config.py \
  tests/test_semantic_capability_graph.py
git commit -m "feat: add reviewed semantic mappings"
```

---

### Task 4: 增加 FieldGrounder、OperationVerifier、AnswerabilityGate

**Files:**
- Create: `src/semantic/query_verifier.py`
- Modify: `tests/test_semantic_query_verifier.py`

- [ ] **Step 1: 写验证器失败测试**

Append to `tests/test_semantic_query_verifier.py`:

```python
from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.query_verifier import SemanticQueryVerifier
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from tests.semantic_test_utils import new_admissions_dataset


class SemanticQueryVerifierTest(unittest.TestCase):
    def test_verifier_accepts_reviewed_fields_and_ops(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(
            DomainConfig.load("admissions"),
            graph,
        )
        ast = QueryAST.from_candidate(
            {
                "intent": "table_filter",
                "select": ["university_name", "major_name", "major_min_rank"],
                "filters": [
                    {"field_id": "year", "op": "eq", "value": 2025},
                    {"field_id": "major_min_rank", "op": "between", "value": [9000, 18000]},
                ],
                "sort": [{"field_id": "major_min_rank", "direction": "asc"}],
                "limit": 20,
            }
        )

        result = SemanticQueryVerifier(registry, table_name="admissions").verify(ast)

        self.assertTrue(result.ok)
        self.assertEqual(result.plan.table_name, "admissions")
        self.assertEqual(result.plan.filters[0]["source_column"], "年份")
        self.assertEqual(result.plan.filters[1]["source_column"], "最低位次")
        self.assertEqual(result.issues, [])

    def test_verifier_rejects_unavailable_city_and_tuition(self) -> None:
        dataset = next(new_admissions_dataset())
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(
            DomainConfig.load("admissions"),
            graph,
        )
        ast = QueryAST.from_candidate(
            {
                "intent": "table_filter",
                "select": ["university_name", "major_name", "city", "tuition_yuan_per_year"],
                "filters": [
                    {"field_id": "city", "op": "contains", "value": "广州"},
                    {"field_id": "tuition_yuan_per_year", "op": "<=", "value": 20000},
                ],
                "sort": [],
                "limit": 20,
            }
        )

        result = SemanticQueryVerifier(registry, table_name="admissions").verify(ast)

        self.assertFalse(result.ok)
        self.assertEqual(
            [issue.code for issue in result.issues],
            ["missing_field", "missing_field", "missing_field", "missing_field"],
        )
        self.assertEqual(
            [item["field_id"] for item in result.unanswerable_intents],
            ["city", "tuition_yuan_per_year", "city", "tuition_yuan_per_year"],
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_query_verifier.SemanticQueryVerifierTest
```

Expected: FAIL because `SemanticQueryVerifier` does not exist.

- [ ] **Step 3: 实现查询验证器**

Create `src/semantic/query_verifier.py`:

```python
"""受控查询计划验证。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.semantic.query_ast import (
    QueryAST,
    QueryVerificationIssue,
    VerifiedQueryPlan,
)
from src.semantic.reviewed_mapping import ReviewedMappingRegistry


@dataclass(frozen=True)
class SemanticQueryVerificationResult:
    """查询计划验证结果。"""

    ok: bool
    plan: VerifiedQueryPlan
    issues: list[QueryVerificationIssue]
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]


class SemanticQueryVerifier:
    """验证 QueryAST 中的字段、操作和值。"""

    def __init__(
        self,
        registry: ReviewedMappingRegistry,
        *,
        table_name: str,
    ) -> None:
        self.registry = registry
        self.table_name = table_name

    def verify(self, ast: QueryAST) -> SemanticQueryVerificationResult:
        issues: list[QueryVerificationIssue] = []
        answerable: list[dict[str, Any]] = []
        unanswerable: list[dict[str, Any]] = []
        select_columns = []
        for field_id in ast.select:
            source_column = self.registry.source_column_or_none(field_id)
            if source_column is None:
                issue = _missing_field_issue(field_id, self.registry)
                issues.append(issue)
                unanswerable.append(_unanswerable(field_id, issue.message))
                continue
            select_columns.append({"field_id": field_id, "source_column": source_column})
            answerable.append({"field_id": field_id, "capability": "select"})

        verified_filters = []
        for item in ast.filters:
            source_column = self.registry.source_column_or_none(item.field_id)
            if source_column is None:
                issue = _missing_field_issue(item.field_id, self.registry)
                issues.append(issue)
                unanswerable.append(_unanswerable(item.field_id, issue.message))
                continue
            if not self.registry.has_op(item.field_id, item.op):
                issue = QueryVerificationIssue(
                    code="unsupported_op",
                    severity="error",
                    message=f"字段 `{item.field_id}` 不允许操作 `{item.op}`。",
                    field_id=item.field_id,
                )
                issues.append(issue)
                unanswerable.append(_unanswerable(item.field_id, issue.message))
                continue
            value_issue = _value_issue(item.field_id, item.op, item.value)
            if value_issue:
                issues.append(value_issue)
                unanswerable.append(_unanswerable(item.field_id, value_issue.message))
                continue
            verified_filters.append(
                {
                    "field_id": item.field_id,
                    "source_column": source_column,
                    "op": item.op,
                    "value": item.value,
                }
            )
            answerable.append({"field_id": item.field_id, "capability": "filter"})

        verified_sort = []
        for item in ast.sort:
            source_column = self.registry.source_column_or_none(item.field_id)
            if source_column is None:
                issue = _missing_field_issue(item.field_id, self.registry)
                issues.append(issue)
                unanswerable.append(_unanswerable(item.field_id, issue.message))
                continue
            if not self.registry.has_op(item.field_id, "sort"):
                issue = QueryVerificationIssue(
                    code="unsupported_sort",
                    severity="error",
                    message=f"字段 `{item.field_id}` 不允许排序。",
                    field_id=item.field_id,
                )
                issues.append(issue)
                unanswerable.append(_unanswerable(item.field_id, issue.message))
                continue
            verified_sort.append(
                {
                    "field_id": item.field_id,
                    "source_column": source_column,
                    "direction": item.direction,
                }
            )
            answerable.append({"field_id": item.field_id, "capability": "sort"})

        plan = VerifiedQueryPlan(
            intent=ast.intent,
            table_name=self.table_name,
            select_columns=select_columns,
            filters=verified_filters,
            sort=verified_sort,
            limit=ast.limit,
            answerable_intents=answerable,
            unanswerable_intents=unanswerable,
        )
        return SemanticQueryVerificationResult(
            ok=not any(issue.severity == "error" for issue in issues),
            plan=plan,
            issues=issues,
            answerable_intents=answerable,
            unanswerable_intents=unanswerable,
        )


def _missing_field_issue(
    field_id: str,
    registry: ReviewedMappingRegistry,
) -> QueryVerificationIssue:
    return QueryVerificationIssue(
        code="missing_field",
        severity="error",
        message=registry.unsupported_reason(field_id),
        field_id=field_id,
    )


def _value_issue(
    field_id: str,
    op: str,
    value: Any,
) -> QueryVerificationIssue | None:
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            return QueryVerificationIssue(
                code="invalid_between_value",
                severity="error",
                message="between 操作必须提供两个边界值。",
                field_id=field_id,
            )
    if op in {"in", "not_in", "contains_any"} and not isinstance(value, list):
        return QueryVerificationIssue(
            code="invalid_list_value",
            severity="error",
            message=f"{op} 操作必须提供数组值。",
            field_id=field_id,
        )
    return None


def _unanswerable(field_id: str, reason: str) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "answerable": False,
        "reason": reason,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_query_verifier
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add src/semantic/query_verifier.py tests/test_semantic_query_verifier.py
git commit -m "feat: verify semantic query plans"
```

---

### Task 5: 增加参数化 SQLBuilder

**Files:**
- Create: `src/semantic/sql_builder.py`
- Create: `tests/test_semantic_sql_builder.py`

- [ ] **Step 1: 写 SQLBuilder 失败测试**

Create `tests/test_semantic_sql_builder.py`:

```python
from __future__ import annotations

import unittest

from src.semantic.query_ast import VerifiedQueryPlan
from src.semantic.sql_builder import SemanticSQLBuilder


class SemanticSQLBuilderTest(unittest.TestCase):
    def test_builds_parameterized_sql(self) -> None:
        plan = VerifiedQueryPlan(
            intent="table_filter",
            table_name="admissions",
            select_columns=[
                {"field_id": "university_name", "source_column": "院校名称"},
                {"field_id": "major_name", "source_column": "专业"},
                {"field_id": "major_min_rank", "source_column": "最低位次"},
            ],
            filters=[
                {"field_id": "year", "source_column": "年份", "op": "eq", "value": 2025},
                {
                    "field_id": "major_min_rank",
                    "source_column": "最低位次",
                    "op": "between",
                    "value": [9000, 18000],
                },
            ],
            sort=[
                {
                    "field_id": "major_min_rank",
                    "source_column": "最低位次",
                    "direction": "asc",
                }
            ],
            limit=20,
            answerable_intents=[],
            unanswerable_intents=[],
        )

        built = SemanticSQLBuilder().build(plan)

        self.assertEqual(
            built.sql,
            'SELECT "院校名称" AS "university_name", "专业" AS "major_name", '
            '"最低位次" AS "major_min_rank" FROM "admissions" '
            'WHERE "年份" = ? AND "最低位次" BETWEEN ? AND ? '
            'ORDER BY "最低位次" ASC NULLS LAST LIMIT ?',
        )
        self.assertEqual(built.params, [2025, 9000, 18000, 20])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_sql_builder
```

Expected: FAIL because `SemanticSQLBuilder` does not exist.

- [ ] **Step 3: 实现 SQLBuilder**

Create `src/semantic/sql_builder.py`:

```python
"""从已验证 QueryPlan 构造参数化 DuckDB SQL。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.semantic.query_ast import VerifiedQueryPlan


@dataclass(frozen=True)
class BuiltSQL:
    """参数化 SQL 和参数。"""

    sql: str
    params: list[Any]


class SemanticSQLBuilder:
    """只接受 VerifiedQueryPlan，不接受用户原始 SQL。"""

    def build(self, plan: VerifiedQueryPlan) -> BuiltSQL:
        select_sql = ", ".join(
            f"{_quote(item['source_column'])} AS {_quote(item['field_id'])}"
            for item in plan.select_columns
        )
        if not select_sql:
            select_sql = "*"
        where_parts = []
        params: list[Any] = []
        for item in plan.filters:
            fragment, values = _filter_sql(item)
            where_parts.append(fragment)
            params.extend(values)
        sql = f"SELECT {select_sql} FROM {_quote(plan.table_name)}"
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        if plan.sort:
            sql += " ORDER BY " + ", ".join(
                f"{_quote(item['source_column'])} {item['direction'].upper()} NULLS LAST"
                for item in plan.sort
            )
        sql += " LIMIT ?"
        params.append(plan.limit)
        return BuiltSQL(sql=sql, params=params)


def _filter_sql(item: dict[str, Any]) -> tuple[str, list[Any]]:
    op = item["op"]
    column = _quote(item["source_column"])
    value = item.get("value")
    if op == "eq":
        return f"{column} = ?", [value]
    if op == "contains":
        return f"STRPOS(CAST({column} AS VARCHAR), ?) > 0", [value]
    if op == "between":
        lower, upper = value
        return f"{column} BETWEEN ? AND ?", [lower, upper]
    if op in {"<=", ">="}:
        return f"{column} {op} ?", [value]
    if op in {"in", "not_in"}:
        values = list(value)
        placeholders = ", ".join("?" for _ in values)
        operator = "IN" if op == "in" else "NOT IN"
        return f"{column} {operator} ({placeholders})", values
    raise ValueError(f"Unsupported verified SQL op: {op}")


def _quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_sql_builder
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add src/semantic/sql_builder.py tests/test_semantic_sql_builder.py
git commit -m "feat: build semantic query sql"
```

---

### Task 6: 实现 admissions 专业最低位次冲稳保 recipe

**Files:**
- Create: `src/semantic/admissions_major_rank.py`
- Create: `tests/test_semantic_admissions_major_rank.py`

- [ ] **Step 1: 写冲稳保失败测试**

Create `tests/test_semantic_admissions_major_rank.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from src.adapters.data_warehouse import build_structured_store_from_dataset
from src.domains import DomainConfig
from src.semantic.admissions_major_rank import AdmissionsMajorRankPlanner
from tests.semantic_test_utils import new_admissions_dataset


class AdmissionsMajorRankPlannerTest(unittest.TestCase):
    def test_major_rank_plan_returns_reach_match_safety(self) -> None:
        with TemporaryDirectory() as directory:
            dataset = next(new_admissions_dataset())
            database_path = Path(directory) / "admissions.duckdb"
            index_path = Path(directory) / "schema_value_index.json"
            build_structured_store_from_dataset(
                dataset=dataset,
                schema_path=DomainConfig.load("admissions").schema_path,
                database_path=database_path,
                index_path=index_path,
                table_name="admissions",
                source_path=dataset.workbook_path,
            )

            result = AdmissionsMajorRankPlanner(
                domain_config=DomainConfig.load("admissions"),
                database_path=database_path,
                table_name="admissions",
            ).run("广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.query_type, "admissions_major_rank")
        self.assertEqual([item["档位"] for item in result.rows], ["冲", "稳", "保"])
        self.assertEqual(result.rows[0]["院校名称"], "中山大学")
        self.assertEqual(result.rows[0]["专业"], "预防医学")
        self.assertEqual(result.rows[0]["最低录取排名"], 9850)
        self.assertEqual(result.rows[1]["院校名称"], "深圳大学")
        self.assertEqual(result.rows[1]["最低录取排名"], 10257)
        self.assertEqual(result.rows[2]["院校名称"], "暨南大学")
        self.assertEqual(result.rows[2]["最低录取排名"], 16212)
        self.assertNotIn("电子科技大学", [item["院校名称"] for item in result.rows])
        self.assertIn("city", [item["field_id"] for item in result.unanswerable_intents])
        self.assertIn("tuition_yuan_per_year", [item["field_id"] for item in result.unanswerable_intents])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_major_rank
```

Expected: FAIL because planner does not exist.

- [ ] **Step 3: 实现 admissions major-rank planner**

Create `src/semantic/admissions_major_rank.py`:

```python
"""admissions 专业最低位次冲稳保 recipe。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from src.adapters.data_warehouse import load_structured_dataset
from src.domains import DomainConfig
from src.semantic.capability_graph import DatasetCapabilityGraph
from src.semantic.query_ast import QueryAST
from src.semantic.query_verifier import SemanticQueryVerifier
from src.semantic.reviewed_mapping import ReviewedMappingRegistry
from src.semantic.sql_builder import SemanticSQLBuilder


@dataclass(frozen=True)
class AdmissionsMajorRankResult:
    """admissions major-rank planned query result."""

    query_type: str
    status: str
    rows: list[dict[str, Any]]
    answerable_intents: list[dict[str, Any]]
    unanswerable_intents: list[dict[str, Any]]
    execution_summary: dict[str, Any]
    warnings: list[dict[str, Any]] = field(default_factory=list)


class AdmissionsMajorRankPlanner:
    """按专业最低位次执行冲稳保。"""

    def __init__(
        self,
        *,
        domain_config: DomainConfig,
        database_path: str | Path,
        table_name: str,
    ) -> None:
        self.domain_config = domain_config
        self.database_path = Path(database_path)
        self.table_name = table_name

    def run(self, user_request: str) -> AdmissionsMajorRankResult | None:
        if "冲稳保" not in user_request and "最低录取排名" not in user_request:
            return None
        rank = _parse_rank(user_request)
        if rank is None:
            return AdmissionsMajorRankResult(
                query_type="admissions_major_rank",
                status="needs_confirmation",
                rows=[],
                answerable_intents=[],
                unanswerable_intents=[
                    {
                        "field_id": "user_rank",
                        "answerable": False,
                        "reason": "缺少广东省排位，不能生成冲稳保。",
                    }
                ],
                execution_summary=_empty_execution_summary(),
                warnings=[
                    {
                        "code": "missing_rank",
                        "severity": "error",
                        "message": "缺少广东省排位。",
                    }
                ],
            )
        dataset = load_structured_dataset(
            self.database_path,
            required_columns=[],
            table_name=self.table_name,
        )
        graph = DatasetCapabilityGraph.from_dataset(dataset)
        registry = ReviewedMappingRegistry.from_domain(self.domain_config, graph)
        missing_recipe_fields = _missing_recipe_fields(self.domain_config, registry)
        if missing_recipe_fields:
            return AdmissionsMajorRankResult(
                query_type="admissions_major_rank",
                status="blocked",
                rows=[],
                answerable_intents=[],
                unanswerable_intents=[
                    {
                        "field_id": field_id,
                        "answerable": False,
                        "reason": registry.unsupported_reason(field_id),
                    }
                    for field_id in missing_recipe_fields
                ],
                execution_summary=_empty_execution_summary(),
                warnings=[
                    {
                        "code": "missing_recipe_fields",
                        "severity": "error",
                        "message": "当前数据缺少 admissions_major_rank 必需字段。",
                        "missing_fields": missing_recipe_fields,
                    }
                ],
            )
        ast = _query_ast(rank)
        verification = SemanticQueryVerifier(
            registry,
            table_name=self.table_name,
        ).verify(ast)
        if not verification.ok:
            return AdmissionsMajorRankResult(
                query_type="admissions_major_rank",
                status="blocked",
                rows=[],
                answerable_intents=verification.answerable_intents,
                unanswerable_intents=verification.unanswerable_intents,
                execution_summary={
                    **_empty_execution_summary(),
                    "verification_issues": [
                        issue.to_dict() for issue in verification.issues
                    ],
                },
                warnings=[
                    {
                        "code": "query_plan_not_verified",
                        "severity": "error",
                        "message": "候选 QueryAST 未通过字段或操作校验。",
                    }
                ],
            )
        built = SemanticSQLBuilder().build(verification.plan)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            raw_rows = connection.execute(built.sql, built.params).fetchdf().to_dict("records")
        rows = _bucket_rows(raw_rows, rank, self.domain_config.semantic_capabilities)
        status = "ok" if rows else "no_results"
        return AdmissionsMajorRankResult(
            query_type="admissions_major_rank",
            status=status,
            rows=rows,
            answerable_intents=[
                *verification.answerable_intents,
                {
                    "intent": "risk_buckets",
                    "answerable": True,
                    "basis": "专业最低位次",
                },
            ],
            unanswerable_intents=[
                {
                    "field_id": "city",
                    "answerable": False,
                    "reason": registry.unsupported_reason("city"),
                },
                {
                    "field_id": "tuition_yuan_per_year",
                    "answerable": False,
                    "reason": registry.unsupported_reason("tuition_yuan_per_year"),
                },
                {
                    "field_id": "group_min_rank",
                    "answerable": False,
                    "reason": registry.unsupported_reason("group_min_rank"),
                },
            ],
            execution_summary={
                "executor": "duckdb",
                "query_type": "admissions_major_rank",
                "sql": built.sql,
                "params": built.params,
                "input_row_count": len(raw_rows),
                "filtered_row_count": len(rows),
                "rank": rank,
                "basis": "major_min_rank",
                "verified_query_plan": verification.plan,
            },
        )


def _query_ast(rank: int) -> QueryAST:
    return QueryAST.from_candidate(
        {
            "intent": "admissions_major_rank",
            "select": [
                "year",
                "university_name",
                "group_code",
                "major_name",
                "major_code",
                "major_notes",
                "subject_type",
                "subject_requirement",
                "major_min_score",
                "major_min_rank",
                "school_province",
                "school_is_985",
                "school_is_211",
                "plan_count",
            ],
            "filters": [
                {"field_id": "year", "op": "eq", "value": 2025},
                {"field_id": "subject_type", "op": "contains", "value": "物理"},
                {"field_id": "major_min_rank", "op": "between", "value": [rank - 1500, rank + 9000]},
            ],
            "sort": [{"field_id": "major_min_rank", "direction": "asc"}],
            "limit": 100,
            "requested_output": ["risk_buckets", "major_min_rank"],
        }
    )


def _bucket_rows(
    raw_rows: list[dict[str, Any]],
    rank: int,
    capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    special_terms = capabilities.get("special_limit_terms") or []
    normal_rows = [
        row for row in raw_rows if not _has_special_limit(row, special_terms)
    ]
    buckets = [
        ("冲", lambda value: rank - 1500 <= value < rank),
        ("稳", lambda value: rank <= value <= rank + 3000),
        ("保", lambda value: rank + 3000 < value <= rank + 9000),
    ]
    output = []
    for label, predicate in buckets:
        candidates = [
            row for row in normal_rows
            if predicate(int(row["major_min_rank"]))
        ]
        if not candidates:
            continue
        selected = sorted(
            candidates,
            key=lambda row: abs(int(row["major_min_rank"]) - rank),
        )[0]
        output.append(_project_row(label, selected, rank))
    return output


def _project_row(label: str, row: dict[str, Any], rank: int) -> dict[str, Any]:
    min_rank = int(row["major_min_rank"])
    return {
        "档位": label,
        "院校名称": row.get("university_name"),
        "专业组": row.get("group_code"),
        "专业": row.get("major_name"),
        "专业代码": row.get("major_code"),
        "最低分": _int_or_none(row.get("major_min_score")),
        "最低录取排名": min_rank,
        "相对用户排名": min_rank - rank,
        "学校所在": row.get("school_province"),
        "是否985": row.get("school_is_985"),
        "是否211": row.get("school_is_211"),
        "录取人数": _int_or_none(row.get("plan_count")),
    }


def _has_special_limit(row: dict[str, Any], terms: list[str]) -> bool:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ["major_notes", "university_name", "major_name"]
    )
    return any(term in haystack for term in terms)


def _missing_recipe_fields(
    domain_config: DomainConfig,
    registry: ReviewedMappingRegistry,
) -> list[str]:
    recipe = (
        domain_config.semantic_capabilities.get("query_recipes") or {}
    ).get("admissions_major_rank") or {}
    required = recipe.get("required_field_ids") or []
    return [field_id for field_id in required if not registry.has_field(field_id)]


def _parse_rank(text: str) -> int | None:
    match = re.search(r"(\d{1,6})\s*(?:名|位次|排名)", text)
    return int(match.group(1)) if match else None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _empty_execution_summary() -> dict[str, Any]:
    return {
        "executor": None,
        "query_type": "admissions_major_rank",
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_semantic_admissions_major_rank
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add src/semantic/admissions_major_rank.py tests/test_semantic_admissions_major_rank.py
git commit -m "feat: plan admissions by major rank"
```

---

### Task 7: 接入 DatasetService 和 Workbench planned query

**Files:**
- Modify: `src/api/dataset_service.py`
- Modify: `src/api/workbench.py`
- Modify: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 写 uploaded dataset 端到端失败测试**

Append to `tests/test_uploaded_dataset_flow.py`:

```python
from tests.semantic_test_utils import write_new_admissions_excel


class UploadedSemanticAdmissionsFlowTest(unittest.TestCase):
    def test_uploaded_new_admissions_major_rank_query(self) -> None:
        query = "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"
        with TemporaryDirectory() as directory:
            source = write_new_admissions_excel(Path(directory) / "new_admissions.xlsx")
            service = DatasetService(Path(directory) / "managed")
            service.upload(
                filename=source.name,
                content=source.read_bytes(),
                dataset_id="ds_new_admissions",
            )
            service.generate_domain_pack(
                "ds_new_admissions",
                domain_name="admissions",
                base_domain="admissions",
            )
            approved = service.approve_domain("ds_new_admissions")
            self.assertTrue(approved["ok"])
            built = service.build_warehouse("ds_new_admissions")
            self.assertEqual(built["status"], "queryable")

            response = service.query(
                "ds_new_admissions",
                user_input=query,
                soft_preferences={"prompt": query},
            )

        assert_workbench_contract(self, response)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["query_type"], "admissions_major_rank")
        self.assertEqual(
            [item["raw"]["档位"] for item in response["items"]],
            ["冲", "稳", "保"],
        )
        self.assertEqual(response["items"][0]["raw"]["最低录取排名"], 9850)
        self.assertIn(
            "group_min_rank",
            [
                item["field_id"]
                for item in response["evidence_pack"]["unanswerable_intents"]
            ],
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: FAIL because Workbench still returns old admissions planner response or error.

- [ ] **Step 3: 增加 Workbench semantic path**

Modify `src/api/workbench.py` imports:

```python
from src.semantic.admissions_major_rank import AdmissionsMajorRankPlanner
```

In `_run_workbench`, after `warehouse_audit` passes and before `_run_admissions_planned_query`, add:

```python
    semantic_result = _run_semantic_capability_query(config, domain_config)
    if semantic_result is not None:
        return _semantic_capability_payload(
            config=config,
            domain_config=domain_config,
            warehouse_audit=warehouse_audit,
            semantic_result=semantic_result,
        )
```

Add helper functions near `_run_admissions_planned_query`:

```python
def _run_semantic_capability_query(
    config: WorkbenchConfig,
    domain_config: DomainConfig,
) -> Any | None:
    if domain_config.domain_id != "admissions":
        return None
    if not domain_config.semantic_capabilities:
        return None
    return AdmissionsMajorRankPlanner(
        domain_config=domain_config,
        database_path=_warehouse_database_path(domain_config),
        table_name=domain_config.table_name,
    ).run(_compose_user_request(config))


def _semantic_capability_payload(
    *,
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    warehouse_audit: dict[str, Any],
    semantic_result: Any,
) -> dict[str, Any]:
    evidence_pack = _semantic_evidence_pack(
        config=config,
        domain_config=domain_config,
        warehouse_audit=warehouse_audit,
        semantic_result=semantic_result,
    )
    items = _semantic_items(semantic_result.rows)
    top_results = [item["raw"] for item in items]
    answer = _semantic_answer(semantic_result)
    response = WorkbenchResponse(
        schema_version=WORKBENCH_SCHEMA_VERSION,
        domain=domain_config.domain_id,
        domain_version=domain_config.domain_version,
        domain_pack_status=domain_config.pack_status,
        status=semantic_result.status,
        query_type=semantic_result.query_type,
        query={"user_input": _compose_user_request(config)},
        answer=answer,
        items=items,
        top_results=top_results,
        result_sections={"risk_buckets": semantic_result.rows},
        result_count=len(semantic_result.rows),
        executed_filters=[],
        candidates_to_confirm=[],
        confirmed_rules=[],
        unconfirmed_candidates=[],
        unexecuted_preferences=[],
        no_schema_field_preferences=[],
        rejected_confirmations=[],
        warnings=semantic_result.warnings,
        evidence_pack=evidence_pack,
        debug_trace={
            "execution": semantic_result.execution_summary,
            "data_warehouse": warehouse_audit,
        },
    )
    return response.to_dict()
```

Add supporting helpers:

```python
def _semantic_evidence_pack(
    *,
    config: WorkbenchConfig,
    domain_config: DomainConfig,
    warehouse_audit: dict[str, Any],
    semantic_result: Any,
) -> dict[str, Any]:
    return {
        "user_request": _compose_user_request(config),
        "executed_rules": [],
        "candidate_confirmations": [],
        "not_executed_preferences": [],
        "result_count": len(semantic_result.rows),
        "top_k_results": semantic_result.rows[:EVIDENCE_TOP_K],
        "trace_summary": {"mode": "semantic_capability"},
        "execution_summary": semantic_result.execution_summary,
        "answerable_intents": semantic_result.answerable_intents,
        "unanswerable_intents": semantic_result.unanswerable_intents,
        "verified_query_plan": _json_ready(
            semantic_result.execution_summary.get("verified_query_plan")
        ),
        "capability_graph_summary": {
            "domain": domain_config.domain_id,
            "warehouse": warehouse_audit.get("duckdb", {}),
        },
    }


def _semantic_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for index, row in enumerate(rows, start=1):
        items.append(
            {
                "item_id": f"semantic_{index}",
                "title": f"{row.get('档位')}：{row.get('院校名称')} - {row.get('专业')}",
                "subtitle": f"最低录取排名：{row.get('最低录取排名')}",
                "primary_attributes": [
                    {"label": "专业组", "value": row.get("专业组")},
                    {"label": "最低分", "value": row.get("最低分")},
                    {"label": "最低录取排名", "value": row.get("最低录取排名")},
                ],
                "secondary_attributes": [
                    {"label": "学校所在", "value": row.get("学校所在")},
                    {"label": "985/211", "value": f"{row.get('是否985')}/{row.get('是否211')}"},
                    {"label": "相对用户排名", "value": row.get("相对用户排名")},
                ],
                "matched_filters": [],
                "raw": row,
            }
        )
    return items


def _semantic_answer(semantic_result: Any) -> str:
    if semantic_result.status == "blocked":
        return "当前数据缺少该查询所需的已审核字段，未执行 SQL。"
    if semantic_result.status == "needs_confirmation":
        return "请先补充广东省排位后再生成冲稳保。"
    lines = [
        "本次按 2025 年物理类、物化生可满足选科要求、专业最低录取排名生成冲稳保。",
        "未使用学费、城市或专业组最低位次，因为当前数据未提供这些已审核字段。",
    ]
    for row in semantic_result.rows:
        lines.append(
            f"{row['档位']}：{row['院校名称']} {row['专业组']} {row['专业']}，"
            f"最低录取排名 {row['最低录取排名']}。"
        )
    return "\n".join(lines)
```

If `_json_ready` is not available near this helper, reuse the existing local helper in `src/api/workbench.py`; if no helper exists, add:

```python
def _json_ready(value: Any) -> Any:
    if hasattr(value, "__dict__"):
        return {
            key: _json_ready(item)
            for key, item in value.__dict__.items()
        }
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value
```

- [ ] **Step 4: 确保 DatasetService profile 暴露 capability summary**

Modify `src/api/dataset_service.py` imports:

```python
from src.semantic.capability_graph import DatasetCapabilityGraph
```

In `profile`, after loading `profile`, build capability summary from source dataset:

```python
        dataset = load_source_dataset(
            metadata["source_path"],
            sheet_name=metadata.get("sheet_name"),
        )
        capability_graph = DatasetCapabilityGraph.from_dataset(dataset).to_dict()
```

Add to the returned dict:

```python
            "capability_graph": capability_graph,
```

- [ ] **Step 5: 运行端到端测试确认通过**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 6: 回归旧 uploaded dataset 流程**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow
```

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add src/api/workbench.py src/api/dataset_service.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: run capability-aware admissions query"
```

---

### Task 8: 扩展 EvidencePack 和 API contract 测试

**Files:**
- Modify: `src/reporting/evidence_pack.py`
- Modify: `tests/test_workbench_api_contract.py`
- Modify: `tests/workbench_contract_utils.py`

- [ ] **Step 1: 写 EvidencePack 字段测试**

Append to `tests/test_workbench_api_contract.py`:

```python
    def test_evidence_pack_contains_answerability_fields(self) -> None:
        response = run_workbench(WorkbenchConfig(user_input="广东物理，位次9000，想读计算机，请推荐"))

        assert_workbench_contract(self, response)
        evidence = response["evidence_pack"]
        self.assertIn("answerable_intents", evidence)
        self.assertIn("unanswerable_intents", evidence)
        self.assertIn("verified_query_plan", evidence)
        self.assertIn("capability_graph_summary", evidence)
```

If `tests/test_workbench_api_contract.py` does not import `run_workbench` and `WorkbenchConfig`, add:

```python
from src.api.workbench import WorkbenchConfig, run_workbench
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract
```

Expected: FAIL because legacy EvidencePack lacks answerability fields.

- [ ] **Step 3: 增加 EvidencePack 字段**

Modify `src/reporting/evidence_pack.py` dataclass by adding fields:

```python
    answerable_intents: list[dict[str, Any]] = field(default_factory=list)
    unanswerable_intents: list[dict[str, Any]] = field(default_factory=list)
    verified_query_plan: dict[str, Any] = field(default_factory=dict)
    capability_graph_summary: dict[str, Any] = field(default_factory=dict)
```

In `from_verified_pipeline`, set conservative defaults:

```python
            answerable_intents=[
                {"intent": "verified_rules", "answerable": True}
                if compact_rules else {"intent": "verified_rules", "answerable": False}
            ],
            unanswerable_intents=[],
            verified_query_plan={},
            capability_graph_summary={},
```

Place these arguments in the returned `cls(...)` call after `decision_guidance=guidance`.

- [ ] **Step 4: 更新 contract helper**

Modify `tests/workbench_contract_utils.py` by adding:

```python
EVIDENCE_PACK_KEYS = {
    "answerable_intents",
    "unanswerable_intents",
    "verified_query_plan",
    "capability_graph_summary",
}
```

Inside `assert_workbench_contract`, after checking `payload["evidence_pack"]` is a dict, add:

```python
    testcase.assertTrue(EVIDENCE_PACK_KEYS <= set(payload["evidence_pack"]))
```

- [ ] **Step 5: 运行 contract 测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_workbench_api_contract
```

Expected: PASS.

- [ ] **Step 6: 运行语义相关测试**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_semantic_capability_graph \
  tests.test_semantic_query_verifier \
  tests.test_semantic_sql_builder \
  tests.test_semantic_admissions_major_rank \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest
```

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add src/reporting/evidence_pack.py tests/test_workbench_api_contract.py tests/workbench_contract_utils.py
git commit -m "feat: record answerability evidence"
```

---

### Task 9: 文档和人工验收脚本

**Files:**
- Create: `scripts/run_semantic_capability_probe.py`
- Modify: `docs/api_contract.md`
- Modify: `docs/methodology_report.md`
- Modify: `README.md`

- [ ] **Step 1: 创建人工 probe 脚本**

Create `scripts/run_semantic_capability_probe.py`:

```python
"""Run a semantic capability probe for an uploaded admissions workbook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.api.dataset_service import DatasetService


DEFAULT_QUERY = "广东物化生，10000名，列出冲稳保的次序，以及每个专业的最低录取排名"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", help="Excel/CSV source path.")
    parser.add_argument("--dataset-id", default="ds_semantic_probe")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--root", default="outputs/uploaded_datasets")
    args = parser.parse_args()

    source = Path(args.workbook)
    service = DatasetService(args.root)
    upload = service.upload(
        filename=source.name,
        content=source.read_bytes(),
        dataset_id=args.dataset_id,
    )
    service.generate_domain_pack(
        args.dataset_id,
        domain_name="admissions",
        base_domain="admissions",
    )
    approved = service.approve_domain(args.dataset_id)
    if not approved["ok"]:
        print(json.dumps({"upload": upload, "approve": approved}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    build = service.build_warehouse(args.dataset_id)
    response = service.query(
        args.dataset_id,
        user_input=args.query,
        soft_preferences={"prompt": args.query},
    )
    print(
        json.dumps(
            {
                "upload": upload,
                "build": build,
                "status": response["status"],
                "query_type": response["query_type"],
                "answer": response["answer"],
                "top_results": response["top_results"],
                "evidence_pack": {
                    "answerable_intents": response["evidence_pack"].get("answerable_intents", []),
                    "unanswerable_intents": response["evidence_pack"].get("unanswerable_intents", []),
                    "execution_summary": response["evidence_pack"].get("execution_summary", {}),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 更新 README**

In `README.md`, add a short section after the uploaded Excel/CSV workflow:

```markdown
### 语义能力查询

上传表格后，系统会先生成 `capability_graph`，说明当前数据能支持哪些字段、操作和 query type。自然语言只会生成候选 `QueryAST`；只有已审核字段、已审核操作和值校验全部通过后，系统才会生成参数化 SQL。

对新版招生专业录取分表，如果源表只有 `专业`、`最低位次`、`最低分数`、`学校所在` 等字段，系统可以按专业最低录取排名生成冲稳保，但会明确说明没有执行学费、城市和专业组最低位次筛选。

人工 probe：

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py path/to/admissions.xlsx
```
```

- [ ] **Step 3: 更新 API contract 文档**

In `docs/api_contract.md`, add an EvidencePack subsection:

```markdown
## EvidencePack 语义能力字段

`evidence_pack.answerable_intents` 记录本次回答已经由 verified query 或 verified rules 支持的意图。`evidence_pack.unanswerable_intents` 记录当前数据缺字段、缺审核映射或操作不合法而不能回答的意图。`evidence_pack.verified_query_plan` 只保存通过 verifier 的计划，不保存用户 raw SQL。

自然语言 SQL 查询必须走：

```text
NL -> candidate QueryAST -> FieldGrounder -> OperationVerifier -> AnswerabilityGate -> parameterized SQL
```

API 不接受也不执行用户提交的 raw SQL。
```

- [ ] **Step 4: 更新 methodology 文档**

In `docs/methodology_report.md`, add:

```markdown
## LLM 辅助语义能力边界

本项目允许 LLM 参与自然语言意图抽取和字段语义候选生成，但 LLM 输出只是候选结构。字段是否存在、语义是否已审核、操作是否合法、值是否可解析、SQL 是否可执行，都由 deterministic verifier 控制。

工程边界是：

```text
LLM proposes.
System verifies.
SQL executes.
EvidencePack constrains answer.
```

当上传数据缺少 `学费`、`城市` 或 `专业组最低位次` 等字段时，系统必须把对应偏好写入 `unanswerable_intents`，不能在答案中暗示这些筛选已经执行。
```

- [ ] **Step 5: 运行文档和 probe 测试**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_semantic_capability_graph \
  tests.test_semantic_query_verifier \
  tests.test_semantic_sql_builder \
  tests.test_semantic_admissions_major_rank \
  tests.test_uploaded_dataset_flow.UploadedSemanticAdmissionsFlowTest \
  tests.test_workbench_api_contract
git diff --check
```

Expected: all tests PASS and `git diff --check` exits 0.

- [ ] **Step 6: 用真实新 Excel 做人工验收**

Run with the local, untracked source file:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py "22-25年全国高校在广东的专业录取分数.xlsx" --dataset-id ds_semantic_probe_latest
```

Expected:

- `status` is `ok`.
- `query_type` is `admissions_major_rank`.
- `answer` states it used `2025`、`物理类`、物化生可满足 `选科要求`、`最低位次` as 专业最低录取排名.
- `top_results` include `冲`、`稳`、`保` rows.
- `evidence_pack.unanswerable_intents` includes `city`、`tuition_yuan_per_year`、`group_min_rank`.
- The output does not claim that city, tuition, or group minimum rank filters executed.

- [ ] **Step 7: 提交**

```bash
git add \
  scripts/run_semantic_capability_probe.py \
  README.md \
  docs/api_contract.md \
  docs/methodology_report.md
git commit -m "docs: document semantic capability workflow"
```

---

## 最终验证

Run:

```bash
.venv/bin/python -m unittest discover -s tests
git diff --check
```

Expected: all tests PASS and no whitespace errors.

Then run the manual probe against the local new Excel if the file is present:

```bash
.venv/bin/python scripts/run_semantic_capability_probe.py "22-25年全国高校在广东的专业录取分数.xlsx" --dataset-id ds_semantic_probe_latest
```

Expected: generated answer and `top_results` reproduce the same factual basis used in the Codex manual analysis:

- `2025`
- `科类=物理类`
- 物化生 satisfies `选科要求`
- `最低位次` used as 专业最低录取排名
- 冲稳保 output
- no use of 学费、城市、专业组最低位次
- special limitation rows excluded from ordinary recommendation rows

## 自检

- Spec coverage: 本计划覆盖用户提出的 LLM 候选语义、reviewed mapping、capability graph、QueryAST、verifier、SQLBuilder、EvidencePack、answerability、真实提示词验收。
- 外部研究应用: 计划明确采用 DuckDB 参数化执行和 Pydantic 结构化校验；SQLGlot、Frictionless、semantic layer 系统和 text-to-SQL 论文只作为 phase 1 设计参考。
- Placeholder scan: 本计划没有占位任务、空任务或未说明测试命令的步骤。
- Type consistency: Pydantic `QueryAST` / `VerifiedQueryPlan`、`DatasetCapabilityGraph`、`ReviewedMappingRegistry`、`SemanticQueryVerifier`、`SemanticSQLBuilder`、`AdmissionsMajorRankPlanner` 在各任务中的名称一致。
