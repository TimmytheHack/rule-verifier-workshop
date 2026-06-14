# 备份与恢复

本文说明 uploaded dataset、domain pack、warehouse 和 audit log 的备份恢复策略。

## 需要备份的内容

生产环境至少备份持久卷 `/data`：

| 路径 | 内容 |
|---|---|
| `/data/uploaded_datasets/<dataset_id>/source/` | 上传原始 CSV/Excel。 |
| `/data/uploaded_datasets/<dataset_id>/dataset.json` | dataset metadata、状态、fingerprint、history。 |
| `/data/uploaded_datasets/<dataset_id>/domain_packs/` | draft/reviewed domain pack、review.yaml、warehouse 配置。 |
| `/data/uploaded_datasets/<dataset_id>/domain_packs/<domain>/warehouse/` | DuckDB warehouse 和 schema/value index。 |
| `/data/uploaded_datasets/<dataset_id>/domain_packs/<domain>/ingestion_summary.json` | 入仓摘要。 |
| `/data/outputs/tool_audit/` | tool invocation audit JSONL 和轮转文件。 |

不要把 `.env` 和密钥文件混入普通数据备份；secret 应由独立 secret manager 管理。

## 备份步骤

建议在低流量窗口执行：

```bash
docker compose stop api
tar -czf szu-data-backup-$(date +%Y%m%d%H%M%S).tar.gz -C /path/to/volume data
docker compose up -d api
```

如果必须在线备份，应先暂停 operator 的 upload、review 和 build warehouse 操作。查询可以继续运行，但备份中可能包含新旧 audit 文件边界。

## 恢复步骤

1. 停止服务：

```bash
docker compose stop api
```

2. 恢复持久卷：

```bash
rm -rf /path/to/volume/data
tar -xzf szu-data-backup-YYYYMMDDHHMMSS.tar.gz -C /path/to/volume
```

3. 确认环境变量仍指向同一持久化目录：

```bash
DATA_ROOT=/data/uploaded_datasets
OUTPUT_ROOT=/data/outputs
TOOL_AUDIT_LOG_PATH=/data/outputs/tool_audit/audit.jsonl
```

4. 启动服务并检查：

```bash
docker compose up -d api
curl http://127.0.0.1:8001/readyz
```

## 恢复后校验

对每个关键 dataset 执行：

1. `dataset.profile` 能读取字段事实；
2. `dataset.review_summary` 能读取 review 状态；
3. `workbench.query` 对 approved/queryable dataset 返回 `ok`、`needs_confirmation` 或 `no_results`；
4. stale fingerprint 或缺失 warehouse 仍返回 `blocked`；
5. audit log 继续写入并轮转。

如果 fingerprint guard 失败，不要手工修改 DuckDB metadata。应由拥有 `warehouse_admin` 权限的 operator 重新运行 `dataset.build_warehouse`。

## 灾难恢复注意事项

- 如果只恢复了 source 和 domain pack，没有恢复 warehouse，可以重新 build warehouse。
- 如果只恢复了 warehouse，没有恢复 source，Workbench 会因缺源文件或 fingerprint 不一致而 `blocked`。
- 如果恢复后的 `AUTH_TOKENS_JSON` 不同，历史 audit 的 `actor_id` 仍保留，但旧 token 不再有效。
- 如果审计日志被截断，应在事故报告中记录备份时间点和缺口范围。
