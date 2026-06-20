# 程序风险审查报告（2026-06-20）

## 审查目标

本次审查检查硬编码、规则边界绕过、API/tool 权限伤害、前端误导风险、发布文档缺口。核心不变量保持不变：自然语言、前端和 LLM tool call 只能提出结构化意图，只有经过 schema grounding、RuleVerifier、confirmation loop、DuckDB executor 和 EvidencePack 边界的规则可以执行。

## 审查范围

| lane | 范围 | 负责人 |
|---|---|---|
| 后端规则管线 | Extractor 到 EvidencePack 的执行边界、hard rule 来源、candidate_id、no-schema 偏好 | Agent 1 |
| API/tool 权限 | HTTP 鉴权、LLM-safe tool、audit、路径、错误净化、schema contract | Agent 2 |
| 前端 smoke 与 UX | Vite 构建、后端 smoke、dev token、前端 hard filter 入口、确认与未执行展示 | Agent 3 |
| 文档与发布 | README、安全模型、tool contract、生产部署、release checklist、sample outputs | Agent 4 |

## 基线命令

```text
.venv/bin/python -m unittest discover -s tests
cd frontend && npm run build
git diff --check
```

## 初始硬编码扫描

```text
rg -n "(/Users/|outputs/|广东省|duckdb|localhost|127\\.0\\.0\\.1|deepseek|api[_-]?key|token|password|subprocess|shell=True|eval\\(|exec\\(|raw_sql|sql|hard_filters|confirmed_candidates|candidate_id|allow_origins|DATA_ROOT|OUTPUT_ROOT)" src frontend docs tests scripts schemas domains README.md RELEASE_CHECKLIST.md CHANGELOG.md docker-compose.yml Dockerfile Makefile
```

## 发现列表

| id | severity | lane | 文件 | 证据 | 风险 | 建议 | 状态 |
|---|---|---|---|---|---|---|---|

## 已确认安全不变量

| invariant | 证据 | 覆盖测试 |
|---|---|---|

## 残余风险

| 风险 | 原因 | 后续动作 |
|---|---|---|
