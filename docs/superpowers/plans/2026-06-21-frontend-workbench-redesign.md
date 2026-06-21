# Frontend Workbench Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已确认设计重排前端 Workbench：默认空态、显式演示入口、结果优先双栏、主查询候选确认闭环、后端驱动运行选项和上传页轻量步骤流。

**Architecture:** 前端新增一层小型状态/选项/请求工具函数，把可测试行为从 Vue 组件中抽出；`App.vue` 负责工作区编排，`WorkbenchRunBar` 负责顶部常驻运行条，`CandidateRerunPanel` 负责主查询候选确认再查。后端规则边界不变，前端只提交 `WorkbenchResponse` 支持的字段和上一轮系统生成的 `candidate_id`。

**Tech Stack:** Vue 3、Vite、Element Plus、Node `node:test`、浏览器/Playwright 视觉验证。

---

## File Structure

- Create `frontend/src/utils/workbenchState.js`：创建空工作台状态、识别空态、显式套用演示数据、提取可确认候选项。
- Create `frontend/src/utils/workbenchOptions.js`：维护保守 fallback，归一化 `/api/workbench/options` 返回值，给 UI 标记选项来源。
- Create `frontend/src/utils/workbenchRequests.js`：构造 `/workbench/query` 请求体，复用上一轮请求参数并追加 `confirmed_candidates`。
- Create `frontend/src/utils/workbenchState.test.js`：用 Node `node:test` 覆盖默认空态、显式演示、候选确认、请求体构造和 options 归一化。
- Modify `frontend/package.json`：新增 `test:unit` 脚本。
- Create `frontend/src/components/WorkbenchRunBar.vue`：顶部常驻运行条，集中展示数据源、运行状态、运行选项、主查询按钮和演示入口。
- Create `frontend/src/components/CandidateRerunPanel.vue`：主查询里的候选确认再查面板，只允许选择带 `candidate_id` 的候选项。
- Modify `frontend/src/components/WorkbenchModePanel.vue`：移除运行选项硬编码，改由 props 接收 `extractorOptions`、`generatorOptions`、`modelOptions`。
- Modify `frontend/src/components/UserInputPanel.vue`：隐藏底部主按钮、暴露 `submitRun()` 给父组件触发、保留表单校验和 payload 生成。
- Modify `frontend/src/components/ResultTable.vue`：完善空态文案和演示/真实状态下的结果展示，不引入推荐逻辑。
- Modify `frontend/src/components/DatasetIngestionPanel.vue`：把上传、生成草稿、审查、批准、建仓、试查组织成步骤流；原始 JSON 默认折叠。
- Modify `frontend/src/App.vue`：接入空态、顶部运行条、显式演示入口、后端 options、候选确认再查和新布局。
- Modify `frontend/src/style.css`：重写主查询布局、运行条、空态、候选确认、上传步骤和移动端滚动规则。
- Modify `frontend/README.md`：同步默认空态、显式演示、后端 options、候选确认和上传步骤说明。

---

### Task 1: 增加可测试的前端状态、选项和请求工具

**Files:**
- Create: `frontend/src/utils/workbenchState.js`
- Create: `frontend/src/utils/workbenchOptions.js`
- Create: `frontend/src/utils/workbenchRequests.js`
- Create: `frontend/src/utils/workbenchState.test.js`
- Modify: `frontend/package.json`

- [ ] **Step 1: 写失败测试和测试脚本**

修改 `frontend/package.json`，在 `scripts` 中加入 `test:unit`：

```json
{
  "name": "preference-rule-workbench",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test:unit": "node --test src/**/*.test.js"
  },
  "dependencies": {
    "@element-plus/icons-vue": "^2.3.1",
    "@vitejs/plugin-vue": "^5.2.4",
    "element-plus": "^2.10.4",
    "vite": "^5.4.19",
    "vue": "^3.5.17"
  },
  "devDependencies": {}
}
```

创建 `frontend/src/utils/workbenchState.test.js`：

```js
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  confirmableCandidates,
  createEmptyWorkbenchState,
  isEmptyWorkbenchState,
  mergeDemoRun,
} from './workbenchState.js';
import {
  FALLBACK_WORKBENCH_OPTIONS,
  normalizeWorkbenchOptions,
} from './workbenchOptions.js';
import {
  buildConfirmedWorkbenchRequest,
  buildWorkbenchRequest,
} from './workbenchRequests.js';

test('createEmptyWorkbenchState does not expose mock results', () => {
  const state = createEmptyWorkbenchState();

  assert.equal(state.status, 'idle');
  assert.equal(state.result_count, 0);
  assert.deepEqual(state.items, []);
  assert.deepEqual(state.top_results, []);
  assert.equal(isEmptyWorkbenchState(state), true);
});

test('mergeDemoRun marks data as explicit demo only after user action', () => {
  const demo = {
    status: 'ok',
    result_count: 1,
    top_results: [{ university_name: '演示大学' }],
  };
  const merged = mergeDemoRun(demo, {
    selectedOptions: { extractor: 'regex' },
  });

  assert.equal(merged.status, 'ok');
  assert.equal(merged.result_count, 1);
  assert.equal(merged.frontend_state.source, 'demo');
  assert.equal(merged.frontend_state.is_explicit_demo, true);
  assert.equal(merged.selected_options.extractor, 'regex');
});

test('confirmableCandidates keeps only candidates with generated ids', () => {
  const candidates = confirmableCandidates({
    candidates_to_confirm: [
      { candidate_id: 'c_city', label: '广州' },
      { id: 'legacy_id', preference: '软件工程' },
      { preference: '没有 id' },
    ],
  });

  assert.deepEqual(
    candidates.map((candidate) => candidate.confirmationId),
    ['c_city', 'legacy_id'],
  );
});

test('normalizeWorkbenchOptions prefers API payload and falls back per group', () => {
  const options = normalizeWorkbenchOptions({
    extractors: [{ value: 'hybrid', label: '规则优先，LLM 补槽' }],
    generators: [{ value: 'template_evidence', label: '模板证据回答' }],
    models: [{ value: 'deepseek-v4-flash', label: 'LLM 快速模型' }],
    rank_windows: [{ value: 'steady', label: '稳一点', rank_window_upper_percent: 15 }],
    sort_modes: [{ value: 'rank_desc', label: '按历史位次从低到高看（更稳）' }],
  });

  assert.equal(options.source, 'api');
  assert.equal(options.extractors[0].value, 'hybrid');
  assert.equal(options.rank_windows[0].description, '');
});

test('normalizeWorkbenchOptions uses complete fallback when API payload is empty', () => {
  const options = normalizeWorkbenchOptions(null);

  assert.equal(options.source, 'fallback');
  assert.deepEqual(options.extractors, FALLBACK_WORKBENCH_OPTIONS.extractors);
  assert.equal(options.rank_windows.length, 3);
});

test('buildWorkbenchRequest includes dataset id only for uploaded sources', () => {
  const request = buildWorkbenchRequest({
    source: {
      datasetId: 'dataset_1',
      domainName: 'admissions',
      label: '上传：a.xlsx',
    },
    runRequest: {
      user_input: '广东物理，排位 32000。',
      hard_filters: { user_rank: 32000 },
      soft_preferences: { prompt: '想学计算机' },
    },
    extractor: 'hybrid',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  });

  assert.equal(request.dataset_id, 'dataset_1');
  assert.equal(request.domain_name, 'admissions');
  assert.equal(request.extractor, 'hybrid');
  assert.deepEqual(request.confirmed_candidates, []);
});

test('buildConfirmedWorkbenchRequest reuses previous request and appends candidate ids', () => {
  const previous = {
    domain_name: 'admissions',
    user_input: '广东物理，排位 32000。',
    hard_filters: { user_rank: 32000 },
    soft_preferences: { prompt: '想学计算机' },
    extractor: 'regex',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  };

  const request = buildConfirmedWorkbenchRequest(previous, ['c_city', 'c_major']);

  assert.deepEqual(request.confirmed_candidates, ['c_city', 'c_major']);
  assert.equal(request.user_input, previous.user_input);
  assert.notEqual(request, previous);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: FAIL，错误包含 `Cannot find module`，因为 `workbenchState.js`、`workbenchOptions.js` 或 `workbenchRequests.js` 尚未创建。

- [ ] **Step 3: 实现 `workbenchState.js`**

创建 `frontend/src/utils/workbenchState.js`：

```js
export function createEmptyWorkbenchState(overrides = {}) {
  return {
    schema_version: null,
    domain: null,
    domain_version: null,
    domain_pack_status: null,
    status: 'idle',
    query_type: null,
    query: {},
    answer: '',
    items: [],
    top_results: [],
    result_sections: {},
    result_count: 0,
    executed_filters: [],
    executable_rules: [],
    candidates_to_confirm: [],
    candidate_rules: [],
    confirmed_rules: [],
    unconfirmed_candidates: [],
    unexecuted_preferences: [],
    not_executed_preferences: [],
    no_schema_field_preferences: [],
    rejected_confirmations: [],
    warnings: [],
    evidence_pack: {},
    debug_trace: {},
    natural_language_report: null,
    token_usage: null,
    selected_options: {},
    frontend_state: {
      source: 'empty',
      is_explicit_demo: false,
      options_source: 'fallback',
    },
    ...overrides,
  };
}

export function isEmptyWorkbenchState(data) {
  return !data || data.status === 'idle' || data.frontend_state?.source === 'empty';
}

export function mergeDemoRun(demoRun, { runRequest = null, selectedOptions = {} } = {}) {
  return {
    ...demoRun,
    ...(runRequest
      ? {
          user_input: runRequest.user_input,
          hard_filters: runRequest.hard_filters,
          soft_preferences: runRequest.soft_preferences,
        }
      : {}),
    selected_options: {
      ...(demoRun?.selected_options || {}),
      ...selectedOptions,
    },
    token_usage: null,
    frontend_state: {
      source: 'demo',
      is_explicit_demo: true,
      options_source: 'demo',
    },
  };
}

export function candidateIdentifier(candidate) {
  return candidate?.candidate_id || candidate?.id || '';
}

export function confirmableCandidates(runData) {
  const candidates = Array.isArray(runData?.candidates_to_confirm) && runData.candidates_to_confirm.length
    ? runData.candidates_to_confirm
    : Array.isArray(runData?.candidate_rules)
      ? runData.candidate_rules
      : [];

  return candidates
    .map((candidate) => ({
      ...candidate,
      confirmationId: candidateIdentifier(candidate),
    }))
    .filter((candidate) => candidate.confirmationId);
}
```

- [ ] **Step 4: 实现 `workbenchOptions.js`**

创建 `frontend/src/utils/workbenchOptions.js`：

```js
export const FALLBACK_WORKBENCH_OPTIONS = {
  extractors: [
    { value: 'hybrid', label: '规则优先，LLM 补槽' },
    { value: 'regex', label: '规则解析软偏好' },
    { value: 'deepseek', label: 'LLM 辅助解析软偏好' },
  ],
  generators: [
    { value: 'template_evidence', label: '模板证据回答' },
    { value: 'deepseek_evidence', label: 'LLM 证据回答' },
  ],
  models: [
    { value: 'deepseek-v4-flash', label: 'LLM 快速模型' },
    { value: 'deepseek-v4-pro', label: 'LLM 高质量模型' },
  ],
  rank_windows: [
    {
      value: 'reach',
      label: '冲一冲',
      rank_window_lower_percent: 0,
      rank_window_upper_percent: 0,
      description: '只执行后 0% 上界，不设置前向下界。',
    },
    {
      value: 'steady',
      label: '稳一点',
      rank_window_lower_percent: 0,
      rank_window_upper_percent: 15,
      description: '只执行后 15% 上界，不设置前向下界。',
    },
    {
      value: 'safe',
      label: '保底',
      rank_window_lower_percent: 0,
      rank_window_upper_percent: 50,
      description: '只执行后 50% 上界，不设置前向下界。',
    },
  ],
  sort_modes: [
    { value: 'rank_asc', label: '按历史位次从高到低看（更冲）' },
    { value: 'rank_desc', label: '按历史位次从低到高看（更稳）' },
    { value: 'school_rank_asc', label: '同等条件下优先院校排名' },
  ],
};

const OPTION_GROUPS = [
  'extractors',
  'generators',
  'models',
  'rank_windows',
  'sort_modes',
];

export function normalizeWorkbenchOptions(payload) {
  const source = payload && typeof payload === 'object' ? 'api' : 'fallback';
  const normalized = { source };
  let usedFallback = false;

  for (const group of OPTION_GROUPS) {
    const hasApiValues = Array.isArray(payload?.[group]) && payload[group].length;
    const values = hasApiValues ? payload[group] : FALLBACK_WORKBENCH_OPTIONS[group];
    if (!hasApiValues) {
      usedFallback = true;
    }
    normalized[group] = values.map(normalizeOption);
  }

  normalized.source = source === 'api' && usedFallback ? 'partial_fallback' : source;

  return normalized;
}

export function normalizeOption(option) {
  return {
    ...option,
    value: option.value,
    label: option.label || option.value,
    description: option.description || '',
  };
}

export function firstOptionValue(options, fallback = '') {
  return Array.isArray(options) && options.length ? options[0].value : fallback;
}
```

- [ ] **Step 5: 实现 `workbenchRequests.js`**

创建 `frontend/src/utils/workbenchRequests.js`：

```js
export function buildWorkbenchRequest({
  source,
  runRequest,
  extractor,
  generator,
  model,
  confirmedCandidates = [],
}) {
  const requestBody = {
    domain_name: source?.domainName || 'admissions',
    user_input: runRequest.user_input,
    hard_filters: runRequest.hard_filters,
    soft_preferences: runRequest.soft_preferences,
    extractor,
    generator,
    model,
    confirmed_candidates: [...confirmedCandidates],
  };

  if (source?.datasetId) {
    requestBody.dataset_id = source.datasetId;
  }

  return requestBody;
}

export function buildConfirmedWorkbenchRequest(previousRequest, confirmedCandidates) {
  return {
    ...previousRequest,
    confirmed_candidates: [...confirmedCandidates],
  };
}
```

- [ ] **Step 6: 运行测试确认通过**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: PASS，`# pass 7`。

- [ ] **Step 7: 提交 Task 1**

Run:

```bash
git add frontend/package.json frontend/src/utils/workbenchState.js frontend/src/utils/workbenchOptions.js frontend/src/utils/workbenchRequests.js frontend/src/utils/workbenchState.test.js
git commit -m "test: add frontend workbench state helpers"
```

Expected: commit succeeds.

---

### Task 2: 把 `App.vue` 改为空态优先并接入后端 options

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/utils/workbenchState.test.js`

- [ ] **Step 1: 扩展工具测试覆盖 selected options 和空态统计**

在 `frontend/src/utils/workbenchState.test.js` 追加：

```js
test('empty state keeps quick stat compatible fields empty', () => {
  const state = createEmptyWorkbenchState({
    selected_options: { extractor: 'hybrid' },
  });

  assert.equal(state.executed_filters.length, 0);
  assert.equal(state.candidates_to_confirm.length, 0);
  assert.equal(state.no_schema_field_preferences.length, 0);
  assert.equal(state.selected_options.extractor, 'hybrid');
});
```

- [ ] **Step 2: 运行测试确认仍通过**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: PASS，`# pass 8`。

- [ ] **Step 3: 修改 `App.vue` imports 和初始状态**

在 `frontend/src/App.vue` 顶部加入：

```js
import {
  buildConfirmedWorkbenchRequest,
  buildWorkbenchRequest,
} from './utils/workbenchRequests';
import {
  createEmptyWorkbenchState,
  mergeDemoRun,
} from './utils/workbenchState';
import {
  firstOptionValue,
  normalizeWorkbenchOptions,
} from './utils/workbenchOptions';
```

删除当前 `workbenchOptions = ref({ ... })` 的内联常量，替换为：

```js
const workbenchOptions = ref(normalizeWorkbenchOptions(null));
const optionsLoadError = ref('');
```

把当前 `runData = ref({ ...demoRun, ... })` 替换为：

```js
const runData = ref(createEmptyWorkbenchState({
  selected_options: {
    extractor: 'hybrid',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  },
}));
const lastRunRequest = ref(null);
const lastRequestBody = ref(null);
```

把初始运行选项改为：

```js
const extractor = ref('hybrid');
const generator = ref('template_evidence');
const model = ref('deepseek-v4-flash');
```

- [ ] **Step 4: 修改 options 获取逻辑**

替换 `fetchWorkbenchOptions()`：

```js
async function fetchWorkbenchOptions() {
  if (mode.value !== 'api') return;
  try {
    const response = await fetch('/api/workbench/options', {
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error('后端选项加载失败');
    }
    const payload = await response.json();
    workbenchOptions.value = normalizeWorkbenchOptions(payload);
    optionsLoadError.value = '';
    ensureSelectedRuntimeOptions();
  } catch (error) {
    workbenchOptions.value = normalizeWorkbenchOptions(null);
    optionsLoadError.value = error instanceof Error ? error.message : '后端选项加载失败';
    ensureSelectedRuntimeOptions();
  }
}

function ensureSelectedRuntimeOptions() {
  if (!workbenchOptions.value.extractors.some((option) => option.value === extractor.value)) {
    extractor.value = firstOptionValue(workbenchOptions.value.extractors, 'hybrid');
  }
  if (!workbenchOptions.value.generators.some((option) => option.value === generator.value)) {
    generator.value = firstOptionValue(workbenchOptions.value.generators, 'template_evidence');
  }
  if (!workbenchOptions.value.models.some((option) => option.value === model.value)) {
    model.value = firstOptionValue(workbenchOptions.value.models, 'deepseek-v4-flash');
  }
}
```

- [ ] **Step 5: 修改演示和 API 查询逻辑**

替换 `runDemo()`：

```js
function runDemo(runRequest = lastRunRequest.value, selectedOptions = {}) {
  runData.value = mergeDemoRun(demoRun, {
    runRequest,
    selectedOptions: {
      extractor: extractor.value,
      generator: generator.value,
      model: model.value,
      ...selectedOptions,
    },
  });
  apiError.value = '';
  lastRunFailed.value = false;
}
```

替换 `runWorkbench()` 中构造请求体的部分：

```js
async function runWorkbench(runRequest) {
  lastRunRequest.value = runRequest;
  if (mode.value === 'demo') {
    runDemo(runRequest);
    return;
  }

  loading.value = true;
  apiError.value = '';
  lastRunFailed.value = false;
  const source = selectedDataSource.value;
  const requestBody = buildWorkbenchRequest({
    source,
    runRequest,
    extractor: normalizedExtractor(),
    generator: generator.value,
    model: model.value,
  });
  lastRequestBody.value = requestBody;
  try {
    const response = await fetch('/workbench/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(requestBody),
    });
    const apiPayload = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(apiPayload, '后端运行失败'));
    }
    runData.value = {
      ...apiPayload,
      selected_options: {
        ...(apiPayload.selected_options || {}),
        data_source: source.label,
      },
      frontend_state: {
        source: 'api',
        is_explicit_demo: false,
        options_source: workbenchOptions.value.source,
      },
    };
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '后端运行失败');
    lastRunFailed.value = true;
  } finally {
    loading.value = false;
  }
}
```

- [ ] **Step 6: 新增确认再查方法**

在 `App.vue` methods 区加入：

```js
async function rerunWithConfirmedCandidates(candidateIds) {
  if (!lastRequestBody.value || !candidateIds.length) {
    return;
  }
  loading.value = true;
  apiError.value = '';
  lastRunFailed.value = false;
  const requestBody = buildConfirmedWorkbenchRequest(lastRequestBody.value, candidateIds);
  lastRequestBody.value = requestBody;
  try {
    const response = await fetch('/workbench/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(requestBody),
    });
    const apiPayload = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(apiPayload, '确认后查询失败'));
    }
    runData.value = {
      ...apiPayload,
      selected_options: {
        ...(apiPayload.selected_options || {}),
        data_source: selectedDataSource.value.label,
      },
      frontend_state: {
        source: 'api',
        is_explicit_demo: false,
        options_source: workbenchOptions.value.source,
      },
    };
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '确认后查询失败');
    lastRunFailed.value = true;
  } finally {
    loading.value = false;
  }
}
```

- [ ] **Step 7: 运行单元测试和构建**

Run:

```bash
cd frontend && npm run test:unit && npm run build
```

Expected: both commands PASS.

- [ ] **Step 8: 提交 Task 2**

Run:

```bash
git add frontend/src/App.vue frontend/src/utils/workbenchState.test.js
git commit -m "feat: initialize workbench with empty state"
```

Expected: commit succeeds.

---

### Task 3: 新增顶部运行条并让运行选项后端驱动

**Files:**
- Create: `frontend/src/components/WorkbenchRunBar.vue`
- Modify: `frontend/src/components/WorkbenchModePanel.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 修改 `WorkbenchModePanel.vue` 支持外部选项**

在 `frontend/src/components/WorkbenchModePanel.vue` 的 props 中新增：

```js
  extractorOptions: {
    type: Array,
    required: true,
  },
  generatorOptions: {
    type: Array,
    required: true,
  },
  modelOptions: {
    type: Array,
    required: true,
  },
```

删除 `demoExtractors`、`apiExtractors`、`demoGenerators`、`apiGenerators`、`models` 和对应 computed，改成：

```js
const extractorOptions = computed(() => props.extractorOptions);
const generatorOptions = computed(() => props.generatorOptions);
const modelOptions = computed(() => props.modelOptions);
```

更新 `updateMode()`：

```js
function updateMode(value) {
  emit('update:mode', value);
  if (!props.extractorOptions.some((option) => option.value === props.extractor)) {
    emit('update:extractor', props.extractorOptions[0]?.value || 'hybrid');
  }
  if (!props.generatorOptions.some((option) => option.value === props.generator)) {
    emit('update:generator', props.generatorOptions[0]?.value || 'template_evidence');
  }
}
```

把模型 `<el-option>` 的 `v-for` 改为：

```vue
<el-option
  v-for="option in modelOptions"
  :key="option.value"
  :label="option.label"
  :value="option.value"
/>
```

- [ ] **Step 2: 创建 `WorkbenchRunBar.vue`**

创建 `frontend/src/components/WorkbenchRunBar.vue`：

```vue
<script setup>
import { computed } from 'vue';
import { Connection, DataAnalysis, Promotion, Upload } from '@element-plus/icons-vue';

import WorkbenchModePanel from './WorkbenchModePanel.vue';

const props = defineProps({
  mode: { type: String, required: true },
  extractor: { type: String, required: true },
  generator: { type: String, required: true },
  model: { type: String, required: true },
  loading: { type: Boolean, default: false },
  selectedDataSourceId: { type: String, required: true },
  dataSourceOptions: { type: Array, required: true },
  dataSourceTag: { type: Object, required: true },
  dataSourceDescription: { type: String, required: true },
  extractorOptions: { type: Array, required: true },
  generatorOptions: { type: Array, required: true },
  modelOptions: { type: Array, required: true },
  optionsSource: { type: String, required: true },
  optionsError: { type: String, default: '' },
  hasRunData: { type: Boolean, default: false },
});

const emit = defineEmits([
  'run',
  'demo',
  'upload',
  'update:mode',
  'update:extractor',
  'update:generator',
  'update:model',
  'update:selectedDataSourceId',
]);

const selectedSource = computed(() => (
  props.dataSourceOptions.find((source) => source.id === props.selectedDataSourceId)
  || props.dataSourceOptions[0]
));
const optionsTag = computed(() => {
  if (props.optionsSource === 'api') return { type: 'success', label: '后端选项' };
  if (props.optionsSource === 'partial_fallback') return { type: 'warning', label: '部分 fallback' };
  return { type: 'warning', label: 'fallback' };
});
</script>

<template>
  <section class="run-bar" aria-label="运行控制">
    <div class="run-bar-source">
      <span class="control-label">数据源</span>
      <div class="run-bar-source-row">
        <el-select
          :model-value="selectedDataSourceId"
          class="run-bar-select"
          size="small"
          @update:model-value="emit('update:selectedDataSourceId', $event)"
        >
          <el-option
            v-for="source in dataSourceOptions"
            :key="source.id"
            :label="source.label"
            :value="source.id"
          />
        </el-select>
        <el-tag :type="dataSourceTag.type" effect="plain">
          {{ dataSourceTag.label }}
        </el-tag>
      </div>
      <p>{{ selectedSource?.description || dataSourceDescription }}</p>
    </div>

    <div class="run-bar-status">
      <el-tag :type="mode === 'api' ? 'warning' : 'info'" effect="plain">
        {{ mode === 'api' ? 'API 查询' : '演示数据' }}
      </el-tag>
      <el-tag :type="optionsTag.type" effect="plain">
        {{ optionsTag.label }}
      </el-tag>
      <span v-if="optionsError" class="run-bar-warning">{{ optionsError }}</span>
    </div>

    <div class="run-bar-options">
      <el-popover placement="bottom-end" :width="420" trigger="click">
        <template #reference>
          <el-button :icon="DataAnalysis" plain>
            运行选项
          </el-button>
        </template>
        <WorkbenchModePanel
          :mode="mode"
          :extractor="extractor"
          :generator="generator"
          :model="model"
          :extractor-options="extractorOptions"
          :generator-options="generatorOptions"
          :model-options="modelOptions"
          @update:mode="emit('update:mode', $event)"
          @update:extractor="emit('update:extractor', $event)"
          @update:generator="emit('update:generator', $event)"
          @update:model="emit('update:model', $event)"
        />
      </el-popover>
      <el-button :icon="Upload" plain @click="emit('upload')">
        上传表格
      </el-button>
      <el-button :icon="Connection" plain @click="emit('demo')">
        查看演示数据
      </el-button>
      <el-button
        type="primary"
        :icon="Promotion"
        :loading="loading"
        @click="emit('run')"
      >
        {{ loading ? '正在查询' : '开始查询' }}
      </el-button>
    </div>
  </section>
</template>
```

- [ ] **Step 3: 在 `App.vue` 接入运行条**

添加 import：

```js
import WorkbenchRunBar from './components/WorkbenchRunBar.vue';
```

新增输入面板 ref 和顶层运行方法：

```js
const inputPanelRef = ref(null);

function submitCurrentForm() {
  inputPanelRef.value?.submitRun();
}
```

在模板查询页顶部加入：

```vue
<WorkbenchRunBar
  v-model:mode="mode"
  v-model:extractor="extractor"
  v-model:generator="generator"
  v-model:model="model"
  v-model:selected-data-source-id="selectedDataSourceId"
  :loading="loading"
  :data-source-options="dataSourceOptions"
  :data-source-tag="dataSourceTag"
  :data-source-description="dataSourceDescription"
  :extractor-options="workbenchOptions.extractors"
  :generator-options="workbenchOptions.generators"
  :model-options="workbenchOptions.models"
  :options-source="workbenchOptions.source"
  :options-error="optionsLoadError"
  :has-run-data="runData.status !== 'idle'"
  @run="submitCurrentForm"
  @demo="runDemo()"
  @upload="goToUpload"
  @update:selected-data-source-id="handleDataSourceChange"
/>
```

将 `UserInputPanel` 增加 `ref` 和隐藏面板底部按钮：

```vue
<UserInputPanel
  ref="inputPanelRef"
  :default-hard-filters="defaultHardFilters"
  :default-soft-preferences="defaultSoftPreferences"
  :mode="mode"
  :loading="loading"
  :rank-window-options="workbenchOptions.rank_windows"
  :sort-mode-options="workbenchOptions.sort_modes"
  :show-panel-actions="false"
  @run="runWorkbench"
/>
```

- [ ] **Step 4: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: 提交 Task 3**

Run:

```bash
git add frontend/src/components/WorkbenchRunBar.vue frontend/src/components/WorkbenchModePanel.vue frontend/src/App.vue
git commit -m "feat: add workbench run bar"
```

Expected: commit succeeds.

---

### Task 4: 让输入面板支持顶部按钮触发

**Files:**
- Modify: `frontend/src/components/UserInputPanel.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 给 `UserInputPanel.vue` 增加 prop 和 expose**

在 props 中加入：

```js
  showPanelActions: {
    type: Boolean,
    default: true,
  },
```

在 `<script setup>` 末尾加入：

```js
defineExpose({
  submitRun,
});
```

把模板底部按钮包裹为：

```vue
<div v-if="showPanelActions" class="panel-actions">
  <el-button
    type="primary"
    size="large"
    :icon="Search"
    :loading="loading"
    @click="submitRun"
  >
    查看可筛结果
  </el-button>
  <span class="muted-note">
    {{ mode === 'api' ? '实时查询' : '演示结果' }}
  </span>
</div>
```

- [ ] **Step 2: 清理不再需要的左侧数据源面板**

在 `frontend/src/App.vue` 的查询左栏中删除旧的 `<section class="data-source-panel">...</section>`，因为数据源和上传入口已经移到 `WorkbenchRunBar`。

- [ ] **Step 3: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: 提交 Task 4**

Run:

```bash
git add frontend/src/components/UserInputPanel.vue frontend/src/App.vue
git commit -m "feat: trigger query from fixed run bar"
```

Expected: commit succeeds.

---

### Task 5: 增加主查询候选确认再查面板

**Files:**
- Create: `frontend/src/components/CandidateRerunPanel.vue`
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/utils/workbenchState.test.js`

- [ ] **Step 1: 增加无 `candidate_id` 不可确认的测试**

在 `frontend/src/utils/workbenchState.test.js` 追加：

```js
test('confirmableCandidates excludes preferences without generated candidate ids', () => {
  const candidates = confirmableCandidates({
    candidates_to_confirm: [
      { candidate_id: 'c_rank', preference: '稳一点' },
      { preference: '离家近', reason: '没有 schema 字段' },
    ],
  });

  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].confirmationId, 'c_rank');
});
```

- [ ] **Step 2: 运行单元测试**

Run:

```bash
cd frontend && npm run test:unit
```

Expected: PASS，`# pass 9`。

- [ ] **Step 3: 创建 `CandidateRerunPanel.vue`**

创建 `frontend/src/components/CandidateRerunPanel.vue`：

```vue
<script setup>
import { computed, ref, watch } from 'vue';
import { Refresh } from '@element-plus/icons-vue';

import { confirmableCandidates } from '../utils/workbenchState';

const props = defineProps({
  runData: {
    type: Object,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['confirm']);
const selectedIds = ref([]);

const candidates = computed(() => confirmableCandidates(props.runData));
const blockedCandidates = computed(() => {
  const all = props.runData?.candidates_to_confirm?.length
    ? props.runData.candidates_to_confirm
    : props.runData?.candidate_rules || [];
  return all.filter((candidate) => !candidate.candidate_id && !candidate.id);
});

watch(candidates, () => {
  selectedIds.value = [];
});

function title(candidate) {
  return candidate.label
    || candidate.preference
    || candidate.value
    || candidate.normalized_value
    || candidate.confirmationId;
}

function reason(candidate) {
  return candidate.reason
    || candidate.match_type
    || candidate.field_id
    || '确认后后端会重新校验，再决定是否执行。';
}
</script>

<template>
  <section v-if="candidates.length || blockedCandidates.length" class="candidate-rerun-panel">
    <div class="candidate-rerun-header">
      <div>
        <h3>需要确认后再查</h3>
        <p>只提交后端生成的 candidate_id；确认后仍由后端重新验证。</p>
      </div>
      <el-button
        type="warning"
        :icon="Refresh"
        :disabled="!selectedIds.length"
        :loading="loading"
        @click="emit('confirm', selectedIds)"
      >
        确认后再查
      </el-button>
    </div>

    <el-checkbox-group v-model="selectedIds" class="candidate-rerun-list">
      <label
        v-for="candidate in candidates"
        :key="candidate.confirmationId"
        class="candidate-rerun-row"
      >
        <el-checkbox :label="candidate.confirmationId">
          确认使用
        </el-checkbox>
        <strong>{{ title(candidate) }}</strong>
        <span>{{ reason(candidate) }}</span>
      </label>
    </el-checkbox-group>

    <div v-if="blockedCandidates.length" class="candidate-rerun-blocked">
      <el-alert
        v-for="candidate in blockedCandidates"
        :key="candidate.preference || candidate.reason"
        type="warning"
        :closable="false"
        show-icon
        :title="`${title(candidate)}：缺少系统生成的 candidate_id，只展示不确认。`"
      />
    </div>
  </section>
</template>
```

- [ ] **Step 4: 在 `App.vue` 接入面板**

添加 import：

```js
import CandidateRerunPanel from './components/CandidateRerunPanel.vue';
```

在结果区 `ResultTable` 上方加入：

```vue
<CandidateRerunPanel
  :run-data="runData"
  :loading="loading"
  @confirm="rerunWithConfirmedCandidates"
/>
```

- [ ] **Step 5: 运行单元测试和构建**

Run:

```bash
cd frontend && npm run test:unit && npm run build
```

Expected: both commands PASS.

- [ ] **Step 6: 提交 Task 5**

Run:

```bash
git add frontend/src/components/CandidateRerunPanel.vue frontend/src/App.vue frontend/src/utils/workbenchState.test.js
git commit -m "feat: confirm candidates from query results"
```

Expected: commit succeeds.

---

### Task 6: 重排查询页并修复按钮隐藏

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/ResultTable.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 修改 `ResultTable.vue` 空态文案**

把空结果模板替换为：

```vue
<el-empty v-if="!results.length" description="暂无查询结果">
  <p class="beginner-empty">填写左侧信息后点击开始查询；默认不会展示演示院校。</p>
</el-empty>
```

- [ ] **Step 2: 修改 `App.vue` 查询页结构**

把查询页 `<section class="workspace-panel query-workspace">` 内部重排为：

```vue
<section class="workspace-panel query-workspace">
  <WorkbenchRunBar
    v-model:mode="mode"
    v-model:extractor="extractor"
    v-model:generator="generator"
    v-model:model="model"
    v-model:selected-data-source-id="selectedDataSourceId"
    :loading="loading"
    :data-source-options="dataSourceOptions"
    :data-source-tag="dataSourceTag"
    :data-source-description="dataSourceDescription"
    :extractor-options="workbenchOptions.extractors"
    :generator-options="workbenchOptions.generators"
    :model-options="workbenchOptions.models"
    :options-source="workbenchOptions.source"
    :options-error="optionsLoadError"
    :has-run-data="runData.status !== 'idle'"
    @run="submitCurrentForm"
    @demo="runDemo()"
    @upload="goToUpload"
    @update:selected-data-source-id="handleDataSourceChange"
  />

  <div class="query-main-grid">
    <aside class="control-column">
      <UserInputPanel
        ref="inputPanelRef"
        :default-hard-filters="defaultHardFilters"
        :default-soft-preferences="defaultSoftPreferences"
        :mode="mode"
        :loading="loading"
        :rank-window-options="workbenchOptions.rank_windows"
        :sort-mode-options="workbenchOptions.sort_modes"
        :show-panel-actions="false"
        @run="runWorkbench"
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

    <section class="result-column">
      <template v-if="!lastRunFailed">
        <div class="quick-stats">
          <article v-for="item in quickStats" :key="item.label" :class="['quick-stat', `tone-${item.tone}`]">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </article>
        </div>
        <CandidateRerunPanel
          :run-data="runData"
          :loading="loading"
          @confirm="rerunWithConfirmedCandidates"
        />
        <ResultTable
          :results="resultRows"
          :total="runData?.result_count || 0"
          @view-trace="openTrace"
        />
      </template>
      <el-card v-else class="workbench-card empty-run" shadow="never">
        <el-empty description="这次没查成功">
          <p class="beginner-empty">{{ apiError }}</p>
        </el-empty>
      </el-card>
    </section>

    <aside class="evidence-column">
      <template v-if="!lastRunFailed">
        <BeginnerDecisionPanel :run-data="runData" />
        <el-collapse class="detail-collapse">
          <el-collapse-item title="为什么这样筛" name="evidence">
            <EvidenceReport :report="runData?.natural_language_report" />
          </el-collapse-item>
          <el-collapse-item title="检查详情" name="audit">
            <EvalSummary :run-data="runData" />
            <TokenUsagePanel
              :token-usage="runData?.token_usage"
              :mode="mode"
              :selected-options="runData?.selected_options"
            />
          </el-collapse-item>
        </el-collapse>
      </template>
      <el-card v-else class="workbench-card" shadow="never">
        <p class="beginner-empty">本次没有生成筛选依据。处理好左侧提示后再查一次。</p>
      </el-card>
    </aside>
  </div>
</section>
```

- [ ] **Step 3: 替换主布局 CSS**

在 `frontend/src/style.css` 中替换 `body`、`.app-shell`、`.query-workspace`、`.control-column`、`.result-column`、`.evidence-column` 相关规则：

```css
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  overflow: auto;
  background: #eef2f6;
}

.app-shell {
  display: flex;
  flex-direction: column;
  width: min(1600px, calc(100% - 24px));
  min-height: 100vh;
  margin: 0 auto;
  padding: 10px 0 12px;
}

.query-workspace {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
}

.query-main-grid {
  display: grid;
  grid-template-columns: minmax(320px, 390px) minmax(560px, 1.35fr) minmax(280px, 0.75fr);
  gap: 12px;
  min-height: 0;
}

.run-bar {
  position: sticky;
  top: 0;
  z-index: 12;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto auto;
  gap: 12px;
  align-items: center;
  padding: 10px;
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 8px 24px rgba(20, 40, 50, 0.08);
}

.run-bar-source {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.run-bar-source-row,
.run-bar-status,
.run-bar-options,
.candidate-rerun-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.run-bar-select {
  width: min(360px, 100%);
}

.run-bar-source p,
.run-bar-warning,
.candidate-rerun-header p {
  margin: 0;
  color: #66717c;
  font-size: 12px;
  line-height: 1.4;
}

.candidate-rerun-panel {
  padding: 12px;
  border: 1px solid #ead59b;
  border-radius: 8px;
  background: #fffdf8;
}

.candidate-rerun-header {
  justify-content: space-between;
  margin-bottom: 10px;
}

.candidate-rerun-header h3 {
  margin: 0;
  color: #1e333d;
  font-size: 15px;
}

.candidate-rerun-list {
  display: grid;
  gap: 8px;
}

.candidate-rerun-row {
  display: grid;
  grid-template-columns: minmax(130px, auto) minmax(120px, 0.7fr) minmax(200px, 1fr);
  gap: 10px;
  align-items: center;
  padding: 9px;
  border: 1px solid #e8dcc0;
  border-radius: 8px;
  background: #ffffff;
}

.candidate-rerun-row strong {
  color: #1d3039;
}

.candidate-rerun-row span {
  color: #66717c;
  font-size: 13px;
  line-height: 1.45;
}

.candidate-rerun-blocked {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}
```

在现有 `@media (max-width: 980px)` 中加入：

```css
  .run-bar,
  .query-main-grid {
    grid-template-columns: 1fr;
  }

  .run-bar {
    position: static;
  }
```

在现有 `@media (max-width: 640px)` 中加入：

```css
  .candidate-rerun-row {
    grid-template-columns: 1fr;
  }

  .run-bar-options {
    align-items: stretch;
    flex-direction: column;
  }

  .run-bar-options .el-button {
    width: 100%;
    margin-left: 0 !important;
  }
```

- [ ] **Step 4: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: 提交 Task 6**

Run:

```bash
git add frontend/src/App.vue frontend/src/components/ResultTable.vue frontend/src/style.css
git commit -m "feat: redesign query workspace layout"
```

Expected: commit succeeds.

---

### Task 7: 轻量整理上传与审查页

**Files:**
- Modify: `frontend/src/components/DatasetIngestionPanel.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 增加步骤状态 computed**

在 `frontend/src/components/DatasetIngestionPanel.vue` 的 computed 区加入：

```js
const datasetSteps = computed(() => [
  {
    key: 'upload',
    title: '上传文件',
    description: file.value ? file.value.name : '选择 CSV 或 Excel 文件',
    status: dataset.value ? 'success' : file.value ? 'process' : 'wait',
  },
  {
    key: 'draft',
    title: '生成草稿',
    description: datasetId.value ? '生成 domain pack 和 schema profile' : '上传后可生成',
    status: profile.value || reviewSummary.value ? 'success' : datasetId.value ? 'process' : 'wait',
  },
  {
    key: 'review',
    title: '字段审查',
    description: reviewSummary.value ? `${reviewFields.value.length} 个可审查字段` : '生成草稿后查看',
    status: reviewSummary.value ? 'success' : datasetId.value ? 'process' : 'wait',
  },
  {
    key: 'approve',
    title: '批准领域',
    description: dataset.value?.domain_pack_status || '审查后批准',
    status: dataset.value?.domain_pack_status === 'approved' ? 'success' : reviewSummary.value ? 'process' : 'wait',
  },
  {
    key: 'warehouse',
    title: '生成可查询数据',
    description: dataset.value?.status === 'queryable' ? '已可查询' : '批准后建仓',
    status: dataset.value?.status === 'queryable' ? 'success' : dataset.value?.domain_pack_status === 'approved' ? 'process' : 'wait',
  },
  {
    key: 'query',
    title: '试查',
    description: queryResult.value ? statusLabel(queryResult.value.status) : '建仓后试查',
    status: queryResult.value ? 'success' : dataset.value?.status === 'queryable' ? 'process' : 'wait',
  },
]);
```

- [ ] **Step 2: 在模板顶部加入步骤条**

在上传卡片 warning alert 后加入：

```vue
<el-steps class="dataset-steps" :active="datasetSteps.findIndex((step) => step.status !== 'success')" finish-status="success">
  <el-step
    v-for="step in datasetSteps"
    :key="step.key"
    :title="step.title"
    :description="step.description"
    :status="step.status"
  />
</el-steps>
```

- [ ] **Step 3: 折叠原始 JSON 区域**

把现有 `v-if="dataset"` 的 `dataset-json-grid` 包裹为：

```vue
<el-collapse v-if="dataset" class="dataset-debug-collapse">
  <el-collapse-item title="调试数据" name="debug">
    <section class="dataset-json-grid">
      <!-- 保留原有 工作表与表头、必需字段、风险字段、数据概况、表格检查、审查摘要、前端操作审计记录 article -->
    </section>
  </el-collapse-item>
</el-collapse>
```

保留工作表、缺失字段、风险字段和审查摘要的可读内容；不要删除原始 JSON，只把它默认折叠。

- [ ] **Step 4: 增加上传步骤 CSS**

在 `frontend/src/style.css` 加入：

```css
.dataset-steps {
  margin: 10px 0 16px;
  padding: 12px;
  border: 1px solid #dfe8ec;
  border-radius: 8px;
  background: #ffffff;
}

.dataset-debug-collapse {
  margin-top: 16px;
  border: 0;
}

.dataset-debug-collapse .el-collapse-item__header {
  height: 42px;
  padding: 0 12px;
  border: 1px solid #dfe7ec;
  border-radius: 8px;
  background: #ffffff;
  color: #304650;
  font-size: 14px;
  font-weight: 800;
}

.dataset-debug-collapse .el-collapse-item__wrap {
  border: 0;
  background: transparent;
}

.dataset-debug-collapse .el-collapse-item__content {
  padding: 10px 0 0;
}
```

- [ ] **Step 5: 运行构建**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: 提交 Task 7**

Run:

```bash
git add frontend/src/components/DatasetIngestionPanel.vue frontend/src/style.css
git commit -m "feat: organize dataset ingestion steps"
```

Expected: commit succeeds.

---

### Task 8: 更新中文前端 README

**Files:**
- Modify: `frontend/README.md`

- [ ] **Step 1: 更新默认态和演示数据说明**

在 `frontend/README.md` 的“数据来源”段落替换演示数据 bullet：

```markdown
- 演示数据：页面默认不展示演示结果。用户必须点击“查看演示数据”后，前端才会加载 `src/mock/demo_run.json`，并在界面上标记为演示数据。演示数据只用于汇报、调试和本地说明，不代表已调用后端。
```

- [ ] **Step 2: 更新 API 模式说明**

把 API 模式中的运行选项说明替换为：

```markdown
API 模式优先从 `/api/workbench/options` 读取受控选项，包括排位范围、排序方式、规则提取方式、证据回答方式和 LLM 模型。后端不可用时，前端只使用保守 fallback 渲染控件，并显示连接状态；不会把 fallback 或 mock 伪装成真实查询结果。
```

- [ ] **Step 3: 增加候选确认说明**

在主查询页面说明后追加：

```markdown
当后端返回 `candidates_to_confirm` 时，主查询页会展示“确认后再查”。前端只提交上一轮响应里的 `candidate_id` 到 `confirmed_candidates`，不会把用户第二轮自由文本编译成 SQL 或 hard filter。没有 `candidate_id` 的偏好只展示说明，不能在前端确认执行。
```

- [ ] **Step 4: 更新上传流程说明**

把上传数据集段落改为：

```markdown
“上传与审查”工作区按 `上传文件 -> 生成草稿 -> 字段审查 -> 批准领域 -> 生成可查询数据 -> 试查` 展示现有后端能力。原始 JSON 响应默认折叠到“调试数据”，首屏优先展示工作表、缺失字段、风险字段、审查摘要、操作审计和试查状态。
```

- [ ] **Step 5: 运行文档检查**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: 提交 Task 8**

Run:

```bash
git add frontend/README.md
git commit -m "docs: update frontend workbench behavior"
```

Expected: commit succeeds.

---

### Task 9: 完整前端验证

**Files:**
- No source changes unless validation finds a defect.

- [ ] **Step 1: 运行单元测试和生产构建**

Run:

```bash
cd frontend && npm run test:unit && npm run build
```

Expected: both commands PASS.

- [ ] **Step 2: 启动前端开发服务器**

Run:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Expected: Vite prints a local URL, usually `http://127.0.0.1:5173/`. Keep this session running until verification finishes.

- [ ] **Step 3: 浏览器验证默认空态**

Use Browser plugin when available; otherwise use Playwright.

Flow:

```text
app loads -> query workspace renders -> no mock university appears -> start query button is visible
```

Checks:

- Page URL is the Vite local URL.
- DOM contains `开始查询` and `查看演示数据`.
- DOM does not contain `中山大学` before clicking demo.
- No Vite/Vue error overlay.
- Console has no relevant error.
- Screenshot shows the run bar, form and empty result state in the first viewport.

- [ ] **Step 4: 浏览器验证显式演示**

Flow:

```text
click 查看演示数据 -> demo result loads -> demo status is visible
```

Checks:

- DOM contains at least one demo result such as `中山大学`.
- DOM contains `演示数据` or equivalent demo tag.
- Result cards and quick stats do not overlap.

- [ ] **Step 5: 浏览器验证移动布局**

Set viewport to a mobile width such as `390x844`.

Checks:

- Page scrolls naturally.
- Run bar actions are visible and not clipped.
- Form controls do not overlap.
- Result empty/demo state stays below the form and can be reached by scrolling.

- [ ] **Step 6: 确认请求体形状**

If backend is available, use DevTools/network or a temporary Playwright route to inspect `/workbench/query`.

Expected request for confirm rerun:

```json
{
  "confirmed_candidates": ["candidate_id_from_previous_response"]
}
```

The request must not contain newly parsed free-form second-turn text as SQL or a hard rule.

- [ ] **Step 7: 修复验证中发现的缺陷**

If any check fails, make the smallest code change, rerun:

```bash
cd frontend && npm run test:unit && npm run build
```

Then repeat the failing browser check.

- [ ] **Step 8: 最终提交验证修复**

Only if Step 7 changed files:

```bash
git add frontend/src frontend/README.md frontend/package.json
git commit -m "fix: polish frontend workbench validation"
```

Expected: commit succeeds if changes were made. If no changes were needed, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage: Task 1-2 cover default empty state, explicit demo and backend options; Task 3-6 cover result-priority layout and fixed run button; Task 5 covers `candidate_id` confirmation; Task 7 covers upload steps; Task 8 covers docs; Task 9 covers rendered verification.
- Boundary check: no task adds recommendation logic, frontend SQL generation, schema/value candidate selector, or backend verifier relaxation.
- Test path: utility behavior is covered by Node `node:test`; UI rendering is covered by `npm run build` plus browser validation.
- Commit path: each task stages only files owned by that task; `.superpowers/` remains untracked and must not be committed.
