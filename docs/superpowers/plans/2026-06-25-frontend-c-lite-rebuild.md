# 前端 C-lite 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前端重构为 C-lite 架构：普通用户一键导入 uploaded admissions，主查询页左输入右查询前检查，字段审查和证据调试从普通路径移出。

**Architecture:** 保留现有 API 请求、状态归一化和结果展示工具，重写页面壳和主要工作区组件。新增 `domain adapters` 和 `data source registry`，让 admissions 作为第一版唯一 adapter 存在，但不把模板 ID、预检规则和结果渲染逻辑散落在页面组件里。

**Tech Stack:** Vue 3 SFC、Vite、Element Plus、Node.js `node --test`、现有 `/workbench/query`、`/workbench/preflight`、`/datasets/*` API。

---

## 文件结构

- Create: `frontend/src/domain/admissionsAdapter.js`
  - admissions 领域配置、内置数据源、上传数据源归一化、是否需要查询前检查。
- Create: `frontend/src/domain/admissionsAdapter.test.js`
  - 验证 uploaded admissions 才启用 preflight，内置数据源不带 `dataset_id`，上传源标签和行列数归一化稳定。
- Create: `frontend/src/utils/dataSourceRegistry.js`
  - localStorage 读写、选中数据源持久化、上传源列表合并。
- Create: `frontend/src/utils/dataSourceRegistry.test.js`
  - 验证坏 JSON 返回空列表、无效选中值回退内置源、重复上传源被替换并置顶。
- Create: `frontend/src/components/workspaces/QueryWorkspace.vue`
  - 主查询工作区。负责运行条、左侧输入、右侧 preflight/result 切换、候选确认和证据摘要入口。
- Create: `frontend/src/components/workspaces/ImportWorkspace.vue`
  - 普通一键导入工作区。负责上传文件、串行导入流水线、失败步骤详情、成功后发出 `source-ready`。
- Create: `frontend/src/components/workspaces/ReviewWorkspace.vue`
  - 高级字段审查工作区。第一版展示字段摘要、采用模板、建仓和开发者调试折叠区。
- Create: `frontend/src/components/workspaces/EvidenceDebugWorkspace.vue`
  - 证据调试工作区。展示响应、证据、trace、上传审计，不出现在普通查询首屏。
- Create: `frontend/src/components/upload/ImportStepList.vue`
  - 一键导入步骤列表，使用中文步骤名和状态。
- Create: `frontend/src/components/upload/importPipeline.js`
  - 一键导入 API 编排函数，便于单元测试。
- Create: `frontend/src/components/upload/importPipeline.test.js`
  - 使用 fake request 函数验证 API 顺序、失败时停止、成功时返回 source payload。
- Modify: `frontend/src/App.vue`
  - 只保留应用壳、工作区导航、全局状态和数据源注册，不再直接承载三列查询、上传审查和细节区。
- Modify: `frontend/src/components/PreflightPanel.vue`
  - 强化四区块展示：已识别事实、需要你确认、不会参与筛选、还缺少信息；隐藏技术 ID。
- Modify: `frontend/src/components/ResultTable.vue`
  - 保持现有结果卡片，增加专业组明细 section 的兼容渲染。
- Modify: `frontend/src/style.css`
  - 删除三栏工作台依赖样式，新增 C-lite app shell、双栏查询、导入页和调试页样式。
- Modify: `frontend/README.md`
  - 用中文记录 C-lite 前端结构、普通导入路径、preflight 查询路径和测试命令。

## Task 1: 抽出 admissions adapter 和数据源注册

**Files:**
- Create: `frontend/src/domain/admissionsAdapter.js`
- Create: `frontend/src/domain/admissionsAdapter.test.js`
- Create: `frontend/src/utils/dataSourceRegistry.js`
- Create: `frontend/src/utils/dataSourceRegistry.test.js`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 写 admissions adapter 测试**

Create `frontend/src/domain/admissionsAdapter.test.js`:

```js
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ADMISSIONS_DOMAIN,
  BUILTIN_ADMISSIONS_SOURCE,
  createUploadedAdmissionsSource,
  shouldUseUploadedAdmissionsPreflight,
} from './admissionsAdapter.js';

test('admissions domain centralizes reviewed template settings', () => {
  assert.equal(ADMISSIONS_DOMAIN.domainName, 'admissions');
  assert.equal(ADMISSIONS_DOMAIN.templateId, 'admissions_schema_v1');
  assert.equal(ADMISSIONS_DOMAIN.supportsPreflight, true);
  assert.equal(ADMISSIONS_DOMAIN.resultRenderer, 'admissions');
});

test('builtin admissions source is not treated as uploaded dataset', () => {
  assert.equal(BUILTIN_ADMISSIONS_SOURCE.id, 'builtin_admissions');
  assert.equal(BUILTIN_ADMISSIONS_SOURCE.type, 'builtin');
  assert.equal(BUILTIN_ADMISSIONS_SOURCE.datasetId, null);
  assert.equal(shouldUseUploadedAdmissionsPreflight(BUILTIN_ADMISSIONS_SOURCE, 'api'), false);
});

test('uploaded admissions source normalizes warehouse metadata', () => {
  const source = createUploadedAdmissionsSource({
    dataset_id: 'ds_1',
    domain_name: 'admissions',
    file_name: '录取表.xlsx',
    warehouse: { row_count: 1200, column_count: 27 },
    updated_at: '2026-06-25T06:30:00.000Z',
  });

  assert.equal(source.id, 'uploaded:ds_1');
  assert.equal(source.type, 'uploaded');
  assert.equal(source.datasetId, 'ds_1');
  assert.equal(source.domainName, 'admissions');
  assert.equal(source.label, '上传：录取表.xlsx');
  assert.equal(source.description, '1,200 行，27 列，使用上传表格查询。');
  assert.equal(source.updatedAt, '2026-06-25T06:30:00.000Z');
});

test('uploaded admissions preflight only applies in API mode', () => {
  const source = createUploadedAdmissionsSource({
    dataset_id: 'ds_1',
    domain_name: 'admissions',
    source_name: '录取表.xlsx',
  });

  assert.equal(shouldUseUploadedAdmissionsPreflight(source, 'api'), true);
  assert.equal(shouldUseUploadedAdmissionsPreflight(source, 'demo'), false);
  assert.equal(shouldUseUploadedAdmissionsPreflight({ ...source, domainName: 'other' }, 'api'), false);
});
```

- [ ] **Step 2: 运行 adapter 测试确认失败**

Run:

```bash
cd frontend && npm run test:unit -- src/domain/admissionsAdapter.test.js
```

Expected: FAIL，错误包含 `Cannot find module` 或导出函数不存在。

- [ ] **Step 3: 实现 admissions adapter**

Create `frontend/src/domain/admissionsAdapter.js`:

```js
export const ADMISSIONS_DOMAIN = {
  domainName: 'admissions',
  label: '招生录取数据',
  uploadMode: 'one_click_template',
  templateId: 'admissions_schema_v1',
  supportsPreflight: true,
  resultRenderer: 'admissions',
  requiredUserInputs: ['source_province', 'subject_type', 'user_rank'],
};

export const BUILTIN_ADMISSIONS_SOURCE = {
  id: 'builtin_admissions',
  type: 'builtin',
  datasetId: null,
  domainName: ADMISSIONS_DOMAIN.domainName,
  label: '内置招生数据',
  description: '使用仓库内置 admissions 数据。',
};

export function createUploadedAdmissionsSource(payload = {}) {
  const datasetId = payload.dataset_id || payload.datasetId;
  if (!datasetId) {
    return null;
  }
  const rowCount = payload.warehouse?.row_count || payload.row_count || payload.rowCount || null;
  const columnCount = payload.warehouse?.column_count || payload.column_count || payload.columnCount || null;
  const fileName = payload.file_name || payload.source_name || payload.fileName || datasetId;
  const sizeText = rowCount && columnCount
    ? `${formatNumber(rowCount)} 行，${formatNumber(columnCount)} 列`
    : '已生成可查询数据';

  return {
    id: `uploaded:${datasetId}`,
    type: 'uploaded',
    datasetId,
    domainName: payload.domain_name || payload.domainName || ADMISSIONS_DOMAIN.domainName,
    label: `上传：${fileName}`,
    description: `${sizeText}，使用上传表格查询。`,
    rowCount,
    columnCount,
    updatedAt: payload.updated_at || payload.updatedAt || new Date().toISOString(),
  };
}

export function shouldUseUploadedAdmissionsPreflight(source, mode) {
  return mode === 'api'
    && source?.type === 'uploaded'
    && Boolean(source?.datasetId)
    && source?.domainName === ADMISSIONS_DOMAIN.domainName
    && ADMISSIONS_DOMAIN.supportsPreflight;
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isNaN(number) ? value : number.toLocaleString('zh-CN');
}
```

- [ ] **Step 4: 运行 adapter 测试确认通过**

Run:

```bash
cd frontend && npm run test:unit -- src/domain/admissionsAdapter.test.js
```

Expected: PASS。

- [ ] **Step 5: 写数据源注册测试**

Create `frontend/src/utils/dataSourceRegistry.test.js`:

```js
import assert from 'node:assert/strict';
import test from 'node:test';

import { BUILTIN_ADMISSIONS_SOURCE, createUploadedAdmissionsSource } from '../domain/admissionsAdapter.js';
import {
  DATA_SOURCES_STORAGE_KEY,
  SELECTED_SOURCE_STORAGE_KEY,
  loadSelectedDataSourceId,
  loadUploadedDataSources,
  mergeUploadedDataSource,
  persistSelectedDataSourceId,
  persistUploadedDataSources,
} from './dataSourceRegistry.js';

function memoryStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: (key) => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
  };
}

test('loadUploadedDataSources ignores malformed storage', () => {
  const storage = memoryStorage({ [DATA_SOURCES_STORAGE_KEY]: '{bad json' });
  assert.deepEqual(loadUploadedDataSources(storage), []);
});

test('loadSelectedDataSourceId falls back to builtin for stale selection', () => {
  const sources = [createUploadedAdmissionsSource({ dataset_id: 'ds_1' })];
  const storage = memoryStorage({ [SELECTED_SOURCE_STORAGE_KEY]: 'uploaded:missing' });
  assert.equal(loadSelectedDataSourceId(storage, sources), BUILTIN_ADMISSIONS_SOURCE.id);
});

test('mergeUploadedDataSource replaces same id and keeps newest first', () => {
  const oldSource = createUploadedAdmissionsSource({ dataset_id: 'ds_old' });
  const first = createUploadedAdmissionsSource({ dataset_id: 'ds_1', file_name: 'old.xlsx' });
  const updated = createUploadedAdmissionsSource({ dataset_id: 'ds_1', file_name: 'new.xlsx' });

  const merged = mergeUploadedDataSource([oldSource, first], updated);

  assert.deepEqual(merged.map((item) => item.id), ['uploaded:ds_1', 'uploaded:ds_old']);
  assert.equal(merged[0].label, '上传：new.xlsx');
});

test('persist helpers write stable JSON and selected source id', () => {
  const storage = memoryStorage();
  const source = createUploadedAdmissionsSource({ dataset_id: 'ds_1' });

  persistUploadedDataSources(storage, [source]);
  persistSelectedDataSourceId(storage, source.id);

  assert.deepEqual(JSON.parse(storage.getItem(DATA_SOURCES_STORAGE_KEY)), [source]);
  assert.equal(storage.getItem(SELECTED_SOURCE_STORAGE_KEY), 'uploaded:ds_1');
});
```

- [ ] **Step 6: 运行数据源注册测试确认失败**

Run:

```bash
cd frontend && npm run test:unit -- src/utils/dataSourceRegistry.test.js
```

Expected: FAIL，错误包含 `Cannot find module`。

- [ ] **Step 7: 实现数据源注册工具**

Create `frontend/src/utils/dataSourceRegistry.js`:

```js
import { BUILTIN_ADMISSIONS_SOURCE } from '../domain/admissionsAdapter.js';

export const DATA_SOURCES_STORAGE_KEY = 'szu_uploaded_data_sources';
export const SELECTED_SOURCE_STORAGE_KEY = 'szu_selected_data_source';

export function browserStorage() {
  return typeof window === 'undefined' ? null : window.localStorage;
}

export function loadUploadedDataSources(storage = browserStorage()) {
  try {
    const raw = storage?.getItem(DATA_SOURCES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((source) => source?.id && source?.datasetId && source?.domainName)
      : [];
  } catch {
    return [];
  }
}

export function loadSelectedDataSourceId(storage = browserStorage(), sources = []) {
  const saved = storage?.getItem(SELECTED_SOURCE_STORAGE_KEY);
  if (
    saved === BUILTIN_ADMISSIONS_SOURCE.id
    || sources.some((source) => source.id === saved)
  ) {
    return saved;
  }
  return BUILTIN_ADMISSIONS_SOURCE.id;
}

export function mergeUploadedDataSource(currentSources, source, limit = 5) {
  if (!source?.id) {
    return [...(currentSources || [])];
  }
  return [
    source,
    ...(currentSources || []).filter((item) => item.id !== source.id),
  ].slice(0, limit);
}

export function persistUploadedDataSources(storage = browserStorage(), value = []) {
  storage?.setItem(DATA_SOURCES_STORAGE_KEY, JSON.stringify(value));
}

export function persistSelectedDataSourceId(storage = browserStorage(), value) {
  storage?.setItem(SELECTED_SOURCE_STORAGE_KEY, value || BUILTIN_ADMISSIONS_SOURCE.id);
}
```

- [ ] **Step 8: 运行新单元测试**

Run:

```bash
cd frontend && npm run test:unit -- src/domain/admissionsAdapter.test.js src/utils/dataSourceRegistry.test.js
```

Expected: PASS。

- [ ] **Step 9: 让 App 使用 adapter 和 registry**

Modify `frontend/src/App.vue`:

```js
import {
  BUILTIN_ADMISSIONS_SOURCE,
  createUploadedAdmissionsSource,
  shouldUseUploadedAdmissionsPreflight,
} from './domain/admissionsAdapter';
import {
  loadSelectedDataSourceId,
  loadUploadedDataSources,
  mergeUploadedDataSource,
  persistSelectedDataSourceId,
  persistUploadedDataSources,
} from './utils/dataSourceRegistry';
```

Replace local constants and functions:

```js
const BUILTIN_DATA_SOURCE = BUILTIN_ADMISSIONS_SOURCE;
const initialUploadedDataSources = loadUploadedDataSources();
const initialDataSourceId = loadSelectedDataSourceId(undefined, initialUploadedDataSources);
```

Replace `shouldUseUploadedPreflightForSource(source)` body:

```js
function shouldUseUploadedPreflightForSource(source) {
  return shouldUseUploadedAdmissionsPreflight(source, mode.value);
}
```

Replace `activateUploadedSource(payload)` body:

```js
function activateUploadedSource(payload) {
  const source = createUploadedAdmissionsSource(payload);
  if (!source) {
    return;
  }
  uploadedDataSources.value = mergeUploadedDataSource(uploadedDataSources.value, source);
  clearLastRequestContext();
  clearPreflightState();
  selectedDataSourceId.value = source.id;
  mode.value = 'api';
  activeWorkspace.value = 'query';
  apiError.value = '';
  lastRunFailed.value = false;
}
```

Delete the local functions from `App.vue`:

```text
loadUploadedDataSources
loadSelectedDataSourceId
persistUploadedDataSources
persistSelectedDataSourceId
normalizeUploadedDataSource
formatNumber
```

- [ ] **Step 10: 运行前端测试和构建**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: both PASS。

- [ ] **Step 11: Commit Task 1**

```bash
git add frontend/src/domain/admissionsAdapter.js frontend/src/domain/admissionsAdapter.test.js frontend/src/utils/dataSourceRegistry.js frontend/src/utils/dataSourceRegistry.test.js frontend/src/App.vue
git commit -m "refactor: centralize frontend admissions data sources"
```

## Task 2: 新建 C-lite 页面壳和工作区组件

**Files:**
- Create: `frontend/src/components/workspaces/QueryWorkspace.vue`
- Create: `frontend/src/components/workspaces/ImportWorkspace.vue`
- Create: `frontend/src/components/workspaces/ReviewWorkspace.vue`
- Create: `frontend/src/components/workspaces/EvidenceDebugWorkspace.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 创建 QueryWorkspace 组件骨架**

Create `frontend/src/components/workspaces/QueryWorkspace.vue`:

```vue
<script setup>
defineProps({
  runData: { type: Object, required: true },
  preflightState: { type: Object, required: true },
  workbenchOptions: { type: Object, required: true },
  mode: { type: String, required: true },
  extractor: { type: String, required: true },
  generator: { type: String, required: true },
  model: { type: String, required: true },
  loading: { type: Boolean, default: false },
  lastRunFailed: { type: Boolean, default: false },
  apiError: { type: String, default: '' },
  selectedDataSourceId: { type: String, required: true },
  dataSourceOptions: { type: Array, required: true },
  dataSourceTag: { type: Object, required: true },
  dataSourceDescription: { type: String, default: '' },
  optionsLoadError: { type: String, default: '' },
  runStatus: { type: Object, required: true },
  primaryRunLabel: { type: String, required: true },
  quickStats: { type: Array, required: true },
  resultRows: { type: Array, required: true },
  canConfirmCandidates: { type: Boolean, default: false },
  defaultHardFilters: { type: Object, required: true },
  defaultSoftPreferences: { type: Object, required: true },
});

const emit = defineEmits([
  'update:mode',
  'update:extractor',
  'update:generator',
  'update:model',
  'update:selected-data-source-id',
  'run-current-form',
  'show-demo',
  'go-import',
  'draft-change',
  'run-workbench',
  'update-preflight-selection',
  'confirm-candidates',
  'view-trace',
]);
</script>

<template>
  <section class="workspace-panel query-workspace c-lite-query">
    <slot />
  </section>
</template>
```

- [ ] **Step 2: 创建 ImportWorkspace 组件骨架**

Create `frontend/src/components/workspaces/ImportWorkspace.vue`:

```vue
<script setup>
defineProps({
  activeSource: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['source-ready', 'open-review']);
</script>

<template>
  <section class="workspace-panel single-scroll import-workspace">
    <slot :emit-source-ready="(payload) => emit('source-ready', payload)" />
  </section>
</template>
```

- [ ] **Step 3: 创建 ReviewWorkspace 组件骨架**

Create `frontend/src/components/workspaces/ReviewWorkspace.vue`:

```vue
<script setup>
defineProps({
  selectedDataSource: {
    type: Object,
    default: null,
  },
});
</script>

<template>
  <section class="workspace-panel single-scroll review-workspace">
    <el-card class="workbench-card" shadow="never">
      <template #header>
        <div class="card-header">
          <h2>字段审查</h2>
          <el-tag effect="plain">高级</el-tag>
        </div>
      </template>
      <p class="beginner-empty">字段映射不匹配时，从导入数据页进入这里处理。</p>
      <p v-if="selectedDataSource" class="beginner-empty">
        当前数据源：{{ selectedDataSource.label }}
      </p>
    </el-card>
  </section>
</template>
```

- [ ] **Step 4: 创建 EvidenceDebugWorkspace 组件骨架**

Create `frontend/src/components/workspaces/EvidenceDebugWorkspace.vue`:

```vue
<script setup>
import CandidateConfirmation from '../CandidateConfirmation.vue';
import ExtractedPreferences from '../ExtractedPreferences.vue';
import RuleSummaryCards from '../RuleSummaryCards.vue';
import VerificationAudit from '../VerificationAudit.vue';

defineProps({
  runData: {
    type: Object,
    required: true,
  },
});
</script>

<template>
  <section class="workspace-panel detail-workspace evidence-debug-workspace">
    <RuleSummaryCards
      :deterministic-rules="runData?.deterministic_rules || []"
      :candidate-rules="runData?.candidate_rules || []"
      :not-executed-preferences="runData?.not_executed_preferences || []"
      :executable-rules="runData?.executable_rules || []"
    />
    <CandidateConfirmation
      :candidate-rules="runData?.candidate_rules || []"
      :confirmations="runData?.simulated_confirmations || {}"
    />
    <ExtractedPreferences :preferences="runData?.extracted_preferences || []" />
    <VerificationAudit
      :grounding="runData?.attribute_grounding || {}"
      :proposed-rules="runData?.proposed_rules || []"
    />
  </section>
</template>
```

- [ ] **Step 5: 先接入工作区组件但保留旧内容**

Modify `frontend/src/App.vue` imports:

```js
import QueryWorkspace from './components/workspaces/QueryWorkspace.vue';
import ImportWorkspace from './components/workspaces/ImportWorkspace.vue';
import ReviewWorkspace from './components/workspaces/ReviewWorkspace.vue';
import EvidenceDebugWorkspace from './components/workspaces/EvidenceDebugWorkspace.vue';
```

Change tabs labels:

```vue
<el-tab-pane label="查询" name="query">
  <QueryWorkspace
    :run-data="runData"
    :preflight-state="preflightState"
    :workbench-options="workbenchOptions"
    :mode="mode"
    :extractor="extractor"
    :generator="generator"
    :model="model"
    :loading="loading"
    :last-run-failed="lastRunFailed"
    :api-error="apiError"
    :selected-data-source-id="selectedDataSourceId"
    :data-source-options="dataSourceOptions"
    :data-source-tag="dataSourceTag"
    :data-source-description="dataSourceDescription"
    :options-load-error="optionsLoadError"
    :run-status="displayedRunBarStatus"
    :primary-run-label="primaryRunLabel"
    :quick-stats="quickStats"
    :result-rows="resultRows"
    :can-confirm-candidates="canConfirmCandidates"
    :default-hard-filters="defaultHardFilters"
    :default-soft-preferences="defaultSoftPreferences"
  >
    <!-- temporarily keep existing query markup here until Task 3 moves it into QueryWorkspace -->
  </QueryWorkspace>
</el-tab-pane>

<el-tab-pane label="导入数据" name="dataset">
  <ImportWorkspace :active-source="selectedDataSource" @source-ready="activateUploadedSource" @open-review="activeWorkspace = 'review'">
    <DatasetIngestionPanel @source-ready="activateUploadedSource" />
  </ImportWorkspace>
</el-tab-pane>

<el-tab-pane label="字段审查" name="review">
  <ReviewWorkspace :selected-data-source="selectedDataSource" />
</el-tab-pane>

<el-tab-pane label="证据调试" name="details">
  <EvidenceDebugWorkspace :run-data="runData" />
</el-tab-pane>
```

- [ ] **Step 6: 调整全局壳样式**

Modify `frontend/src/style.css`:

```css
.app-shell {
  display: flex;
  flex-direction: column;
  width: min(1440px, calc(100% - 24px));
  min-height: 100dvh;
  height: auto;
  margin: 0 auto;
  padding: 12px 0 16px;
  overflow: visible;
}

.workspace-tabs,
.workspace-tabs > .el-tabs__content,
.workspace-tabs .el-tab-pane,
.workspace-panel {
  min-width: 0;
}

.c-lite-query {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
}

@media (max-width: 980px) {
  .app-shell {
    width: min(100% - 16px, 720px);
  }
}
```

- [ ] **Step 7: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 8: Commit Task 2**

```bash
git add frontend/src/components/workspaces frontend/src/App.vue frontend/src/style.css
git commit -m "refactor: add c-lite frontend workspaces"
```

## Task 3: 将主查询页迁入 QueryWorkspace

**Files:**
- Modify: `frontend/src/components/workspaces/QueryWorkspace.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 将查询页 imports 放入 QueryWorkspace**

Modify `frontend/src/components/workspaces/QueryWorkspace.vue`:

```js
import BeginnerDecisionPanel from '../BeginnerDecisionPanel.vue';
import CandidateRerunPanel from '../CandidateRerunPanel.vue';
import EvalSummary from '../EvalSummary.vue';
import EvidenceReport from '../EvidenceReport.vue';
import PreflightPanel from '../PreflightPanel.vue';
import ResultTable from '../ResultTable.vue';
import TokenUsagePanel from '../TokenUsagePanel.vue';
import UserInputPanel from '../UserInputPanel.vue';
import WorkbenchRunBar from '../WorkbenchRunBar.vue';
import { createEmptyEvidenceReport } from '../../utils/workbenchState.js';
import { shouldShowOptionsLoadError } from '../../utils/workbenchPresentation.js';
```

- [ ] **Step 2: 在 QueryWorkspace 内部创建表单 ref 和提交桥接**

Modify `frontend/src/components/workspaces/QueryWorkspace.vue`:

```js
import { ref } from 'vue';

const inputPanelRef = ref(null);

function submitCurrentForm() {
  inputPanelRef.value?.submitRun?.();
}
```

- [ ] **Step 3: 将查询模板移入 QueryWorkspace**

Replace the `<template>` in `frontend/src/components/workspaces/QueryWorkspace.vue`:

```vue
<template>
  <section class="workspace-panel c-lite-query">
    <WorkbenchRunBar
      :mode="mode"
      :extractor="extractor"
      :generator="generator"
      :model="model"
      :selected-data-source-id="selectedDataSourceId"
      :data-source-options="dataSourceOptions"
      :data-source-tag="dataSourceTag"
      :data-source-description="dataSourceDescription"
      :extractor-options="workbenchOptions.extractors"
      :generator-options="workbenchOptions.generators"
      :model-options="workbenchOptions.models"
      :options-source="workbenchOptions.source"
      :options-error="optionsLoadError"
      :run-status="runStatus"
      :loading="loading"
      :primary-action-label="primaryRunLabel"
      @update:mode="emit('update:mode', $event)"
      @update:extractor="emit('update:extractor', $event)"
      @update:generator="emit('update:generator', $event)"
      @update:model="emit('update:model', $event)"
      @update:selected-data-source-id="emit('update:selected-data-source-id', $event)"
      @run="submitCurrentForm"
      @demo="emit('show-demo')"
      @upload="emit('go-import')"
    />

    <div class="c-lite-query-grid">
      <aside class="query-input-panel">
        <UserInputPanel
          ref="inputPanelRef"
          :default-hard-filters="defaultHardFilters"
          :default-soft-preferences="defaultSoftPreferences"
          :mode="mode"
          :loading="loading"
          :show-panel-actions="false"
          :rank-window-options="workbenchOptions.rank_windows"
          :sort-mode-options="workbenchOptions.sort_modes"
          @draft-change="emit('draft-change', $event)"
          @run="emit('run-workbench', $event)"
        />
        <el-alert
          v-if="shouldShowOptionsLoadError(mode, optionsLoadError)"
          class="inline-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="optionsLoadError"
        />
        <el-alert
          v-if="apiError"
          class="inline-alert"
          type="error"
          :closable="false"
          show-icon
          :title="apiError"
        />
      </aside>

      <section class="query-output-panel">
        <template v-if="!lastRunFailed">
          <PreflightPanel
            :preflight="preflightState.response"
            :selections="preflightState.selections"
            @update-selection="emit('update-preflight-selection', $event)"
          />

          <div class="quick-stats">
            <article v-for="item in quickStats" :key="item.label" :class="['quick-stat', `tone-${item.tone}`]">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </article>
          </div>

          <CandidateRerunPanel
            :run-data="runData"
            :loading="loading"
            :can-confirm="canConfirmCandidates"
            @confirm="emit('confirm-candidates', $event)"
          />

          <ResultTable
            :results="resultRows"
            :total="runData?.result_count || 0"
            @view-trace="emit('view-trace', $event)"
          />

          <el-collapse class="query-evidence-collapse">
            <el-collapse-item title="筛选依据" name="evidence">
              <BeginnerDecisionPanel :run-data="runData" />
              <EvidenceReport :report="runData?.natural_language_report || createEmptyEvidenceReport()" />
            </el-collapse-item>
            <el-collapse-item title="运行摘要" name="audit">
              <EvalSummary :run-data="runData" />
              <TokenUsagePanel
                :token-usage="runData?.token_usage"
                :mode="mode"
                :selected-options="runData?.selected_options"
              />
            </el-collapse-item>
          </el-collapse>
        </template>

        <el-card v-else class="workbench-card empty-run" shadow="never">
          <el-empty description="这次没查成功">
            <p class="beginner-empty">{{ apiError }}</p>
          </el-empty>
        </el-card>
      </section>
    </div>
  </section>
</template>
```

- [ ] **Step 4: 在 App 中替换查询 tab 内容**

Modify `frontend/src/App.vue` query tab:

```vue
<el-tab-pane label="查询" name="query">
  <QueryWorkspace
    v-model:mode="mode"
    v-model:extractor="extractor"
    v-model:generator="generator"
    v-model:model="model"
    :run-data="runData"
    :preflight-state="preflightState"
    :workbench-options="workbenchOptions"
    :loading="loading"
    :last-run-failed="lastRunFailed"
    :api-error="apiError"
    :selected-data-source-id="selectedDataSourceId"
    :data-source-options="dataSourceOptions"
    :data-source-tag="dataSourceTag"
    :data-source-description="dataSourceDescription"
    :options-load-error="shouldShowOptionsLoadError(mode, optionsLoadError) ? optionsLoadError : ''"
    :run-status="displayedRunBarStatus"
    :primary-run-label="primaryRunLabel"
    :quick-stats="quickStats"
    :result-rows="resultRows"
    :can-confirm-candidates="canConfirmCandidates"
    :default-hard-filters="defaultHardFilters"
    :default-soft-preferences="defaultSoftPreferences"
    @update:selected-data-source-id="handleDataSourceChange"
    @show-demo="showDemoRun"
    @go-import="goToUpload"
    @draft-change="handleInputDraftChange"
    @run-workbench="runWorkbench"
    @update-preflight-selection="updatePreflightSelection"
    @confirm-candidates="rerunWithConfirmedCandidates"
    @view-trace="openTrace"
  />
</el-tab-pane>
```

Delete now-unused imports from `App.vue`:

```text
UserInputPanel
WorkbenchRunBar
PreflightPanel
CandidateRerunPanel
ResultTable
EvidenceReport
EvalSummary
TokenUsagePanel
BeginnerDecisionPanel
shouldShowOptionsLoadError
createEmptyEvidenceReport
inputPanelRef
submitCurrentForm
```

Keep `shouldShowOptionsLoadError` if App still uses it for the prop expression; remove only after the prop expression is simplified.

- [ ] **Step 5: 添加双栏查询样式**

Modify `frontend/src/style.css`:

```css
.c-lite-query-grid {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
}

.query-input-panel,
.query-output-panel {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 12px;
}

.query-output-panel {
  grid-auto-rows: max-content;
}

.query-evidence-collapse {
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #ffffff;
}

@media (max-width: 980px) {
  .c-lite-query-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: 运行测试和构建**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: both PASS。

- [ ] **Step 7: Commit Task 3**

```bash
git add frontend/src/components/workspaces/QueryWorkspace.vue frontend/src/App.vue frontend/src/style.css
git commit -m "refactor: move query flow into c-lite workspace"
```

## Task 4: 实现一键导入 pipeline 和普通导入页

**Files:**
- Create: `frontend/src/components/upload/importPipeline.js`
- Create: `frontend/src/components/upload/importPipeline.test.js`
- Create: `frontend/src/components/upload/ImportStepList.vue`
- Modify: `frontend/src/components/workspaces/ImportWorkspace.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 写 import pipeline 测试**

Create `frontend/src/components/upload/importPipeline.test.js`:

```js
import assert from 'node:assert/strict';
import test from 'node:test';

import { runAdmissionsImportPipeline } from './importPipeline.js';

function fakeFile(name = '录取表.xlsx') {
  return { name };
}

test('runAdmissionsImportPipeline calls dataset APIs in order', async () => {
  const calls = [];
  const requestJson = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body });
    if (url.startsWith('/datasets/upload')) {
      return { dataset_id: 'ds_1', source_name: '录取表.xlsx' };
    }
    if (url.endsWith('/generate-domain-pack')) {
      return { dataset_id: 'ds_1', domain_template_id: 'admissions_schema_v1' };
    }
    if (url.endsWith('/profile')) {
      return { fields: [] };
    }
    if (url.endsWith('/review-summary')) {
      return { reviewable_fields: [] };
    }
    if (url.endsWith('/approve-domain')) {
      return { ok: true, payload: { domain_pack_status: 'approved' } };
    }
    if (url.endsWith('/build-warehouse')) {
      return {
        dataset_id: 'ds_1',
        domain_name: 'admissions',
        status: 'queryable',
        source_name: '录取表.xlsx',
        warehouse: { row_count: 10, column_count: 4 },
      };
    }
    throw new Error(`unexpected url ${url}`);
  };

  const result = await runAdmissionsImportPipeline({
    file: fakeFile(),
    requestJson,
    onStep: () => {},
  });

  assert.deepEqual(calls.map((call) => call.url), [
    '/datasets/upload?filename=%E5%BD%95%E5%8F%96%E8%A1%A8.xlsx',
    '/datasets/ds_1/generate-domain-pack',
    '/datasets/ds_1/profile',
    '/datasets/ds_1/review-summary',
    '/datasets/ds_1/approve-domain',
    '/datasets/ds_1/build-warehouse',
  ]);
  assert.equal(result.dataset.dataset_id, 'ds_1');
  assert.equal(result.dataset.status, 'queryable');
});

test('runAdmissionsImportPipeline stops when approve-domain reports business failure', async () => {
  const visited = [];
  const requestJson = async (url) => {
    visited.push(url);
    if (url.startsWith('/datasets/upload')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/generate-domain-pack')) return { dataset_id: 'ds_1' };
    if (url.endsWith('/profile')) return {};
    if (url.endsWith('/review-summary')) return {};
    if (url.endsWith('/approve-domain')) {
      return { ok: false, payload: { failures: ['primary field 不存在：city'] } };
    }
    throw new Error('build warehouse must not run after failed approval');
  };

  await assert.rejects(
    () => runAdmissionsImportPipeline({ file: fakeFile(), requestJson, onStep: () => {} }),
    /字段模板审核未通过/,
  );
  assert.equal(visited.some((url) => url.endsWith('/build-warehouse')), false);
});
```

- [ ] **Step 2: 运行 pipeline 测试确认失败**

Run:

```bash
cd frontend && npm run test:unit -- src/components/upload/importPipeline.test.js
```

Expected: FAIL，错误包含 `Cannot find module`。

- [ ] **Step 3: 实现 import pipeline**

Create `frontend/src/components/upload/importPipeline.js`:

```js
import { ADMISSIONS_DOMAIN } from '../../domain/admissionsAdapter.js';
import {
  approvalFailureMessage,
  mergeApprovedDatasetState,
} from '../../utils/uploadDatasetState.js';

export const ADMISSIONS_IMPORT_STEPS = [
  { key: 'upload', label: '上传文件' },
  { key: 'domain_pack', label: '检查字段' },
  { key: 'profile', label: '读取表格结构' },
  { key: 'review_summary', label: '生成字段摘要' },
  { key: 'approve_domain', label: '确认字段模板' },
  { key: 'build_warehouse', label: '生成可查询数据' },
];

export async function runAdmissionsImportPipeline({ file, requestJson, onStep }) {
  if (!file) {
    throw new Error('请先选择 CSV 或 Excel 文件。');
  }
  const mark = (key, status, details = {}) => onStep?.({ key, status, details });

  mark('upload', 'running');
  const params = new URLSearchParams({ filename: file.name });
  let dataset = await requestJson(`/datasets/upload?${params}`, {
    method: 'POST',
    body: file,
  });
  mark('upload', 'success', { dataset_id: dataset.dataset_id });

  const datasetId = dataset.dataset_id;
  mark('domain_pack', 'running');
  dataset = await requestJson(`/datasets/${datasetId}/generate-domain-pack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      domain_name: ADMISSIONS_DOMAIN.domainName,
      template_id: ADMISSIONS_DOMAIN.templateId,
      llm: 'off',
    }),
  });
  mark('domain_pack', 'success');

  mark('profile', 'running');
  const profile = await requestJson(`/datasets/${datasetId}/profile`);
  mark('profile', 'success', { field_count: profile?.fields?.length || 0 });

  mark('review_summary', 'running');
  const reviewSummary = await requestJson(`/datasets/${datasetId}/review-summary`);
  mark('review_summary', 'success', {
    reviewable_fields: reviewSummary?.reviewable_fields?.length || 0,
  });

  mark('approve_domain', 'running');
  const approval = await requestJson(`/datasets/${datasetId}/approve-domain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title_field: 'university_name',
      primary_fields: ['group_code', 'major_name', 'city'],
      default_safe_sort: true,
    }),
  });
  dataset = mergeApprovedDatasetState(dataset, approval);
  const approvalMessage = approvalFailureMessage(approval);
  if (approvalMessage) {
    mark('approve_domain', 'error', { message: approvalMessage });
    throw new Error(approvalMessage);
  }
  mark('approve_domain', 'success');

  mark('build_warehouse', 'running');
  dataset = await requestJson(`/datasets/${datasetId}/build-warehouse`, { method: 'POST' });
  mark('build_warehouse', 'success', {
    row_count: dataset?.warehouse?.row_count || dataset?.row_count || null,
  });

  return { dataset, profile, reviewSummary };
}
```

- [ ] **Step 4: 运行 pipeline 测试确认通过**

Run:

```bash
cd frontend && npm run test:unit -- src/components/upload/importPipeline.test.js
```

Expected: PASS。

- [ ] **Step 5: 创建导入步骤列表组件**

Create `frontend/src/components/upload/ImportStepList.vue`:

```vue
<script setup>
defineProps({
  steps: {
    type: Array,
    required: true,
  },
});

function statusLabel(status) {
  const labels = {
    idle: '等待',
    running: '处理中',
    success: '完成',
    error: '需要处理',
  };
  return labels[status] || status;
}

function tagType(status) {
  if (status === 'success') return 'success';
  if (status === 'running') return 'warning';
  if (status === 'error') return 'danger';
  return 'info';
}
</script>

<template>
  <ol class="import-step-list">
    <li v-for="step in steps" :key="step.key" class="import-step-item">
      <span class="import-step-dot" :class="`is-${step.status}`" />
      <div>
        <strong>{{ step.label }}</strong>
        <small v-if="step.message">{{ step.message }}</small>
      </div>
      <el-tag :type="tagType(step.status)" effect="plain">{{ statusLabel(step.status) }}</el-tag>
    </li>
  </ol>
</template>
```

- [ ] **Step 6: 用 ImportWorkspace 替代 DatasetIngestionPanel 普通路径**

Replace `frontend/src/components/workspaces/ImportWorkspace.vue` with:

```vue
<script setup>
import { computed, ref } from 'vue';
import { UploadFilled } from '@element-plus/icons-vue';

import { createUploadedAdmissionsSource } from '../../domain/admissionsAdapter.js';
import { formatApiError } from '../../utils/apiError.js';
import { selectedRawUploadFile } from '../../utils/uploadFiles.js';
import ImportStepList from '../upload/ImportStepList.vue';
import { ADMISSIONS_IMPORT_STEPS, runAdmissionsImportPipeline } from '../upload/importPipeline.js';

const props = defineProps({
  activeSource: {
    type: Object,
    default: null,
  },
  authHeaders: {
    type: Function,
    required: true,
  },
});

const emit = defineEmits(['source-ready', 'open-review']);

const file = ref(null);
const loading = ref(false);
const errorText = ref('');
const importedSource = ref(null);
const steps = ref(initialSteps());

const canImport = computed(() => Boolean(file.value) && !loading.value);

function initialSteps() {
  return ADMISSIONS_IMPORT_STEPS.map((step) => ({
    ...step,
    status: 'idle',
    message: '',
  }));
}

function updateStep({ key, status, details = {} }) {
  steps.value = steps.value.map((step) => {
    if (step.key !== key) return step;
    return {
      ...step,
      status,
      message: details.message || step.message,
    };
  });
}

function handleFileChange(uploadFile) {
  const selectedFile = selectedRawUploadFile(uploadFile);
  if (selectedFile) {
    file.value = selectedFile;
    errorText.value = '';
    steps.value = initialSteps();
  }
}

async function importAdmissionsFile() {
  if (!file.value) {
    errorText.value = '请先选择 CSV 或 Excel 文件。';
    return;
  }
  loading.value = true;
  errorText.value = '';
  importedSource.value = null;
  steps.value = initialSteps();
  try {
    const result = await runAdmissionsImportPipeline({
      file: file.value,
      requestJson,
      onStep: updateStep,
    });
    const source = createUploadedAdmissionsSource({
      ...result.dataset,
      file_name: file.value.name,
    });
    importedSource.value = source;
    emit('source-ready', result.dataset);
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '导入失败';
  } finally {
    loading.value = false;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...props.authHeaders(),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(formatApiError(payload, 'API 请求失败'));
  }
  return payload;
}
</script>

<template>
  <section class="workspace-panel single-scroll import-workspace">
    <el-card class="workbench-card import-main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>导入招生表</h2>
            <p class="panel-copy">选择招生 CSV / Excel 后，系统会自动检查字段并生成可查询数据。</p>
          </div>
          <el-tag effect="plain">uploaded admissions</el-tag>
        </div>
      </template>

      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        :on-change="handleFileChange"
        accept=".csv,.xlsx,.xls,.xlsm"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖入或选择 CSV / Excel</div>
      </el-upload>

      <div class="button-row">
        <el-button type="primary" :disabled="!canImport" :loading="loading" @click="importAdmissionsFile">
          导入并生成可查询数据
        </el-button>
        <el-button @click="emit('open-review')">打开字段审查</el-button>
      </div>

      <el-alert
        v-if="errorText"
        class="inline-alert"
        type="error"
        :closable="false"
        show-icon
        :title="errorText"
      />
      <el-alert
        v-if="importedSource"
        class="inline-alert"
        type="success"
        :closable="false"
        show-icon
        :title="`${importedSource.label} 已可查询`"
      />

      <ImportStepList :steps="steps" />
    </el-card>
  </section>
</template>
```

- [ ] **Step 7: 从 App 传入 authHeaders 并移除 DatasetIngestionPanel 普通入口**

Modify `frontend/src/App.vue` import list:

```js
// remove DatasetIngestionPanel import
```

Modify import tab:

```vue
<el-tab-pane label="导入数据" name="dataset">
  <ImportWorkspace
    :active-source="selectedDataSource"
    :auth-headers="authHeaders"
    @source-ready="activateUploadedSource"
    @open-review="activeWorkspace = 'review'"
  />
</el-tab-pane>
```

- [ ] **Step 8: 添加导入页样式**

Modify `frontend/src/style.css`:

```css
.import-workspace {
  display: grid;
  gap: 14px;
}

.import-main-card {
  max-width: 920px;
}

.import-step-list {
  display: grid;
  gap: 8px;
  padding: 0;
  margin: 16px 0 0;
  list-style: none;
}

.import-step-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #ffffff;
}

.import-step-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #a7b2ba;
}

.import-step-dot.is-running {
  background: #d9932f;
}

.import-step-dot.is-success {
  background: #2f7d63;
}

.import-step-dot.is-error {
  background: #c94343;
}

.import-step-item small {
  display: block;
  margin-top: 2px;
  color: #66717c;
}
```

- [ ] **Step 9: 运行测试和构建**

Run:

```bash
cd frontend && npm run test:unit
cd frontend && npm run build
```

Expected: both PASS。

- [ ] **Step 10: Commit Task 4**

```bash
git add frontend/src/components/upload frontend/src/components/workspaces/ImportWorkspace.vue frontend/src/App.vue frontend/src/style.css
git commit -m "feat: add one-click uploaded admissions import"
```

## Task 5: 收口字段审查和证据调试

**Files:**
- Modify: `frontend/src/components/workspaces/ReviewWorkspace.vue`
- Modify: `frontend/src/components/workspaces/EvidenceDebugWorkspace.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 让 ReviewWorkspace 只展示高级入口**

Replace `frontend/src/components/workspaces/ReviewWorkspace.vue` with:

```vue
<script setup>
import DatasetIngestionPanel from '../DatasetIngestionPanel.vue';

defineProps({
  selectedDataSource: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['source-ready']);
</script>

<template>
  <section class="workspace-panel single-scroll review-workspace">
    <el-card class="workbench-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>字段审查</h2>
            <p class="panel-copy">只有导入失败或字段映射不对时使用这里。</p>
          </div>
          <el-tag effect="plain" type="warning">高级操作</el-tag>
        </div>
      </template>
      <p class="beginner-empty">
        当前普通路径会自动套用招生字段模板。这里保留原审查工具，方便处理模板不匹配的表格。
      </p>
      <p v-if="selectedDataSource" class="beginner-empty">
        当前数据源：{{ selectedDataSource.label }}
      </p>
    </el-card>

    <el-collapse class="developer-collapse">
      <el-collapse-item title="开发者字段审查工具" name="legacy-review">
        <DatasetIngestionPanel @source-ready="emit('source-ready', $event)" />
      </el-collapse-item>
    </el-collapse>
  </section>
</template>
```

- [ ] **Step 2: 在 App 中接入 ReviewWorkspace source-ready**

Modify `frontend/src/App.vue` review tab:

```vue
<el-tab-pane label="字段审查" name="review">
  <ReviewWorkspace
    :selected-data-source="selectedDataSource"
    @source-ready="activateUploadedSource"
  />
</el-tab-pane>
```

- [ ] **Step 3: 强化证据调试标题**

Modify `frontend/src/components/workspaces/EvidenceDebugWorkspace.vue` template opening:

```vue
<template>
  <section class="workspace-panel detail-workspace evidence-debug-workspace">
    <el-card class="workbench-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>证据调试</h2>
            <p class="panel-copy">这里展示规则、候选、抽取和 verification 细节，不代表额外筛选已经执行。</p>
          </div>
          <el-tag effect="plain">调试</el-tag>
        </div>
      </template>
    </el-card>
    <!-- keep existing rule, candidate, extraction and verification components below this card -->
  </section>
</template>
```

- [ ] **Step 4: 添加审查和调试样式**

Modify `frontend/src/style.css`:

```css
.review-workspace,
.evidence-debug-workspace {
  display: grid;
  gap: 12px;
  align-content: start;
}

.developer-collapse {
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #ffffff;
}
```

- [ ] **Step 5: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 6: Commit Task 5**

```bash
git add frontend/src/components/workspaces/ReviewWorkspace.vue frontend/src/components/workspaces/EvidenceDebugWorkspace.vue frontend/src/App.vue frontend/src/style.css
git commit -m "refactor: isolate frontend review and evidence debug"
```

## Task 6: 强化查询前检查和专业组结果展示

**Files:**
- Modify: `frontend/src/components/PreflightPanel.vue`
- Modify: `frontend/src/components/ResultTable.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 更新 PreflightPanel 标题和空态文案**

Modify `frontend/src/components/PreflightPanel.vue`:

```vue
<header class="preflight-header">
  <div>
    <h2>查询前检查</h2>
    <p>系统先判断哪些内容有证据可以执行，哪些需要你确认，哪些不会进入筛选。</p>
  </div>
  <el-tag :type="statusTag.type" effect="plain">{{ statusTag.label }}</el-tag>
</header>
```

Use these section titles in order:

```vue
<h3>已识别事实</h3>
<h3>需要你确认</h3>
<h3>不会参与筛选</h3>
<h3>还缺少信息</h3>
```

Use these empty messages:

```text
暂无已识别事实。
没有需要确认的边界。
没有被排除的偏好。
没有阻断查询的缺失信息。
```

- [ ] **Step 2: 确认 PreflightPanel 不展示技术 ID**

In `frontend/src/components/PreflightPanel.vue`, keep `confirmation_id` only in `:key` and emitted payload. Do not render:

```text
preflight_id
confirmation_id
preference_id
requirement_id
```

Expected rendered labels come from:

```js
fact.label
boundary.label || boundary.source_text
preference.source_text || preference.label
requirement.label
```

- [ ] **Step 3: 增加 ResultTable 分组结果兼容**

Modify `frontend/src/components/ResultTable.vue` script:

```js
function groupSections(row) {
  if (Array.isArray(row?.majors)) {
    return row.majors;
  }
  if (Array.isArray(row?.items)) {
    return row.items;
  }
  return [];
}

function majorTitle(major) {
  return major.major_name || major.full_major_name || major.title || '专业名称暂无';
}

function majorScore(major) {
  return attrValue(major, ['major_min_score_2024', 'major_min_score', '最低分1', '最低分数']);
}
```

Inside each result item, after `.result-facts`, add:

```vue
<div v-if="groupSections(row).length" class="group-major-list">
  <div
    v-for="major in groupSections(row)"
    :key="major.major_code || major.item_id || majorTitle(major)"
    class="group-major-row"
  >
    <span>{{ majorTitle(major) }}</span>
    <strong>{{ majorScore(major) || '分数暂无' }}</strong>
  </div>
</div>
```

- [ ] **Step 4: 添加专业组明细样式**

Modify `frontend/src/style.css`:

```css
.group-major-list {
  display: grid;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid #edf1f3;
  border-radius: 8px;
  background: #f8faf9;
}

.group-major-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  color: #3d4a52;
  font-size: 13px;
}

.group-major-row span {
  min-width: 0;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 5: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 6: Commit Task 6**

```bash
git add frontend/src/components/PreflightPanel.vue frontend/src/components/ResultTable.vue frontend/src/style.css
git commit -m "feat: clarify preflight and group result display"
```

## Task 7: 文档、全量验证和浏览器验收

**Files:**
- Modify: `frontend/README.md`
- Modify: `README.md` if the root frontend description mentions the old upload/debug flow
- Modify: `docs/methodology_report.md` if it describes frontend uploaded admissions behavior

- [ ] **Step 1: 更新 frontend README**

Modify `frontend/README.md` to include:

```markdown
## C-lite 工作区

前端分为四个工作区：

- 查询：普通用户入口。uploaded admissions 会先做查询前检查，再允许确认后查询。
- 导入数据：普通上传入口。招生表采用一键导入，成功后自动成为可查询数据源。
- 字段审查：高级入口。只有字段模板不匹配或导入失败时使用。
- 证据调试：开发和研究入口。展示规则、候选、证据和 trace。

前端不生成 SQL、QueryAST、RankingPlan 或推荐规则。所有可执行条件必须来自后端验证结果。

## 验证命令

```bash
npm run test:unit
npm run build
```
```

- [ ] **Step 2: 搜索旧描述**

Run:

```bash
rg -n "上传表格|字段审查|查询前检查|DatasetIngestion|三栏|试查上传数据|前端只提交操作" README.md docs frontend/README.md
```

Expected: Identify stale public descriptions. Update only tracked Chinese documentation that describes old ordinary user flow.

- [ ] **Step 3: 运行前端全量测试**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: PASS。

- [ ] **Step 4: 运行前端生产构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS。

- [ ] **Step 5: 跑后端单测防止契约误改**

Run:

```bash
.venv/bin/python -m unittest discover -s tests
```

Expected: PASS with the existing expected failure count unchanged.

- [ ] **Step 6: 浏览器验收桌面主查询**

Open the current dev server or start it:

```bash
cd frontend && npm run dev
```

Verify at desktop width:

```text
默认进入“查询”
左侧是输入
右侧先显示查询前检查或空态
顶部主按钮可见
普通首屏没有 field_id、domain_pack、preflight_id、candidate_id
```

- [ ] **Step 7: 浏览器验收导入页**

In the browser:

```text
进入“导入数据”
只看到上传、一键导入按钮、步骤状态
不看到 city/city 字段输入
失败时显示中文失败步骤
成功后自动回到查询页并选中上传数据源
```

- [ ] **Step 8: 浏览器验收移动宽度**

Use browser responsive mode around 390px width:

```text
查询页纵向滚动
输入、查询前检查、结果不横向溢出
导入步骤列表不挤出屏幕
主按钮和错误提示可见
```

- [ ] **Step 9: 最终差异检查**

Run:

```bash
git status --short
git diff --check
```

Expected: only intended frontend/docs files changed; `git diff --check` exits 0.

- [ ] **Step 10: Commit Task 7**

```bash
git add frontend/README.md README.md docs/methodology_report.md
git commit -m "docs: document c-lite frontend workflow"
```

If `README.md` or `docs/methodology_report.md` had no stale text and were not modified, omit them from `git add` and commit only `frontend/README.md`.

## 自检记录

- 规格覆盖：查询、导入数据、字段审查、证据调试、uploaded admissions preflight、一键导入、adapter 扩展、中文文案、验证命令均有任务覆盖。
- 占位扫描：本计划不使用待填占位项；每个文件、命令和提交范围均已列出。
- 类型一致性：`ADMISSIONS_DOMAIN`、`BUILTIN_ADMISSIONS_SOURCE`、`createUploadedAdmissionsSource`、`shouldUseUploadedAdmissionsPreflight`、`mergeUploadedDataSource`、`runAdmissionsImportPipeline` 在定义任务和使用任务中命名一致。
