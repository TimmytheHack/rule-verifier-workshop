# Real Dataset Pilot 报告

- status：`pass`
- source_path：`outputs/real_dataset_pilot/fixtures/real_like_admissions_pilot.xlsx`
- dataset_id：`ds_real_pilot_real_like_admissions_pil`
- source_fingerprint：`e371c6c65607bb49079016bfe386e705be90b1bf867a2e72ddd6b6c0109d6a15`
- sheet_name：`招生数据`
- row_count / column_count：`6` / `25`
- detected_header_row：`3`
- warehouse_path：`uploaded_datasets/ds_real_pilot_real_like_admissions_pil/domain_packs/admissions/warehouse/admissions.duckdb`
- warehouse_fingerprint：`e371c6c65607bb49079016bfe386e705be90b1bf867a2e72ddd6b6c0109d6a15`

## Schema Profile Summary
```json
{
  "row_count": 6,
  "column_count": 25,
  "sheet_summaries": [
    {
      "sheet_name": "说明",
      "row_count": 1,
      "column_count": 1,
      "non_empty_cells": 0,
      "selected": false
    },
    {
      "sheet_name": "招生数据",
      "row_count": 9,
      "column_count": 26,
      "non_empty_cells": 178,
      "selected": true
    }
  ],
  "detected_header_row": 3,
  "header_detection_status": "confirmed",
  "inferred_type_distribution": {
    "number": 14,
    "enum": 10,
    "number_from_string": 1
  },
  "warnings": [
    {
      "code": "upload_received",
      "severity": "info",
      "message": "文件已保存到托管数据目录。",
      "size_bytes": 6557,
      "extension": ".xlsx"
    },
    {
      "code": "merged_cells_detected",
      "severity": "warning",
      "message": "检测到合并单元格，请确认表头和数据未被合并结构影响。",
      "ranges": [
        "A1:C1"
      ]
    },
    {
      "code": "hidden_rows_or_columns_detected",
      "severity": "warning",
      "message": "检测到隐藏行或隐藏列，ingestion 会按文件内容读取。",
      "hidden_rows": [
        2
      ],
      "hidden_columns": []
    },
    {
      "code": "formula_cells_detected",
      "severity": "warning",
      "message": "检测到公式单元格；读取值可能依赖 Excel 缓存，请人工核验。",
      "cells": [
        "Z4"
      ]
    }
  ]
}
```
## Risky Fields
```json
[]
```
## Approved / Blocked Fields
```json
{
  "approved_fields": [
    "batch",
    "city",
    "full_major_name",
    "group_code",
    "group_min_rank_2024",
    "group_min_score_2024",
    "group_name",
    "group_plan_count",
    "major_code",
    "major_max_score_2024",
    "major_min_rank_2024",
    "major_min_score_2024",
    "major_name",
    "plan_count",
    "row_id",
    "school_province",
    "school_rank",
    "school_tags",
    "source_province",
    "subject_requirement",
    "subject_type",
    "tuition_yuan_per_year",
    "university_code",
    "university_name",
    "year"
  ],
  "blocked_fields": [],
  "required_fields": [
    {
      "field_id": "city",
      "source_column": "城市",
      "present": true
    },
    {
      "field_id": "full_major_name",
      "source_column": "专业全称",
      "present": true
    },
    {
      "field_id": "group_code",
      "source_column": "院校专业组代码",
      "present": true
    },
    {
      "field_id": "group_min_rank_2024",
      "source_column": "专业组最低位次1",
      "present": true
    },
    {
      "field_id": "group_min_score_2024",
      "source_column": "专业组最低分1",
      "present": true
    },
    {
      "field_id": "group_name",
      "source_column": "专业组名称",
      "present": true
    },
    {
      "field_id": "major_code",
      "source_column": "专业代码",
      "present": true
    },
    {
      "field_id": "major_max_score_2024",
      "source_column": "最高分1",
      "present": true
    },
    {
      "field_id": "major_min_rank_2024",
      "source_column": "最低位次1",
      "present": true
    },
    {
      "field_id": "major_min_score_2024",
      "source_column": "最低分1",
      "present": true
    },
    {
      "field_id": "major_name",
      "source_column": "专业名称",
      "present": true
    },
    {
      "field_id": "plan_count",
      "source_column": "计划人数",
      "present": true
    },
    {
      "field_id": "school_province",
      "source_column": "所在省",
      "present": true
    },
    {
      "field_id": "tuition_yuan_per_year",
      "source_column": "学费",
      "present": true
    },
    {
      "field_id": "university_name",
      "source_column": "院校名称",
      "present": true
    },
    {
      "field_id": "year",
      "source_column": "年份",
      "present": true
    }
  ],
  "missing_fields": []
}
```
## Target Query Results
```json
[
  {
    "query": "列出25年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数",
    "status": "ok",
    "query_type": "group_detail_report",
    "result_count": 1,
    "items": [
      {
        "item_id": "result_001",
        "title": "深圳大学",
        "subtitle": "物理225组（2 个专业）",
        "primary_attributes": [
          {
            "key": "year",
            "label": "year",
            "value": 2025
          },
          {
            "key": "university_name",
            "label": "university_name",
            "value": "深圳大学"
          },
          {
            "key": "group_code",
            "label": "group_code",
            "value": "10590225"
          },
          {
            "key": "group_name",
            "label": "group_name",
            "value": "物理225组"
          }
        ],
        "secondary_attributes": [
          {
            "key": "major_name",
            "label": "major_name",
            "value": "物理225组（2 个专业）"
          },
          {
            "key": "rank_2024",
            "label": "rank_2024",
            "value": 7800
          },
          {
            "key": "group_min_rank",
            "label": "group_min_rank",
            "value": 7800
          }
        ],
        "matched_filters": [
          {
            "id": "planned_year",
            "field": "年份",
            "operator": "eq",
            "value": 2025,
            "matched": false,
            "text": ""
          },
          {
            "id": "planned_university_name",
            "field": "院校名称",
            "operator": "contains",
            "value": "深圳大学",
            "matched": false,
            "text": ""
          }
        ],
        "raw": {
          "年份": 2025,
          "院校名称": "深圳大学",
          "院校专业组代码": "10590225",
          "专业组名称": "物理225组",
          "专业组最低分1": 634,
          "专业组最低位次1": 7800,
          "专业名称": "物理225组（2 个专业）"
        }
      }
    ],
    "top_results": [
      {
        "id": "result_001",
        "trace": [],
        "year": 2025,
        "batch": null,
        "university_code": null,
        "university_name": "深圳大学",
        "group_code": "10590225",
        "group_name": "物理225组",
        "major_code": null,
        "major_name": "物理225组（2 个专业）",
        "full_major_name": null,
        "subject_requirement": null,
        "province": null,
        "city": null,
        "tuition": null,
        "rank_2024": 7800,
        "major_rank_2024": null,
        "plan_count": null,
        "group_min_rank": 7800,
        "major_min_rank": null,
        "safety_margin": ""
      }
    ],
    "result_sections": {
      "groups": [
        {
          "group_code": "10590225",
          "group_title": "物理225组",
          "group_metric_score": 634,
          "group_min_rank": 7800,
          "major_count": 2,
          "majors": [
            {
              "major_code": "80901",
              "major_name": "计算机科学与技术",
              "full_major_name": "计算机科学与技术",
              "min_score": 631,
              "min_rank": 7700,
              "max_score": 645,
              "plan_count": 30
            },
            {
              "major_code": "80717",
              "major_name": "人工智能",
              "full_major_name": "人工智能",
              "min_score": 630,
              "min_rank": 7800,
              "max_score": 644,
              "plan_count": 20
            }
          ]
        }
      ]
    },
    "warnings": [
      {
        "code": "metric_default_used",
        "severity": "warning",
        "message": "“录取最高”按 domain pack 默认指标：专业组最低分最高。",
        "metric": "group_min_score_2024",
        "sort": "DESC"
      }
    ],
    "evidence_pack": {
      "user_request": "列出25年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数",
      "query_type": "group_detail_report",
      "executed_rules": [
        {
          "rule_id": "planned_year",
          "field": "年份",
          "operator": "eq",
          "value": 2025
        },
        {
          "rule_id": "planned_university_name",
          "field": "院校名称",
          "operator": "contains",
          "value": "深圳大学"
        }
      ],
      "candidate_confirmations": [],
      "not_executed_preferences": [],
      "result_count": 1,
      "top_k_results": [
        {
          "id": "result_001",
          "trace": [],
          "year": 2025,
          "batch": null,
          "university_code": null,
          "university_name": "深圳大学",
          "group_code": "10590225",
          "group_name": "物理225组",
          "major_code": null,
          "major_name": "物理225组（2 个专业）",
          "full_major_name": null,
          "subject_requirement": null,
          "province": null,
          "city": null,
          "tuition": null,
          "rank_2024": 7800,
          "major_rank_2024": null,
          "plan_count": null,
          "group_min_rank": 7800,
          "major_min_rank": null,
          "safety_margin": ""
        }
      ],
      "result_sections": {
        "groups": [
          {
            "group_code": "10590225",
            "group_title": "物理225组",
            "group_metric_score": 634,
            "group_min_rank": 7800,
            "major_count": 2,
            "majors": [
              {
                "major_code": "80901",
                "major_name": "计算机科学与技术",
                "full_major_name": "计算机科学与技术",
                "min_score": 631,
                "min_rank": 7700,
                "max_score": 645,
                "plan_count": 30
              },
              {
                "major_code": "80717",
                "major_name": "人工智能",
                "full_major_name": "人工智能",
                "min_score": 630,
                "min_rank": 7800,
                "max_score": 644,
                "plan_count": 20
              }
            ]
          }
        ]
      },
      "trace_summary": {
        "top_k": 5,
        "query_type": "group_detail_report",
        "result_count": 1
      },
      "extracted_preferences": [
        {
          "id": "query_type",
          "slot": "query_type",
          "value": "group_detail_report",
          "status": "planned"
        }
      ],
      "attribute_grounding_summary": {},
      "proposed_rule_audit": [],
      "execution_summary": {
        "executor": "duckdb",
        "query_type": "group_detail_report",
        "sql": "SELECT\n  CAST(\"院校专业组代码\" AS VARCHAR) AS group_code,\n  ANY_VALUE(CAST(\"专业组名称\" AS VARCHAR)) AS group_title,\n  MAX(TRY_CAST(regexp_extract(REPLACE(CAST(\"专业组最低分1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE)) AS group_metric_score,\n  MIN(TRY_CAST(regexp_extract(REPLACE(CAST(\"专业组最低位次1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE)) AS group_min_rank,\n  COUNT(*) AS major_count\nFROM \"admissions\"\nWHERE TRY_CAST(regexp_extract(REPLACE(CAST(\"年份\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) = ?\n  AND STRPOS(CAST(\"院校名称\" AS VARCHAR), ?) > 0\n  AND \"院校专业组代码\" IS NOT NULL\nGROUP BY CAST(\"院校专业组代码\" AS VARCHAR)\nORDER BY group_metric_score DESC NULLS LAST, group_code ASC\nLIMIT ?",
        "params": [
          2025,
          "深圳大学",
          5
        ],
        "detail_sql": "SELECT\n  CAST(\"院校专业组代码\" AS VARCHAR) AS group_code,\n  CAST(\"专业组名称\" AS VARCHAR) AS group_title,\n  CAST(\"专业代码\" AS VARCHAR) AS major_code,\n  CAST(\"专业名称\" AS VARCHAR) AS major_name,\n  CAST(\"专业全称\" AS VARCHAR) AS full_major_name,\n  TRY_CAST(regexp_extract(REPLACE(CAST(\"最低分1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) AS min_score,\n  TRY_CAST(regexp_extract(REPLACE(CAST(\"最低位次1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) AS min_rank,\n  TRY_CAST(regexp_extract(REPLACE(CAST(\"最高分1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) AS max_score,\n  TRY_CAST(regexp_extract(REPLACE(CAST(\"计划人数\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) AS plan_count\nFROM \"admissions\"\nWHERE TRY_CAST(regexp_extract(REPLACE(CAST(\"年份\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) = ?\n  AND STRPOS(CAST(\"院校名称\" AS VARCHAR), ?) > 0\n  AND CAST(\"院校专业组代码\" AS VARCHAR) IN (?)\nORDER BY group_code ASC, min_score DESC NULLS LAST, major_code ASC",
        "detail_params": [
          2025,
          "深圳大学",
          "10590225"
        ],
        "input_row_count": 6,
        "filtered_row_count": 1,
        "nested_result_count": 2,
        "group_by": [
          "院校专业组代码",
          "专业组名称"
        ],
        "metric": {
          "field_id": "group_min_score_2024",
          "field": "专业组最低分1",
          "direction": "DESC"
        },
        "sort": [
          {
            "field": "专业组最低分1",
            "direction": "DESC"
          }
        ],
        "top_k": 5,
        "hard_rule_ids": [
          "planned_year",
          "planned_university_name"
        ],
        "skipped_soft_rule_ids": [],
        "warnings": [
          {
            "code": "metric_default_used",
            "severity": "warning",
            "message": "“录取最高”按 domain pack 默认指标：专业组最低分最高。",
            "metric": "group_min_score_2024",
            "sort": "DESC"
          }
        ]
      },
      "attribute_explanations": [],
      "confirmed_rules": [],
      "confirmation_source": [],
      "executed_after_confirmation": [],
      "unconfirmed_candidates": [],
      "no_schema_field_preferences": [],
      "rejected_confirmations": [],
      "policy_references": []
    },
    "sql": "SELECT\n  CAST(\"院校专业组代码\" AS VARCHAR) AS group_code,\n  ANY_VALUE(CAST(\"专业组名称\" AS VARCHAR)) AS group_title,\n  MAX(TRY_CAST(regexp_extract(REPLACE(CAST(\"专业组最低分1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE)) AS group_metric_score,\n  MIN(TRY_CAST(regexp_extract(REPLACE(CAST(\"专业组最低位次1\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE)) AS group_min_rank,\n  COUNT(*) AS major_count\nFROM \"admissions\"\nWHERE TRY_CAST(regexp_extract(REPLACE(CAST(\"年份\" AS VARCHAR), ',', ''), '\\d+(?:\\.\\d+)?') AS DOUBLE) = ?\n  AND STRPOS(CAST(\"院校名称\" AS VARCHAR), ?) > 0\n  AND \"院校专业组代码\" IS NOT NULL\nGROUP BY CAST(\"院校专业组代码\" AS VARCHAR)\nORDER BY group_metric_score DESC NULLS LAST, group_code ASC\nLIMIT ?",
    "params": [
      2025,
      "深圳大学",
      5
    ],
    "failures": []
  },
  {
    "query": "假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐",
    "status": "needs_confirmation",
    "query_type": "recommendation",
    "result_count": 0,
    "items": [],
    "top_results": [],
    "result_sections": {
      "reach": {
        "label": "冲",
        "items": []
      },
      "match": {
        "label": "稳",
        "items": []
      },
      "safety": {
        "label": "保",
        "items": []
      }
    },
    "warnings": [
      {
        "code": "score_without_rank",
        "severity": "error",
        "message": "只提供分数没有位次；请补充广东省排位，系统不会仅凭分数执行推荐。"
      }
    ],
    "evidence_pack": {
      "user_request": "假设我今年的高考分数是630分，想读人工智能，计算机，而且不想去国外，想留在广东省，请给出推荐",
      "query_type": "recommendation",
      "executed_rules": [],
      "candidate_confirmations": [],
      "not_executed_preferences": [
        {
          "source_text": "不想去国外",
          "field_id": "school_country_or_region",
          "field": "无可执行字段",
          "match_type": "no_schema_field",
          "executable": false,
          "reason": "当前 domain pack 未启用境外办学字段，不能执行该排除条件。"
        }
      ],
      "result_count": 0,
      "top_k_results": [],
      "result_sections": {
        "reach": {
          "label": "冲",
          "items": []
        },
        "match": {
          "label": "稳",
          "items": []
        },
        "safety": {
          "label": "保",
          "items": []
        }
      },
      "trace_summary": {
        "top_k": 5,
        "query_type": "recommendation",
        "result_count": 0
      },
      "extracted_preferences": [
        {
          "id": "pref_major",
          "slot": "专业名称",
          "value": [
            "计算机",
            "人工智能"
          ],
          "status": "已对齐字段"
        },
        {
          "id": "pref_score",
          "slot": "分数",
          "value": 630,
          "status": "等待补充位次，未用于执行"
        },
        {
          "id": "pref_school_province",
          "slot": "院校所在地省份",
          "value": [
            "广东"
          ],
          "status": "已对齐字段"
        }
      ],
      "attribute_grounding_summary": {},
      "proposed_rule_audit": [],
      "execution_summary": {
        "executor": null,
        "query_type": "recommendation",
        "sql": "",
        "params": [],
        "input_row_count": 0,
        "filtered_row_count": 0,
        "nested_result_count": 0,
        "group_by": [],
        "metric": null,
        "sort": [],
        "top_k": 0,
        "hard_rule_ids": [],
        "skipped_soft_rule_ids": [],
        "warnings": [
          {
            "code": "score_without_rank",
            "severity": "error",
            "message": "只提供分数没有位次；请补充广东省排位，系统不会仅凭分数执行推荐。"
          }
        ]
      },
      "attribute_explanations": [],
      "confirmed_rules": [],
      "confirmation_source": [],
      "executed_after_confirmation": [],
      "unconfirmed_candidates": [],
      "no_schema_field_preferences": [
        {
          "source_text": "不想去国外",
          "field_id": "school_country_or_region",
          "field": "无可执行字段",
          "match_type": "no_schema_field",
          "executable": false,
          "reason": "当前 domain pack 未启用境外办学字段，不能执行该排除条件。"
        }
      ],
      "rejected_confirmations": [],
      "policy_references": []
    },
    "sql": "",
    "params": [],
    "failures": []
  }
]
```
## Warnings
```json
[
  {
    "code": "upload_received",
    "severity": "info",
    "message": "文件已保存到托管数据目录。",
    "size_bytes": 6557,
    "extension": ".xlsx"
  },
  {
    "code": "merged_cells_detected",
    "severity": "warning",
    "message": "检测到合并单元格，请确认表头和数据未被合并结构影响。",
    "ranges": [
      "A1:C1"
    ]
  },
  {
    "code": "hidden_rows_or_columns_detected",
    "severity": "warning",
    "message": "检测到隐藏行或隐藏列，ingestion 会按文件内容读取。",
    "hidden_rows": [
      2
    ],
    "hidden_columns": []
  },
  {
    "code": "formula_cells_detected",
    "severity": "warning",
    "message": "检测到公式单元格；读取值可能依赖 Excel 缓存，请人工核验。",
    "cells": [
      "Z4"
    ]
  }
]
```
## Failures
```json
[]
```
