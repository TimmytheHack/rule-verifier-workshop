<script setup>
import { computed, ref, watch } from 'vue';

import TraceDrawer from './components/TraceDrawer.vue';
import QueryWorkspace from './components/workspaces/QueryWorkspace.vue';
import ImportWorkspace from './components/workspaces/ImportWorkspace.vue';
import ReviewWorkspace from './components/workspaces/ReviewWorkspace.vue';
import EvidenceDebugWorkspace from './components/workspaces/EvidenceDebugWorkspace.vue';
import {
  BUILTIN_ADMISSIONS_SOURCE,
  createUploadedAdmissionsSource,
  shouldUseUploadedAdmissionsPreflight,
} from './domain/admissionsAdapter';
import { formatApiError } from './utils/apiError';
import {
  browserStorage,
  loadSelectedDataSourceId,
  loadUploadedDataSources,
  mergeUploadedDataSource,
  persistSelectedDataSourceId,
  persistUploadedDataSources,
} from './utils/dataSourceRegistry';
import {
  buildConfirmedWorkbenchRequest,
  buildPreflightConfirmedWorkbenchRequest,
  buildWorkbenchPreflightRequest,
  buildWorkbenchRequest,
} from './utils/workbenchRequests';
import {
  boundarySelectionsFromPreflight,
  candidateConfirmationSummary,
  createEmptyPreflightState,
  createEmptyWorkbenchState,
  isCurrentPreflight,
  mergeDemoRun,
  splitPreflightBoundarySelections,
  uniqueUnusedPreferences,
} from './utils/workbenchState';
import {
  firstOptionValue,
  normalizeWorkbenchOptions,
} from './utils/workbenchOptions';
import { normalizeRunBarStatus } from './utils/workbenchRunBar';
import { primaryWorkbenchRunLabel } from './utils/workbenchUiState';
import {
  canRerunConfirmedRequest,
  defaultWorkbenchMode,
  describeDataSourceState,
  isActiveWorkbenchResponse,
  resultRowsForDisplay,
  shouldShowOptionsLoadError,
} from './utils/workbenchPresentation';
import demoRun from './mock/demo_run.json';

const defaultHardFilters = {
  source_province: '广东',
  subject_type: '物理',
  reselected_subjects: ['化学', '生物'],
  user_rank: 32000,
  major_keyword: null,
  preferred_cities: [],
  tuition_cap_yuan: null,
};
const defaultSoftPreferences = {
  prompt: '想学计算机，最好在广州深圳，学校稳一点，不想去太贵的中外合作。',
  safety_margin_percent: null,
  rank_window_label: null,
  rank_window_lower_percent: null,
  rank_window_upper_percent: null,
  sort_mode: null,
  tuition_cap_yuan: null,
};
const workbenchOptions = ref(normalizeWorkbenchOptions(null));
const optionsLoadError = ref('');
const BUILTIN_DATA_SOURCE = BUILTIN_ADMISSIONS_SOURCE;
const DEFAULT_DEV_ACTOR_TOKEN = import.meta.env.DEV ? 'operator-token' : '';
const EXTRACTOR_ALIASES = {
  deepseek_slots: 'deepseek',
};
const initialUploadedDataSources = loadUploadedDataSources();
const initialDataSourceId = loadSelectedDataSourceId({ sources: initialUploadedDataSources });

const runData = ref(createEmptyWorkbenchState({
  selected_options: {
    extractor: 'hybrid',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  },
}));
const preflightState = ref(createEmptyPreflightState());
const lastRunRequest = ref(null);
const lastRequestContext = ref(null);
const activeWorkbenchRequestId = ref(0);
const activeResult = ref(null);
const traceVisible = ref(false);
const activeWorkspace = ref('query');
const inputDraftSignature = ref('');
const mode = ref(defaultWorkbenchMode());
const extractor = ref('hybrid');
const generator = ref('template_evidence');
const model = ref('deepseek-v4-flash');
const loading = ref(false);
const apiError = ref('');
const lastRunFailed = ref(false);
const uploadedDataSources = ref(initialUploadedDataSources);
const selectedDataSourceId = ref(initialDataSourceId);

const resultRows = computed(() => resultRowsForDisplay(runData.value));
const dataSourceOptions = computed(() => [
  BUILTIN_DATA_SOURCE,
  ...uploadedDataSources.value,
]);
const selectedDataSource = computed(() => (
  dataSourceOptions.value.find((source) => source.id === selectedDataSourceId.value)
  || BUILTIN_DATA_SOURCE
));
const dataSourceDescription = computed(() => {
  return describeDataSourceState({
    mode: mode.value,
    selectedDataSource: selectedDataSource.value,
    runData: runData.value,
  });
});
const dataSourceTag = computed(() => {
  if (mode.value === 'demo') return { type: 'info', label: '演示' };
  if (selectedDataSource.value.datasetId) return { type: 'success', label: '上传表格' };
  return { type: 'warning', label: '内置' };
});
const quickStats = computed(() => {
  const data = runData.value || {};
  const confirmationSummary = candidateConfirmationSummary(data);
  return [
    { label: '处理状态', value: statusLabel(data.status || 'ok'), tone: data.status || 'ok' },
    { label: '可看结果', value: data.result_count ?? 0, tone: 'ok' },
    { label: '已用条件', value: data.executable_rules?.length || data.executed_filters?.length || 0, tone: 'ok' },
    { label: '可确认', value: confirmationSummary.confirmableCount, tone: 'needs_confirmation' },
    { label: '仅提示', value: confirmationSummary.warningOnlyCount, tone: 'needs_confirmation' },
    { label: '未参与', value: uniqueUnusedPreferences(data).length, tone: 'blocked' },
  ];
});
const runBarStatus = computed(() => normalizeRunBarStatus({
  loading: loading.value,
  lastRunFailed: lastRunFailed.value,
  runData: runData.value,
}));
const canConfirmCandidates = computed(() => (
  mode.value === 'api'
  && lastRequestContext.value?.mode === mode.value
  && lastRequestContext.value?.dataSourceId === selectedDataSourceId.value
  && (
    !lastRequestContext.value?.inputSignature
    || lastRequestContext.value.inputSignature === inputDraftSignature.value
  )
  && Boolean(lastRequestContext.value?.requestBody)
));
const shouldUsePreflight = computed(() => shouldUseUploadedPreflightForSource(selectedDataSource.value));
const currentPreflightReady = computed(() => isCurrentPreflight({
  preflightState: preflightState.value,
  inputSignature: inputDraftSignature.value,
}));
const currentPreflightCanQuery = computed(() => (
  currentPreflightReady.value
  && ['ready', 'needs_confirmation'].includes(preflightState.value.response?.status)
));
const displayedRunBarStatus = computed(() => {
  if (loading.value && shouldUsePreflight.value && !currentPreflightCanQuery.value) {
    return { type: 'warning', label: '预检中' };
  }
  return runBarStatus.value;
});
const primaryRunLabel = computed(() => {
  return primaryWorkbenchRunLabel({
    loading: loading.value,
    shouldUsePreflight: shouldUsePreflight.value,
    currentPreflightCanQuery: currentPreflightCanQuery.value,
    currentPreflightReady: currentPreflightReady.value,
    mode: mode.value,
  });
});

watch(uploadedDataSources, (value) => persistUploadedDataSources(undefined, value), { deep: true });
watch(selectedDataSourceId, (value) => persistSelectedDataSourceId(undefined, value));
watch(mode, handleModeChange, { immediate: true });

function runDemo(runRequest = lastRunRequest.value, selectedOptions = {}) {
  clearLastRequestContext();
  clearPreflightState();
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

function showDemoRun() {
  mode.value = 'demo';
  runDemo();
}

async function runWorkbench(runRequest) {
  lastRunRequest.value = runRequest;
  if (mode.value === 'demo') {
    runDemo(runRequest);
    return;
  }

  loading.value = true;
  apiError.value = '';
  lastRunFailed.value = false;
  const requestId = nextWorkbenchRequestId();
  const requestDataSourceId = selectedDataSourceId.value;
  const requestMode = mode.value;
  const source = selectedDataSource.value;
  const inputSignature = runRequest.form_signature || inputDraftSignature.value;
  lastRequestContext.value = null;
  if (
    shouldUseUploadedPreflightForSource(source)
    && !hasRunnableCurrentPreflight(inputSignature)
  ) {
    await requestPreflight({
      runRequest,
      requestId,
      requestDataSourceId,
      requestMode,
      source,
      inputSignature,
    });
    return;
  }

  let requestBody = buildWorkbenchRequest({
    source,
    runRequest,
    extractor: normalizedExtractor(),
    generator: generator.value,
    model: model.value,
  });
  if (shouldUseUploadedPreflightForSource(source)) {
    const boundarySelections = splitPreflightBoundarySelections(
      preflightState.value.response,
      preflightState.value.selections,
    );
    requestBody = buildPreflightConfirmedWorkbenchRequest(requestBody, {
      preflightId: preflightState.value.response?.preflight_id,
      confirmedBoundaries: boundarySelections.confirmed_boundaries,
      disabledBoundaries: boundarySelections.disabled_boundaries,
    });
  }
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
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    lastRequestContext.value = {
      requestBody,
      dataSourceId: requestDataSourceId,
      mode: requestMode,
      inputSignature,
    };
    clearPreflightState();
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
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '后端运行失败');
    lastRunFailed.value = true;
  } finally {
    if (requestId === activeWorkbenchRequestId.value) {
      loading.value = false;
    }
  }
}

async function requestPreflight({
  runRequest,
  requestId,
  requestDataSourceId,
  requestMode,
  source,
  inputSignature,
}) {
  const requestBody = buildWorkbenchPreflightRequest({
    source,
    runRequest,
    model: model.value,
  });
  if (!requestBody) {
    apiError.value = '当前数据源不需要查询前检查。';
    lastRunFailed.value = true;
    loading.value = false;
    return;
  }
  clearPreflightState();
  try {
    const response = await fetch('/workbench/preflight', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify(requestBody),
    });
    const apiPayload = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(apiPayload, '查询前检查失败'));
    }
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    preflightState.value = createEmptyPreflightState({
      response: apiPayload,
      inputSignature,
      selections: boundarySelectionsFromPreflight(apiPayload),
    });
    runData.value = createEmptyWorkbenchState({
      status: apiPayload.status || 'needs_confirmation',
      warnings: apiPayload.warnings || [],
      selected_options: {
        data_source: source.label,
      },
      frontend_state: {
        source: 'preflight',
        is_explicit_demo: false,
        options_source: workbenchOptions.value.source,
      },
    });
  } catch (error) {
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '查询前检查失败');
    lastRunFailed.value = true;
  } finally {
    if (requestId === activeWorkbenchRequestId.value) {
      loading.value = false;
    }
  }
}

async function rerunWithConfirmedCandidates(candidateIds) {
  if (!canRerunConfirmedRequest({
    context: lastRequestContext.value,
    candidateIds,
    currentMode: mode.value,
    selectedDataSourceId: selectedDataSourceId.value,
    currentInputSignature: inputDraftSignature.value,
  })) {
    apiError.value = '查询条件已变化，请先重新查询后再确认。';
    return;
  }
  loading.value = true;
  apiError.value = '';
  lastRunFailed.value = false;
  const requestId = nextWorkbenchRequestId();
  const requestDataSourceId = selectedDataSourceId.value;
  const requestMode = mode.value;
  const source = selectedDataSource.value;
  const requestBody = buildConfirmedWorkbenchRequest(lastRequestContext.value.requestBody, candidateIds);
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
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    lastRequestContext.value = {
      requestBody,
      dataSourceId: requestDataSourceId,
      mode: requestMode,
      inputSignature: inputDraftSignature.value,
    };
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
    if (!isActiveWorkbenchResponse({
      requestId,
      activeRequestId: activeWorkbenchRequestId.value,
      requestDataSourceId,
      selectedDataSourceId: selectedDataSourceId.value,
      requestMode,
      currentMode: mode.value,
    })) {
      return;
    }
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '确认后查询失败');
    lastRunFailed.value = true;
  } finally {
    if (requestId === activeWorkbenchRequestId.value) {
      loading.value = false;
    }
  }
}

function normalizedExtractor() {
  return EXTRACTOR_ALIASES[extractor.value] || extractor.value;
}

function shouldUseUploadedPreflightForSource(source) {
  return shouldUseUploadedAdmissionsPreflight(source, mode.value);
}

function hasRunnableCurrentPreflight(inputSignature) {
  return isCurrentPreflight({
    preflightState: preflightState.value,
    inputSignature,
  }) && ['ready', 'needs_confirmation'].includes(preflightState.value.response?.status);
}

function openTrace(result) {
  activeResult.value = result;
  traceVisible.value = true;
}

function handleDataSourceChange(value) {
  if (value && dataSourceOptions.value.some((source) => source.id === value)) {
    selectedDataSourceId.value = value;
  }
  clearLastRequestContext();
  clearPreflightState();
  mode.value = 'api';
  apiError.value = '';
  lastRunFailed.value = false;
}

function handleInputDraftChange(signature) {
  if ((signature || '') !== inputDraftSignature.value) {
    clearPreflightState();
  }
  inputDraftSignature.value = signature || '';
}

function updatePreflightSelection({ confirmationId, optionId }) {
  if (!confirmationId) return;
  preflightState.value = {
    ...preflightState.value,
    selections: {
      ...preflightState.value.selections,
      [confirmationId]: optionId,
    },
  };
}

function goToUpload() {
  activeWorkspace.value = 'dataset';
}

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

function authHeaders() {
  let token = DEFAULT_DEV_ACTOR_TOKEN;
  try {
    token = browserStorage()?.getItem('actor_token') || DEFAULT_DEV_ACTOR_TOKEN;
  } catch {
    token = DEFAULT_DEV_ACTOR_TOKEN;
  }
  return token ? { 'X-Actor-Token': token } : {};
}

async function fetchWorkbenchOptions() {
  if (mode.value !== 'api') {
    optionsLoadError.value = '';
    return;
  }
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
    if (mode.value !== 'api') {
      optionsLoadError.value = '';
      return;
    }
    workbenchOptions.value = normalizeWorkbenchOptions(null);
    optionsLoadError.value = error instanceof Error ? error.message : '后端选项加载失败';
    ensureSelectedRuntimeOptions();
  }
}

function handleModeChange(value) {
  if (value === 'demo') {
    clearLastRequestContext();
    clearPreflightState();
    optionsLoadError.value = '';
  }
  fetchWorkbenchOptions();
}

function clearPreflightState() {
  preflightState.value = createEmptyPreflightState();
}

function clearLastRequestContext() {
  lastRequestContext.value = null;
  activeWorkbenchRequestId.value += 1;
  loading.value = false;
}

function nextWorkbenchRequestId() {
  activeWorkbenchRequestId.value += 1;
  return activeWorkbenchRequestId.value;
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

function statusLabel(status) {
  const labels = {
    idle: '待查询',
    ready: '可查询',
    ok: '通过',
    needs_confirmation: '待确认',
    no_results: '无结果',
    blocked: '已阻断',
    error: '错误',
  };
  return labels[status] || status;
}
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <div>
        <h1>招生筛选助手</h1>
        <p class="header-copy">填排位、专业和城市，查看哪些结果通过了数据筛选。</p>
      </div>
      <el-tag size="large" effect="plain" type="warning">仅做筛选</el-tag>
    </header>

    <el-tabs v-model="activeWorkspace" class="workspace-tabs">
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

      <el-tab-pane label="导入数据" name="dataset">
        <ImportWorkspace
          :active-source="selectedDataSource"
          :auth-headers="authHeaders"
          @source-ready="activateUploadedSource"
          @open-review="activeWorkspace = 'review'"
        />
      </el-tab-pane>

      <el-tab-pane label="字段审查" name="review">
        <ReviewWorkspace
          :selected-data-source="selectedDataSource"
          @source-ready="activateUploadedSource"
        />
      </el-tab-pane>

      <el-tab-pane label="证据调试" name="details">
        <EvidenceDebugWorkspace :run-data="runData" />
      </el-tab-pane>
    </el-tabs>

    <TraceDrawer v-model="traceVisible" :result="activeResult" />
  </main>
</template>
