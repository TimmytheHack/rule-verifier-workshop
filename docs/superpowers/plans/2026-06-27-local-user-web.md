# 独立本地用户 Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个独立的本地用户 Web，让用户先选择本机数据源，再基于后端能力摘要上传、配置 LLM、查询和查看证据。

**Architecture:** 后端补齐产品化 API：数据源列表、能力摘要、LLM 本机设置和发行模式。前端新增 `frontend-user/`，不复用旧 mock/demo 页面，所有查询 UI 都由 `semantic_query_options`、`capability_level` 和 `recommendation_readiness` 驱动。admissions domain pack 只作为后端内部已审查能力种子，前端不读取模板名来决定 UI。

**Tech Stack:** FastAPI、现有 `DatasetService`、标准库 JSON 配置、Vue 3、Vite、Node `node --test`、现有 `/datasets/*` 和 `/workbench/*` API。

---

## Scope Check

本计划覆盖一个可独立运行的第一版本地用户 Web。它包含后端 API、前端新应用和发行模式，但不包含 Tauri/Electron 打包，也不迁移旧研发前端。

## 文件结构

- Modify: `src/api/dataset_service.py`
  - 新增 `list_datasets()`，返回无本地路径泄漏的数据源列表。
  - 新增能力摘要字段，供前端用 `capability_level` / `recommendation_readiness` 渲染。
- Modify: `src/api/server.py`
  - 新增 `GET /datasets`、`GET /settings/llm`、`POST /settings/llm`。
  - 为 `APP_DISTRIBUTION_MODE=user_upload_only` 暴露状态。
- Create: `src/api/local_settings.py`
  - 本机 LLM 配置读写、状态返回和密钥读取。
- Modify: `src/extractors/deepseek_extractor.py`
  - `env_value()` 在环境变量和 `.env` 之外读取本机配置。
- Modify: `.env.example`
  - 增加发行模式和本机设置路径示例。
- Modify: `.gitignore`
  - 忽略本机 LLM 设置文件目录。
- Test: `tests/test_uploaded_dataset_flow.py`
  - 覆盖数据源列表和能力摘要。
- Test: `tests/test_server_deployment.py`
  - 覆盖新增设置接口和发行配置。
- Create: `frontend-user/package.json`
  - 独立前端包脚本和依赖。
- Create: `frontend-user/vite.config.js`
  - 代理 `/api`、`/datasets`、`/workbench`、`/settings`。
- Create: `frontend-user/index.html`
  - 本地用户 Web 入口。
- Create: `frontend-user/src/main.js`
  - Vue app 挂载入口。
- Create: `frontend-user/src/App.vue`
  - 应用壳、路由状态和页面切换。
- Create: `frontend-user/src/styles/tokens.css`
  - 设计 token、布局、按钮、表单和状态色条。
- Create: `frontend-user/src/api/client.js`
  - fetch 包装、错误归一化。
- Create: `frontend-user/src/api/datasets.js`
  - 数据源列表、上传、profile、review、建仓、query API。
- Create: `frontend-user/src/api/settings.js`
  - LLM 设置 API。
- Create: `frontend-user/src/domain/queryOptions.js`
  - 把后端能力摘要转成 UI 控件模型。
- Test: `frontend-user/src/domain/queryOptions.test.js`
  - 验证 schema 驱动 UI 不读取模板名。
- Create: `frontend-user/src/pages/DatasetLibrary.vue`
  - 本机数据源首页。
- Create: `frontend-user/src/pages/DatasetDetail.vue`
  - 数据源详情和查询页。
- Create: `frontend-user/src/pages/SettingsPage.vue`
  - LLM 设置页。
- Create: `frontend-user/src/components/QueryComposer.vue`
  - schema 驱动查询输入。
- Create: `frontend-user/src/components/EvidenceSummary.vue`
  - 已执行、待确认、未执行和结果摘要。
- Create: `frontend-user/src/components/ImportPanel.vue`
  - 上传、生成 domain pack、approve、建仓的串行导入。
- Create: `frontend-user/README.md`
  - 新 Web 的本地运行、构建和边界说明。

## Task 1: 数据源列表 API 和能力摘要

**Files:**
- Modify: `src/api/dataset_service.py`
- Modify: `src/api/server.py`
- Test: `tests/test_uploaded_dataset_flow.py`

- [ ] **Step 1: 写 `DatasetService.list_datasets()` 的失败测试**

Append to `tests/test_uploaded_dataset_flow.py`:

```python
    def test_list_datasets_returns_safe_summaries(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            service, dataset_id = _generated_generic_dataset(root)
            metadata_path = service._metadata_path(dataset_id)  # noqa: SLF001
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata.update(
                {
                    "status": "queryable",
                    "domain_name": "leases",
                    "warehouse_database_path": str(root / "secret.duckdb"),
                    "capability_level": "filterable",
                    "recommendation_readiness": "not_applicable",
                }
            )
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            payload = service.list_datasets()

        self.assertEqual(len(payload["datasets"]), 1)
        item = payload["datasets"][0]
        self.assertEqual(item["dataset_id"], dataset_id)
        self.assertEqual(item["status"], "queryable")
        self.assertEqual(item["capability_level"], "filterable")
        self.assertEqual(item["recommendation_readiness"], "not_applicable")
        self.assertNotIn("source_path", item)
        self.assertNotIn("warehouse_database_path", item)
        self.assertNotIn(str(root), json.dumps(item, ensure_ascii=False))

        profile = service.profile(dataset_id)
        self.assertEqual(profile["domain_name"], "leases")
        self.assertEqual(profile["capability_level"], "filterable")
        self.assertEqual(profile["recommendation_readiness"], "not_applicable")

    def test_list_datasets_ignores_invalid_directories(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            service, dataset_id = _generated_generic_dataset(root)
            bad_dir = root / "bad"
            bad_dir.mkdir(parents=True, exist_ok=True)
            (bad_dir / "dataset.json").write_text("{}", encoding="utf-8")

            payload = service.list_datasets()

        self.assertEqual([item["dataset_id"] for item in payload["datasets"]], [dataset_id])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_list_datasets_returns_safe_summaries tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_list_datasets_ignores_invalid_directories
```

Expected: FAIL，提示 `DatasetService` 没有 `list_datasets`。

- [ ] **Step 3: 实现数据源列表和默认能力摘要**

Modify `src/api/dataset_service.py` inside `DatasetService` after `profile()`:

```python
    def list_datasets(self) -> dict[str, Any]:
        """列出本机托管数据源，不暴露本地文件路径。"""

        datasets: list[dict[str, Any]] = []
        if not self.root.exists():
            return {"datasets": datasets}
        for child in sorted(self.root.iterdir(), key=lambda path: path.name):
            if not child.is_dir():
                continue
            metadata_path = child / "dataset.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = _load_json(metadata_path)
                raw_dataset_id = metadata.get("dataset_id")
                if not raw_dataset_id:
                    continue
                dataset_id = str(raw_dataset_id)
                self._validate_dataset_id(dataset_id, allow_reserved=False)
                if self._dataset_dir(dataset_id).resolve() != child.resolve():
                    continue
            except (DatasetServiceError, OSError, ValueError, json.JSONDecodeError):
                continue
            datasets.append(_dataset_list_item(metadata))
        return {"datasets": datasets}
```

Add module-level helpers near `_review_result_payload`:

```python
def _dataset_list_item(metadata: dict[str, Any]) -> dict[str, Any]:
    warning_summary = _safe_issue_summary(metadata.get("warnings", []))
    error_summary = _safe_issue_summary(metadata.get("errors", []))
    item = {
        "dataset_id": metadata.get("dataset_id"),
        "status": metadata.get("status"),
        "domain_name": metadata.get("domain_name"),
        "domain_pack_status": metadata.get("domain_pack_status"),
        "capability_level": metadata.get("capability_level")
        or _default_capability_level(metadata),
        "recommendation_readiness": metadata.get("recommendation_readiness")
        or _default_recommendation_readiness(metadata),
        "original_filename": _safe_original_filename(metadata.get("original_filename")),
        "row_count": metadata.get("row_count"),
        "column_count": metadata.get("column_count"),
        "sheet_name": metadata.get("sheet_name"),
        "created_at": metadata.get("created_at"),
        "updated_at": metadata.get("updated_at"),
        "warning_count": warning_summary["count"],
        "error_count": error_summary["count"],
        "warning_codes": warning_summary["codes"],
        "error_codes": error_summary["codes"],
    }
    return {key: value for key, value in item.items() if value is not None}


def _safe_issue_summary(entries: Any) -> dict[str, Any]:
    if not isinstance(entries, list):
        return {"count": 0, "codes": []}
    codes = sorted(
        {
            code
            for entry in entries
            if isinstance(entry, dict)
            for code in [entry.get("code")]
            if _is_safe_issue_code(code)
        }
    )
    return {"count": len(entries), "codes": codes}


def _is_safe_issue_code(code: Any) -> bool:
    return isinstance(code, str) and bool(re.fullmatch(r"[A-Za-z0-9_.-]+", code))


def _safe_original_filename(filename: Any) -> str | None:
    if filename is None:
        return None
    normalized = str(filename).replace("\\", "/")
    return Path(normalized).name


def _default_capability_level(metadata: dict[str, Any]) -> str:
    if metadata.get("status") != "queryable":
        return "profile_only"
    if _uses_admissions_schema_template(metadata):
        return "admissions_filterable"
    return "filterable"


def _default_recommendation_readiness(metadata: dict[str, Any]) -> str:
    if metadata.get("status") != "queryable":
        return "not_ready"
    return "candidate_list" if _uses_admissions_schema_template(metadata) else "not_applicable"
```

- [ ] **Step 4: 让 profile 返回同一套能力摘要**

Modify `src/api/dataset_service.py` inside `profile()` return payload:

```python
            "domain_name": metadata.get("domain_name"),
            "domain_pack_status": metadata.get("domain_pack_status"),
            "capability_level": metadata.get("capability_level")
            or _default_capability_level(metadata),
            "recommendation_readiness": metadata.get("recommendation_readiness")
            or _default_recommendation_readiness(metadata),
```

Place these fields beside `dataset_id` and `status`, before `source_fingerprint`.

- [ ] **Step 5: 暴露 `GET /datasets`**

Modify `src/api/server.py` before `@app.post("/datasets/upload")`:

```python
@app.get("/datasets")
def list_datasets(request: Request) -> dict[str, object]:
    """列出本机托管数据源。"""

    try:
        _ensure_scope(_actor_context_from_request(request), "read_only")
        return dataset_service.list_datasets()
    except DatasetServiceError as exc:
        raise _dataset_http_error(exc) from exc
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_list_datasets_returns_safe_summaries tests.test_uploaded_dataset_flow.UploadedDatasetFlowTest.test_list_datasets_ignores_invalid_directories
```

Expected: OK.

- [ ] **Step 7: 提交**

```bash
git add src/api/dataset_service.py src/api/server.py tests/test_uploaded_dataset_flow.py
git commit -m "feat: list local datasets"
```

## Task 2: 本机 LLM 设置 API

**Files:**
- Create: `src/api/local_settings.py`
- Modify: `src/api/server.py`
- Modify: `src/extractors/deepseek_extractor.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Test: `tests/test_server_deployment.py`

- [ ] **Step 1: 写 LLM 设置测试**

Append to `tests/test_server_deployment.py`:

```python
    def test_llm_settings_status_does_not_return_secret(self) -> None:
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "llm.json"
            with patch.dict(
                "os.environ",
                {"LOCAL_SETTINGS_PATH": str(settings_path), "AUTH_TOKENS_JSON": json.dumps({
                    "operator-token": {
                        "actor_id": "operator",
                        "permission_scopes": ["read_only", "diagnostics"],
                    }
                })},
                clear=False,
            ):
                response = self.client.post(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                    json={
                        "enabled": True,
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "api_url": "https://api.deepseek.com/chat/completions",
                        "api_key": "secret-test-key",
                    },
                )
                status = self.client.get(
                    "/settings/llm",
                    headers={"X-Actor-Token": "operator-token"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(status.status_code, 200)
        payload = status.json()
        self.assertTrue(payload["api_key_configured"])
        self.assertNotIn("api_key", payload)
        self.assertNotIn("secret-test-key", json.dumps(payload))
```

Add imports at top if absent:

```python
import os
from unittest.mock import patch
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_server_deployment.ServerDeploymentTest.test_llm_settings_status_does_not_return_secret
```

Expected: FAIL，`/settings/llm` 不存在。

- [ ] **Step 3: 新增本机设置模块**

Create `src/api/local_settings.py`:

```python
"""本机产品设置，避免把密钥暴露给前端。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS_PATH = Path("outputs/local_settings/llm.json")
SUPPORTED_PROVIDERS = {"deepseek"}


def settings_path() -> Path:
    return Path(os.getenv("LOCAL_SETTINGS_PATH", str(DEFAULT_SETTINGS_PATH)))


def llm_status() -> dict[str, Any]:
    settings = _read_settings()
    provider = settings.get("provider") or "deepseek"
    return {
        "enabled": bool(settings.get("enabled")),
        "provider": provider,
        "model": settings.get("model") or "deepseek-chat",
        "api_url": settings.get("api_url") or "https://api.deepseek.com/chat/completions",
        "api_key_configured": bool(settings.get("api_key")),
    }


def save_llm_settings(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "deepseek")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的 LLM provider：{provider}")
    settings = {
        "enabled": bool(payload.get("enabled")),
        "provider": provider,
        "model": str(payload.get("model") or "deepseek-chat"),
        "api_url": str(
            payload.get("api_url") or "https://api.deepseek.com/chat/completions"
        ),
    }
    api_key = str(payload.get("api_key") or "").strip()
    existing = _read_settings()
    if api_key:
        settings["api_key"] = api_key
    elif existing.get("api_key"):
        settings["api_key"] = existing["api_key"]
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return llm_status()


def local_setting_value(name: str) -> str | None:
    settings = _read_settings()
    if not settings.get("enabled"):
        return None
    mapping = {
        "DEEPSEEK_API_KEY": "api_key",
        "DEEPSEEK_MODEL": "model",
        "DEEPSEEK_API_URL": "api_url",
        "ENABLE_LLM": "enabled",
    }
    key = mapping.get(name)
    if not key:
        return None
    value = settings.get(key)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if value else None


def _read_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
```

- [ ] **Step 4: 接入 DeepSeek 配置读取**

Modify `src/extractors/deepseek_extractor.py` in `env_value()` after `os.getenv(name)` and before `_dotenv_paths()` loop:

```python
    try:
        from src.api.local_settings import local_setting_value

        local_value = local_setting_value(name)
    except Exception:  # noqa: BLE001 - 本机设置不可用时回退到 .env。
        local_value = None
    if local_value:
        return local_value
```

- [ ] **Step 5: 暴露设置 API**

Modify `src/api/server.py` imports:

```python
from src.api.local_settings import llm_status, save_llm_settings
```

Add request model near other models:

```python
class LLMSettingsRequest(BaseModel):
    """本机 LLM 设置请求。"""

    enabled: bool = False
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_url: str = "https://api.deepseek.com/chat/completions"
    api_key: str | None = None
```

Add endpoints before tool endpoints:

```python
@app.get("/settings/llm")
def get_llm_settings(request: Request) -> dict[str, Any]:
    """返回本机 LLM 配置状态，不返回密钥明文。"""

    _ensure_scope(_actor_context_from_request(request), "read_only")
    return llm_status()


@app.post("/settings/llm")
def update_llm_settings(
    request: LLMSettingsRequest,
    http_request: Request,
) -> dict[str, Any]:
    """保存本机 LLM 配置，不把密钥回显给前端。"""

    _ensure_scope(_actor_context_from_request(http_request), "diagnostics")
    try:
        return save_llm_settings(request.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_llm_settings", "message": str(exc)},
        ) from exc
```

- [ ] **Step 6: 更新配置示例和忽略规则**

Append to `.env.example`:

```env
APP_DISTRIBUTION_MODE=user_upload_only
LOCAL_SETTINGS_PATH=outputs/local_settings/llm.json
```

Append to `.gitignore`:

```gitignore
outputs/local_settings/
```

- [ ] **Step 7: 运行测试确认通过**

Run:

```bash
.venv/bin/python -m unittest tests.test_server_deployment.ServerDeploymentTest.test_llm_settings_status_does_not_return_secret
```

Expected: OK.

- [ ] **Step 8: 提交**

```bash
git add src/api/local_settings.py src/api/server.py src/extractors/deepseek_extractor.py .env.example .gitignore tests/test_server_deployment.py
git commit -m "feat: add local llm settings"
```

## Task 3: 独立 `frontend-user` 项目骨架

**Files:**
- Create: `frontend-user/package.json`
- Create: `frontend-user/vite.config.js`
- Create: `frontend-user/index.html`
- Create: `frontend-user/src/main.js`
- Create: `frontend-user/src/App.vue`
- Create: `frontend-user/src/styles/tokens.css`
- Create: `frontend-user/README.md`

- [ ] **Step 1: 创建 package 和 Vite 配置**

Create `frontend-user/package.json`:

```json
{
  "name": "local-admissions-workbench",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "vite build",
    "preview": "vite preview --host 127.0.0.1",
    "test:unit": "node --test \"src/**/*.test.js\""
  },
  "dependencies": {
    "@vitejs/plugin-vue": "^5.2.4",
    "vite": "^5.4.19",
    "vue": "^3.5.17"
  },
  "devDependencies": {}
}
```

Create `frontend-user/vite.config.js`:

```js
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001';

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': backendTarget,
      '/datasets': backendTarget,
      '/workbench': backendTarget,
      '/settings': backendTarget,
    },
  },
});
```

- [ ] **Step 2: 创建入口文件**

Create `frontend-user/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>本地招生数据工作台</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

Create `frontend-user/src/main.js`:

```js
import { createApp } from 'vue';
import App from './App.vue';
import './styles/tokens.css';

createApp(App).mount('#app');
```

Create initial `frontend-user/src/App.vue`:

```vue
<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="kicker">本机数据</p>
        <h1>本地招生数据工作台</h1>
      </div>
      <button class="secondary-button" type="button">设置</button>
    </header>
    <section class="empty-panel">
      <h2>先导入一份表格</h2>
      <p>表格、规则和密钥都保存在本机。导入后，下次打开可以直接继续查询。</p>
      <button class="primary-button" type="button">导入表格</button>
    </section>
  </main>
</template>
```

- [ ] **Step 3: 写设计 token CSS**

Create `frontend-user/src/styles/tokens.css`:

```css
:root {
  color-scheme: light;
  --surface: #f6f8f5;
  --surface-elevated: #ffffff;
  --text-primary: #17362f;
  --text-muted: #60766e;
  --accent: #2b6f8f;
  --review: #d19b3d;
  --danger: #b94b43;
  --border: #d7dfd5;
  --radius: 8px;
  font-family:
    Atkinson Hyperlegible,
    -apple-system,
    BlinkMacSystemFont,
    "PingFang SC",
    "Microsoft YaHei",
    sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 320px;
  background: var(--surface);
  color: var(--text-primary);
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  min-height: 44px;
  cursor: pointer;
}

button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--accent) 48%, white);
  outline-offset: 2px;
}

.app-shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 24px 0 48px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 68px;
  gap: 16px;
  padding: 16px 0;
}

.kicker {
  margin: 0 0 4px;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 700;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 0;
  font-size: clamp(28px, 4vw, 40px);
  line-height: 1.12;
}

.empty-panel {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-elevated);
  padding: 24px;
}

.primary-button,
.secondary-button {
  border: 1px solid transparent;
  border-radius: var(--radius);
  padding: 0 16px;
  font-weight: 800;
}

.primary-button {
  background: var(--text-primary);
  color: #ffffff;
}

.secondary-button {
  background: var(--surface-elevated);
  color: var(--text-primary);
  border-color: var(--border);
}

@media (prefers-reduced-motion: no-preference) {
  button {
    transition:
      transform 160ms ease,
      background-color 160ms ease,
      border-color 160ms ease;
  }

  button:active {
    transform: translateY(1px);
  }
}
```

- [ ] **Step 4: 添加 README**

Create `frontend-user/README.md`:

```markdown
# 本地用户 Web

这是独立于现有研发前端的本地用户 Web。页面不读取旧 mock/demo 数据，不展示内部 admissions 数据源，只消费本机后端返回的数据源和能力摘要。

## 本地运行

```bash
npm install
npm run dev
```

后端默认代理到 `http://127.0.0.1:8001`，可用 `VITE_API_PROXY_TARGET` 覆盖。

## 验证

```bash
npm run test:unit
npm run build
```
```

- [ ] **Step 5: 安装依赖并构建**

Run:

```bash
cd frontend-user && npm install && npm run build
```

Expected: Vite build exits 0 and creates `frontend-user/dist`.

- [ ] **Step 6: 提交**

```bash
git add frontend-user
git commit -m "feat: scaffold local user frontend"
```

## Task 4: 前端 API adapters 和能力模型

**Files:**
- Create: `frontend-user/src/api/client.js`
- Create: `frontend-user/src/api/datasets.js`
- Create: `frontend-user/src/api/settings.js`
- Create: `frontend-user/src/domain/queryOptions.js`
- Test: `frontend-user/src/domain/queryOptions.test.js`

- [ ] **Step 1: 写能力模型测试**

Create `frontend-user/src/domain/queryOptions.test.js`:

```js
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildQueryControls,
  summarizeDatasetCapability,
} from './queryOptions.js';

test('summarizeDatasetCapability ignores template ids and uses capability fields', () => {
  const summary = summarizeDatasetCapability({
    domain_template_id: 'legacy_template_x',
    capability_level: 'admissions_filterable',
    recommendation_readiness: 'candidate_list',
    semantic_query_options: {
      query_types: ['admissions_major_rank'],
      required_user_context: ['user_rank'],
    },
  });

  assert.equal(summary.label, '可查询候选列表');
  assert.equal(summary.requiresUserRank, true);
  assert.equal(summary.canCallRecommendation, false);
});

test('buildQueryControls renders filters and sort fields from backend options', () => {
  const controls = buildQueryControls({
    filters: {
      city: { source_column: '城市', allowed_ops: ['contains'], field_type: 'text' },
      tuition: { source_column: '学费', allowed_ops: ['between'], field_type: 'number' },
    },
    sort_fields: {
      tuition: { source_column: '学费', field_type: 'number' },
    },
    required_user_context: ['user_rank'],
  });

  assert.deepEqual(
    controls.requiredInputs.map((item) => item.id),
    ['user_rank'],
  );
  assert.deepEqual(
    controls.filters.map((item) => item.id),
    ['city', 'tuition'],
  );
  assert.equal(controls.sortFields[0].label, '学费');
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd frontend-user && npm run test:unit
```

Expected: FAIL，提示 `queryOptions.js` 不存在。

- [ ] **Step 3: 实现能力模型**

Create `frontend-user/src/domain/queryOptions.js`:

```js
const REQUIRED_INPUT_LABELS = {
  user_rank: '省排位',
};

const CAPABILITY_LABELS = {
  admissions_profile_only: '只能查看字段',
  admissions_filterable: '可字段筛选',
  admissions_major_rank: '可查询专业位次',
  admissions_candidate_list: '可查询候选列表',
  admissions_verified_recommendation: '可生成验证推荐',
  filterable: '可字段筛选',
  profile_only: '只能查看字段',
};

export function summarizeDatasetCapability(profile = {}) {
  const options = profile.semantic_query_options || {};
  const queryTypes = Array.isArray(options.query_types) ? options.query_types : [];
  const capabilityLevel = profile.capability_level || inferCapabilityLevel(queryTypes);
  const readiness = profile.recommendation_readiness || 'not_ready';
  return {
    capabilityLevel,
    readiness,
    label: CAPABILITY_LABELS[capabilityLevel] || '能力待确认',
    queryTypes,
    requiresUserRank: requiredContext(options).includes('user_rank'),
    canCallRecommendation: capabilityLevel === 'admissions_verified_recommendation',
  };
}

export function buildQueryControls(options = {}) {
  return {
    requiredInputs: requiredContext(options).map((id) => ({
      id,
      label: REQUIRED_INPUT_LABELS[id] || id,
      type: id === 'user_rank' ? 'number' : 'text',
    })),
    filters: Object.entries(options.filters || {}).map(([id, value]) => ({
      id,
      label: value.source_column || id,
      allowedOps: value.allowed_ops || [],
      fieldType: value.field_type || 'text',
    })),
    sortFields: Object.entries(options.sort_fields || {}).map(([id, value]) => ({
      id,
      label: value.source_column || id,
      fieldType: value.field_type || 'text',
    })),
  };
}

function requiredContext(options = {}) {
  return Array.isArray(options.required_user_context)
    ? options.required_user_context
    : [];
}

function inferCapabilityLevel(queryTypes) {
  if (queryTypes.includes('semantic_recommendation')) {
    return 'admissions_candidate_list';
  }
  if (queryTypes.includes('admissions_major_rank')) {
    return 'admissions_major_rank';
  }
  return queryTypes.length ? 'filterable' : 'profile_only';
}
```

- [ ] **Step 4: 实现 API adapters**

Create `frontend-user/src/api/client.js`:

```js
export async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || {};
    throw new Error(detail.message || payload.message || `请求失败：${response.status}`);
  }
  return payload;
}
```

Create `frontend-user/src/api/datasets.js`:

```js
import { requestJson } from './client.js';

export function listDatasets() {
  return requestJson('/datasets');
}

export function datasetProfile(datasetId) {
  return requestJson(`/datasets/${encodeURIComponent(datasetId)}/profile`);
}

export function uploadDataset({ file, datasetId, sheetName }) {
  const params = new URLSearchParams({ filename: file.name });
  if (datasetId) params.set('dataset_id', datasetId);
  if (sheetName) params.set('sheet_name', sheetName);
  return fetch(`/datasets/upload?${params}`, {
    method: 'POST',
    body: file,
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail?.message || `上传失败：${response.status}`);
    }
    return payload;
  });
}

export function generateDomainPack(datasetId, payload = {}) {
  return requestJson(`/datasets/${encodeURIComponent(datasetId)}/generate-domain-pack`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function approveDomain(datasetId, payload = {}) {
  return requestJson(`/datasets/${encodeURIComponent(datasetId)}/approve-domain`, {
    method: 'POST',
    body: JSON.stringify({
      title_field: null,
      primary_fields: [],
      default_safe_sort: true,
      reviewed_by: 'local_user_web',
      ...payload,
    }),
  });
}

export function buildWarehouse(datasetId) {
  return requestJson(`/datasets/${encodeURIComponent(datasetId)}/build-warehouse`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}
```

Create `frontend-user/src/api/settings.js`:

```js
import { requestJson } from './client.js';

export function getLlmSettings() {
  return requestJson('/settings/llm');
}

export function saveLlmSettings(payload) {
  return requestJson('/settings/llm', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
```

- [ ] **Step 5: 运行前端单测**

Run:

```bash
cd frontend-user && npm run test:unit
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add frontend-user/src/api frontend-user/src/domain
git commit -m "feat: add local frontend api model"
```

## Task 5: 数据源首页和设置页

**Files:**
- Modify: `frontend-user/src/App.vue`
- Create: `frontend-user/src/pages/DatasetLibrary.vue`
- Create: `frontend-user/src/pages/SettingsPage.vue`
- Modify: `frontend-user/src/styles/tokens.css`

- [ ] **Step 1: 实现数据源首页**

Create `frontend-user/src/pages/DatasetLibrary.vue`:

```vue
<script setup>
defineProps({
  datasets: {
    type: Array,
    default: () => [],
  },
  loading: Boolean,
  error: String,
});

const emit = defineEmits(['open-dataset', 'open-import', 'open-settings']);
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <h2>我的数据源</h2>
        <p>先选择本机表格，再进入查询页。</p>
      </div>
      <button class="primary-button" type="button" @click="emit('open-import')">
        导入表格
      </button>
    </div>

    <p v-if="loading" class="state-line">正在读取本机数据源...</p>
    <p v-else-if="error" class="error-line">{{ error }}</p>

    <div v-else-if="datasets.length" class="dataset-grid">
      <article
        v-for="dataset in datasets"
        :key="dataset.dataset_id"
        class="dataset-card"
      >
        <div class="status-strip" :data-status="dataset.status"></div>
        <div class="dataset-card-body">
          <div class="dataset-card-title">
            <h3>{{ dataset.original_filename || dataset.dataset_id }}</h3>
            <span>{{ dataset.status || '未知状态' }}</span>
          </div>
          <dl class="metric-grid">
            <div>
              <dt>记录</dt>
              <dd>{{ dataset.row_count ?? '-' }}</dd>
            </div>
            <div>
              <dt>字段</dt>
              <dd>{{ dataset.column_count ?? '-' }}</dd>
            </div>
            <div>
              <dt>能力</dt>
              <dd>{{ dataset.capability_level || '待确认' }}</dd>
            </div>
          </dl>
          <button
            class="primary-button full-width"
            type="button"
            :disabled="dataset.status !== 'queryable'"
            @click="emit('open-dataset', dataset.dataset_id)"
          >
            开始查询
          </button>
        </div>
      </article>
    </div>

    <div v-else class="empty-panel">
      <h3>还没有本机数据源</h3>
      <p>导入 Excel 或 CSV 后，系统会在本机生成可查询数据，下次打开不用重新上传。</p>
      <div class="action-row">
        <button class="primary-button" type="button" @click="emit('open-import')">
          导入表格
        </button>
        <button class="secondary-button" type="button" @click="emit('open-settings')">
          配置 LLM
        </button>
      </div>
    </div>
  </section>
</template>
```

- [ ] **Step 2: 实现设置页**

Create `frontend-user/src/pages/SettingsPage.vue`:

```vue
<script setup>
import { reactive, ref, watchEffect } from 'vue';
import { saveLlmSettings } from '../api/settings.js';

const props = defineProps({
  settings: {
    type: Object,
    default: () => ({}),
  },
});
const emit = defineEmits(['saved', 'back']);

const form = reactive({
  enabled: false,
  provider: 'deepseek',
  model: 'deepseek-chat',
  api_url: 'https://api.deepseek.com/chat/completions',
  api_key: '',
});
const saving = ref(false);
const error = ref('');

watchEffect(() => {
  form.enabled = Boolean(props.settings.enabled);
  form.provider = props.settings.provider || 'deepseek';
  form.model = props.settings.model || 'deepseek-chat';
  form.api_url = props.settings.api_url || 'https://api.deepseek.com/chat/completions';
});

async function save() {
  saving.value = true;
  error.value = '';
  try {
    const payload = await saveLlmSettings({ ...form });
    form.api_key = '';
    emit('saved', payload);
  } catch (exc) {
    error.value = exc.message || '保存失败，请检查配置。';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="page-section narrow-section">
    <button class="secondary-button" type="button" @click="emit('back')">返回</button>
    <h2>LLM 设置</h2>
    <p>密钥保存在本机。页面只显示是否已配置，不回显明文。</p>
    <form class="form-stack" @submit.prevent="save">
      <label>
        <span>启用 LLM</span>
        <input v-model="form.enabled" type="checkbox" />
      </label>
      <label>
        <span>Provider</span>
        <input v-model="form.provider" type="text" autocomplete="off" />
      </label>
      <label>
        <span>Model</span>
        <input v-model="form.model" type="text" autocomplete="off" />
      </label>
      <label>
        <span>API URL</span>
        <input v-model="form.api_url" type="url" autocomplete="off" />
      </label>
      <label>
        <span>API key</span>
        <input v-model="form.api_key" type="password" autocomplete="off" />
      </label>
      <p class="state-line">
        当前状态：{{ settings.api_key_configured ? '已配置' : '未配置' }}
      </p>
      <p v-if="error" class="error-line">{{ error }}</p>
      <button class="primary-button" type="submit" :disabled="saving">
        {{ saving ? '保存中' : '保存设置' }}
      </button>
    </form>
  </section>
</template>
```

- [ ] **Step 3: 接入 App 状态**

Replace `frontend-user/src/App.vue` with:

```vue
<script setup>
import { onMounted, ref } from 'vue';
import { listDatasets } from './api/datasets.js';
import { getLlmSettings } from './api/settings.js';
import DatasetLibrary from './pages/DatasetLibrary.vue';
import SettingsPage from './pages/SettingsPage.vue';

const view = ref('library');
const datasets = ref([]);
const settings = ref({});
const loading = ref(false);
const error = ref('');
const selectedDatasetId = ref('');

onMounted(refresh);

async function refresh() {
  loading.value = true;
  error.value = '';
  try {
    const [datasetPayload, settingsPayload] = await Promise.all([
      listDatasets(),
      getLlmSettings().catch(() => ({})),
    ]);
    datasets.value = datasetPayload.datasets || [];
    settings.value = settingsPayload;
  } catch (exc) {
    error.value = exc.message || '读取本机数据源失败。';
  } finally {
    loading.value = false;
  }
}

function openDataset(datasetId) {
  selectedDatasetId.value = datasetId;
  view.value = 'detail';
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="kicker">本机数据</p>
        <h1>本地招生数据工作台</h1>
      </div>
      <button class="secondary-button" type="button" @click="view = 'settings'">
        设置
      </button>
    </header>

    <DatasetLibrary
      v-if="view === 'library'"
      :datasets="datasets"
      :loading="loading"
      :error="error"
      @open-dataset="openDataset"
      @open-import="view = 'import'"
      @open-settings="view = 'settings'"
    />
    <SettingsPage
      v-else-if="view === 'settings'"
      :settings="settings"
      @saved="(payload) => { settings = payload; view = 'library'; }"
      @back="view = 'library'"
    />
    <section v-else class="page-section">
      <button class="secondary-button" type="button" @click="view = 'library'">
        返回
      </button>
      <h2>数据源详情</h2>
      <p>当前数据源：{{ selectedDatasetId }}</p>
    </section>
  </main>
</template>
```

- [ ] **Step 4: 补 CSS**

Append to `frontend-user/src/styles/tokens.css`:

```css
.page-section {
  display: grid;
  gap: 16px;
}

.section-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.dataset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

.dataset-card {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-elevated);
}

.status-strip {
  height: 6px;
  background: var(--review);
}

.status-strip[data-status="queryable"] {
  background: var(--accent);
}

.dataset-card-body {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.dataset-card-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0;
}

.metric-grid div {
  border-radius: var(--radius);
  background: var(--surface);
  padding: 10px;
}

.metric-grid dt {
  color: var(--text-muted);
  font-size: 12px;
}

.metric-grid dd {
  margin: 3px 0 0;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.full-width {
  width: 100%;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.narrow-section {
  max-width: 720px;
}

.form-stack {
  display: grid;
  gap: 14px;
}

.form-stack label {
  display: grid;
  gap: 6px;
  font-weight: 700;
}

.form-stack input:not([type="checkbox"]) {
  min-height: 44px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0 12px;
}

.state-line {
  color: var(--text-muted);
}

.error-line {
  color: var(--danger);
  font-weight: 700;
}

@media (max-width: 700px) {
  .app-shell {
    width: min(100vw - 20px, 1180px);
    padding-top: 12px;
  }

  .topbar,
  .section-heading {
    align-items: stretch;
    flex-direction: column;
  }
}
```

- [ ] **Step 5: 构建验证**

Run:

```bash
cd frontend-user && npm run build
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add frontend-user/src/App.vue frontend-user/src/pages frontend-user/src/styles/tokens.css
git commit -m "feat: add local dataset library"
```

## Task 6: 导入流程和 schema 驱动查询页

**Files:**
- Create: `frontend-user/src/components/ImportPanel.vue`
- Create: `frontend-user/src/components/QueryComposer.vue`
- Create: `frontend-user/src/components/EvidenceSummary.vue`
- Create: `frontend-user/src/pages/DatasetDetail.vue`
- Modify: `frontend-user/src/App.vue`

- [ ] **Step 1: 创建导入面板**

Create `frontend-user/src/components/ImportPanel.vue`:

```vue
<script setup>
import { ref } from 'vue';
import {
  approveDomain,
  buildWarehouse,
  generateDomainPack,
  uploadDataset,
} from '../api/datasets.js';

const emit = defineEmits(['done', 'cancel']);
const file = ref(null);
const busy = ref(false);
const error = ref('');
const steps = ref([]);

function setFile(event) {
  file.value = event.target.files?.[0] || null;
}

async function runImport() {
  if (!file.value) {
    error.value = '请选择 Excel 或 CSV 文件。';
    return;
  }
  busy.value = true;
  error.value = '';
  steps.value = [];
  try {
    const uploaded = await recordStep('保存文件', () => uploadDataset({ file: file.value }));
    await recordStep('检查字段', () => generateDomainPack(uploaded.dataset_id, { llm: 'off' }));
    await recordStep('批准本机数据源', () => approveDomain(uploaded.dataset_id));
    const built = await recordStep('生成可查询数据', () => buildWarehouse(uploaded.dataset_id));
    emit('done', built);
  } catch (exc) {
    error.value = exc.message || '导入失败。';
  } finally {
    busy.value = false;
  }
}

async function recordStep(label, action) {
  steps.value.push({ label, status: 'running' });
  const index = steps.value.length - 1;
  try {
    const result = await action();
    steps.value[index] = { label, status: 'done' };
    return result;
  } catch (exc) {
    steps.value[index] = { label, status: 'error' };
    throw exc;
  }
}
</script>

<template>
  <section class="page-section narrow-section">
    <button class="secondary-button" type="button" @click="emit('cancel')">返回</button>
    <h2>导入表格</h2>
    <p>系统会在本机保存表格，并生成可查询数据源。</p>
    <label class="file-picker">
      <span>Excel 或 CSV 文件</span>
      <input type="file" accept=".xlsx,.xls,.xlsm,.csv" @change="setFile" />
    </label>
    <button class="primary-button" type="button" :disabled="busy" @click="runImport">
      {{ busy ? '导入中' : '开始导入' }}
    </button>
    <ol class="step-list">
      <li v-for="step in steps" :key="step.label">{{ step.label }}：{{ step.status }}</li>
    </ol>
    <p v-if="error" class="error-line">{{ error }}</p>
  </section>
</template>
```

- [ ] **Step 2: 创建查询组件**

Create `frontend-user/src/components/QueryComposer.vue`:

```vue
<script setup>
import { computed, reactive } from 'vue';
import { buildQueryControls, summarizeDatasetCapability } from '../domain/queryOptions.js';

const props = defineProps({
  profile: {
    type: Object,
    required: true,
  },
  running: Boolean,
});
const emit = defineEmits(['submit']);

const prompt = defineModel('prompt', { default: '' });
const userContext = reactive({});
const controls = computed(() => buildQueryControls(props.profile.semantic_query_options || {}));
const summary = computed(() => summarizeDatasetCapability(props.profile));

function submit() {
  emit('submit', {
    user_input: prompt.value,
    hard_filters: {},
    soft_preferences: {
      user_context: { ...userContext },
    },
  });
}
</script>

<template>
  <section class="query-panel">
    <div class="status-strip" :data-status="summary.capabilityLevel"></div>
    <div class="query-panel-body">
      <div>
        <h2>你想怎么查？</h2>
        <p>{{ summary.label }}</p>
      </div>
      <div class="required-grid" v-if="controls.requiredInputs.length">
        <label v-for="input in controls.requiredInputs" :key="input.id">
          <span>{{ input.label }}</span>
          <input v-model="userContext[input.id]" :type="input.type" />
        </label>
      </div>
      <label class="prompt-box">
        <span>一句话描述需求</span>
        <textarea
          v-model="prompt"
          rows="5"
          placeholder="例如：想读计算机，优先广州或深圳，学费两万以内"
        ></textarea>
      </label>
      <div class="field-summary">
        <p>可筛字段：{{ controls.filters.length }}</p>
        <p>可排序字段：{{ controls.sortFields.length }}</p>
      </div>
      <button class="primary-button" type="button" :disabled="running" @click="submit">
        {{ running ? '处理中' : '查询前检查' }}
      </button>
    </div>
  </section>
</template>
```

- [ ] **Step 3: 创建证据摘要**

Create `frontend-user/src/components/EvidenceSummary.vue`:

```vue
<script setup>
defineProps({
  result: {
    type: Object,
    default: null,
  },
});
</script>

<template>
  <section v-if="result" class="evidence-panel">
    <h2>本次结果</h2>
    <dl class="metric-grid">
      <div>
        <dt>状态</dt>
        <dd>{{ result.status }}</dd>
      </div>
      <div>
        <dt>结果数</dt>
        <dd>{{ result.result_count ?? 0 }}</dd>
      </div>
      <div>
        <dt>未执行偏好</dt>
        <dd>{{ result.not_executed_preferences?.length ?? 0 }}</dd>
      </div>
    </dl>
    <div v-if="result.items?.length" class="result-list">
      <article v-for="item in result.items.slice(0, 5)" :key="item.row_id || item.id" class="result-item">
        <pre>{{ JSON.stringify(item, null, 2) }}</pre>
      </article>
    </div>
  </section>
</template>
```

- [ ] **Step 4: 创建详情页**

Create `frontend-user/src/pages/DatasetDetail.vue`:

```vue
<script setup>
import { onMounted, ref } from 'vue';
import { datasetProfile } from '../api/datasets.js';
import { requestJson } from '../api/client.js';
import EvidenceSummary from '../components/EvidenceSummary.vue';
import QueryComposer from '../components/QueryComposer.vue';

const props = defineProps({
  datasetId: {
    type: String,
    required: true,
  },
});
const emit = defineEmits(['back']);

const profile = ref(null);
const result = ref(null);
const prompt = ref('');
const loading = ref(false);
const running = ref(false);
const error = ref('');

onMounted(loadProfile);

async function loadProfile() {
  loading.value = true;
  error.value = '';
  try {
    profile.value = await datasetProfile(props.datasetId);
  } catch (exc) {
    error.value = exc.message || '读取数据源能力失败。';
  } finally {
    loading.value = false;
  }
}

async function runPreflight(payload) {
  running.value = true;
  error.value = '';
  try {
    const domainName = profile.value?.domain_name;
    if (!domainName) {
      throw new Error('数据源缺少已审查 domain，无法查询。');
    }
    result.value = await requestJson('/workbench/preflight', {
      method: 'POST',
      body: JSON.stringify({
        dataset_id: props.datasetId,
        domain_name: domainName,
        user_input: payload.user_input || prompt.value || '查询',
        hard_filters: payload.hard_filters || {},
        soft_preferences: payload.soft_preferences || {},
        planner_mode: 'auto',
      }),
    });
  } catch (exc) {
    error.value = exc.message || '查询前检查失败。';
  } finally {
    running.value = false;
  }
}
</script>

<template>
  <section class="page-section">
    <button class="secondary-button" type="button" @click="emit('back')">返回数据源</button>
    <p v-if="loading" class="state-line">正在读取能力摘要...</p>
    <p v-else-if="error" class="error-line">{{ error }}</p>
    <template v-else-if="profile">
      <QueryComposer v-model:prompt="prompt" :profile="profile" :running="running" @submit="runPreflight" />
      <EvidenceSummary :result="result" />
    </template>
  </section>
</template>
```

- [ ] **Step 5: 接入 App**

Modify `frontend-user/src/App.vue` imports:

```js
import DatasetDetail from './pages/DatasetDetail.vue';
import ImportPanel from './components/ImportPanel.vue';
```

Replace placeholder `detail` section with:

```vue
    <DatasetDetail
      v-else-if="view === 'detail'"
      :dataset-id="selectedDatasetId"
      @back="view = 'library'"
    />
    <ImportPanel
      v-else-if="view === 'import'"
      @done="() => { view = 'library'; refresh(); }"
      @cancel="view = 'library'"
    />
```

- [ ] **Step 6: 补 CSS**

Append to `frontend-user/src/styles/tokens.css`:

```css
.query-panel,
.evidence-panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-elevated);
}

.query-panel-body,
.evidence-panel {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.required-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.required-grid label,
.prompt-box,
.file-picker {
  display: grid;
  gap: 6px;
  font-weight: 700;
}

.prompt-box textarea {
  resize: vertical;
  min-height: 110px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
}

.field-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--text-muted);
}

.step-list {
  margin: 0;
  padding-left: 20px;
}

.result-list {
  display: grid;
  gap: 10px;
}

.result-item {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  padding: 12px;
}
```

- [ ] **Step 7: 构建验证**

Run:

```bash
cd frontend-user && npm run test:unit && npm run build
```

Expected: PASS.

- [ ] **Step 8: 提交**

```bash
git add frontend-user/src
git commit -m "feat: add schema driven query flow"
```

## Task 7: 发行模式和静态托管

**Files:**
- Modify: `src/api/server.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_server_deployment.py`

- [ ] **Step 1: 写发行模式测试**

Append to `tests/test_server_deployment.py`:

```python
    def test_distribution_mode_status(self) -> None:
        with patch.dict(os.environ, {"APP_DISTRIBUTION_MODE": "user_upload_only"}, clear=False):
            response = self.client.get("/version")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["distribution_mode"], "user_upload_only")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
.venv/bin/python -m unittest tests.test_server_deployment.ServerDeploymentTest.test_distribution_mode_status
```

Expected: FAIL，`distribution_mode` 不存在。

- [ ] **Step 3: 添加 distribution mode 到 version**

Modify `src/api/server.py` `version()` return payload:

```python
        "distribution_mode": os.getenv("APP_DISTRIBUTION_MODE", "development"),
```

- [ ] **Step 4: 记录本地用户 Web 命令**

Append to `README.md` in the quick-start or commands section:

```markdown
## 本地用户 Web

本地用户 Web 是独立于研发前端的用户入口，不加载旧 mock/demo 数据。启动后端后运行：

```bash
cd frontend-user
npm install
npm run dev
```

发行模式可设置：

```bash
APP_DISTRIBUTION_MODE=user_upload_only
```
```

- [ ] **Step 5: 运行验证**

Run:

```bash
.venv/bin/python -m unittest tests.test_server_deployment.ServerDeploymentTest.test_distribution_mode_status
git diff --check
```

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add src/api/server.py .env.example README.md tests/test_server_deployment.py
git commit -m "docs: document local user web mode"
```

## Task 8: 全量验证和收尾

**Files:**
- Modify as needed: `frontend-user/README.md`
- Inspect: `docs/superpowers/specs/2026-06-27-local-user-web-design.md`

- [ ] **Step 1: 运行后端单元测试**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: OK. If this fails because `.venv` is missing, run `make bootstrap` first.

- [ ] **Step 2: 运行前端验证**

Run:

```bash
cd frontend-user && npm run test:unit && npm run build
```

Expected: PASS.

- [ ] **Step 3: 检查发行包没有引用旧 mock**

Run:

```bash
rg -n "demo_run|BUILTIN_ADMISSIONS_SOURCE|admissions_schema_v1" frontend-user
rg -n "mock" frontend-user/src
```

Expected: no matches. `frontend-user/README.md` may mention mock only when describing the old frontend boundary.

- [ ] **Step 4: 检查文档和空白**

Run:

```bash
git diff --check
rg -n "frontend-user|APP_DISTRIBUTION_MODE|LOCAL_SETTINGS_PATH" README.md .env.example docs/superpowers/specs/2026-06-27-local-user-web-design.md
```

Expected: `git diff --check` exits 0 and all new public behavior has matching docs.

- [ ] **Step 5: 手动浏览器 smoke**

Run backend:

```bash
AUTH_TOKENS_JSON='{"operator-token":{"actor_id":"operator","permission_scopes":["read_only","query","confirm","dataset_write","review_admin","warehouse_admin","diagnostics"]}}' .venv/bin/python -m uvicorn src.api.server:app --port 8001
```

Run frontend:

```bash
cd frontend-user && npm run dev
```

Open `http://127.0.0.1:5173` and check:

- Empty library renders without horizontal scroll at 375px.
- Settings page saves an LLM key and never displays the key.
- Import page accepts a small CSV fixture.
- Dataset detail page shows query controls from `semantic_query_options`.
- No UI text exposes `admissions_schema_v1`.

- [ ] **Step 6: Final commit if docs changed**

```bash
git status --short
git add frontend-user/README.md README.md .env.example docs/superpowers/specs/2026-06-27-local-user-web-design.md
git commit -m "docs: finish local user web notes"
```

Only run this commit if Step 4 or Step 5 produced documentation edits.

## Self-Review

- Spec coverage: dataset list, LLM settings, capability-driven UI, no frontend template branch, import flow, query flow, privacy exclusions, tests, and browser smoke are covered.
- Placeholder scan: no task uses “TBD”, “TODO”, “implement later”, or unbounded “add tests” wording.
- Type consistency: backend fields use `capability_level`, `recommendation_readiness`, `semantic_query_options`, `required_user_context`, `filters`, and `sort_fields` consistently. Frontend code never branches on `domain_template_id` or `admissions_schema_v1`.
