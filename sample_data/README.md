# 样例数据

本目录只放小型、脱敏、可提交的演示数据，不放真实招生大表、DuckDB、上传原件或带密钥文件。

| 文件 | 用途 |
|---|---|
| `admissions_minimal.csv` | admissions uploaded dataset 流程演示，覆盖专业组明细和推荐查询所需字段。 |
| `housing.csv` | housing toy domain 20 行 fixture。 |
| `products.csv` | products toy domain 20 行 fixture，包含 `email_contact` 用于演示 PII-like 字段审查。 |

正式试运行真实 Excel 时使用：

```bash
.venv/bin/python scripts/run_operator_trial.py path/to/admissions.xlsx
```

这些 sample data 可以用于 operator 或前端 demo，但不能代替人工 review/approval、warehouse fingerprint guard 或 Quality Gate。
