<script setup>
import { computed, ref, watch } from 'vue';

import UserInputPanel from './components/UserInputPanel.vue';
import WorkbenchRunBar from './components/WorkbenchRunBar.vue';
import PreflightPanel from './components/PreflightPanel.vue';
import DatasetIngestionPanel from './components/DatasetIngestionPanel.vue';
import ExtractedPreferences from './components/ExtractedPreferences.vue';
import VerificationAudit from './components/VerificationAudit.vue';
import RuleSummaryCards from './components/RuleSummaryCards.vue';
import CandidateConfirmation from './components/CandidateConfirmation.vue';
import CandidateRerunPanel from './components/CandidateRerunPanel.vue';
import ResultTable from './components/ResultTable.vue';
import TraceDrawer from './components/TraceDrawer.vue';
import EvidenceReport from './components/EvidenceReport.vue';
import EvalSummary from './components/EvalSummary.vue';
import TokenUsagePanel from './components/TokenUsagePanel.vue';
import BeginnerDecisionPanel from './components/BeginnerDecisionPanel.vue';
import { formatApiError } from './utils/apiError';
import {
  buildConfirmedWorkbenchRequest,
  buildPreflightConfirmedWorkbenchRequest,
  buildWorkbenchPreflightRequest,
  buildWorkbenchRequest,
} from './utils/workbenchRequests';
import {
  boundarySelectionsFromPreflight,
  createEmptyPreflightState,
  createEmptyEvidenceReport,
  createEmptyWorkbenchState,
  isCurrentPreflight,
  mergeDemoRun,
  splitPreflightBoundarySelections,
} from './utils/workbenchState';
import {
  firstOptionValue,
  normalizeWorkbenchOptions,
} from './utils/workbenchOptions';
import { normalizeRunBarStatus } from './utils/workbenchRunBar';
import {
  canRerunConfirmedRequest,
  defaultWorkbenchMode,
  describeDataSourceState,
  isActiveWorkbenchResponse,
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
const BUILTIN_DATA_SOURCE = {
  id: 'builtin_admissions',
  type: 'builtin',
  datasetId: null,
  domainName: 'admissions',
  label: '内置招生数据',
  description: '使用仓库内置 admissions 数据。',
};
const DATA_SOURCES_STORAGE_KEY = 'szu_uploaded_data_sources';
const SELECTED_SOURCE_STORAGE_KEY = 'szu_selected_data_source';
const DEFAULT_DEV_ACTOR_TOKEN = import.meta.env.DEV ? 'operator-token' : '';
const EXTRACTOR_ALIASES = {
  deepseek_slots: 'deepseek',
};
const initialUploadedDataSources = loadUploadedDataSources();
const initialDataSourceId = loadSelectedDataSourceId(initialUploadedDataSources);

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
const inputPanelRef = ref(null);
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

const resultRows = computed(() => (
  runData.value?.items?.length ? runData.value.items : runData.value?.top_results || []
));
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
  return [
    { label: '处理状态', value: statusLabel(data.status || 'ok'), tone: data.status || 'ok' },
    { label: '可看结果', value: data.result_count ?? 0, tone: 'ok' },
    { label: '已用条件', value: data.executable_rules?.length || data.executed_filters?.length || 0, tone: 'ok' },
    { label: '待确认', value: data.candidate_rules?.length || data.candidates_to_confirm?.length || 0, tone: 'needs_confirmation' },
    { label: '未参与', value: data.not_executed_preferences?.length || data.unexecuted_preferences?.length || data.no_schema_field_preferences?.length || 0, tone: 'blocked' },
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
const shouldUsePreflight = computed(() => (
  mode.value === 'api'
  && selectedDataSource.value?.type === 'uploaded'
  && selectedDataSource.value?.domainName === 'admissions'
));
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
  if (loading.value) {
    return currentPreflightCanQuery.value ? '正在查询' : '正在预检';
  }
  if (!shouldUsePreflight.value) {
    return mode.value === 'api' ? '开始查询' : '演示结果';
  }
  if (currentPreflightCanQuery.value) {
    return '确认后查询';
  }
  return currentPreflightReady.value ? '重新预检' : '先做预检';
});

watch(uploadedDataSources, persistUploadedDataSources, { deep: true });
watch(selectedDataSourceId, persistSelectedDataSourceId);
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
  return mode.value === 'api'
    && source?.type === 'uploaded'
    && source?.domainName === 'admissions';
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

function submitCurrentForm() {
  inputPanelRef.value?.submitRun?.();
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
  const source = normalizeUploadedDataSource(payload);
  if (!source) {
    return;
  }
  uploadedDataSources.value = [
    source,
    ...uploadedDataSources.value.filter((item) => item.id !== source.id),
  ].slice(0, 5);
  clearLastRequestContext();
  clearPreflightState();
  selectedDataSourceId.value = source.id;
  mode.value = 'api';
  activeWorkspace.value = 'query';
  apiError.value = '';
  lastRunFailed.value = false;
}

function authHeaders() {
  const token = localStorageSafe()?.getItem('actor_token') || DEFAULT_DEV_ACTOR_TOKEN;
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

function loadUploadedDataSources() {
  try {
    const raw = localStorageSafe()?.getItem(DATA_SOURCES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((source) => source?.id && source?.datasetId && source?.domainName)
      : [];
  } catch {
    return [];
  }
}

function loadSelectedDataSourceId(sources = []) {
  const saved = localStorageSafe()?.getItem(SELECTED_SOURCE_STORAGE_KEY);
  if (
    saved === BUILTIN_DATA_SOURCE.id
    || sources.some((source) => source.id === saved)
  ) {
    return saved;
  }
  return BUILTIN_DATA_SOURCE.id;
}

function persistUploadedDataSources(value) {
  localStorageSafe()?.setItem(DATA_SOURCES_STORAGE_KEY, JSON.stringify(value));
}

function persistSelectedDataSourceId(value) {
  localStorageSafe()?.setItem(SELECTED_SOURCE_STORAGE_KEY, value || BUILTIN_DATA_SOURCE.id);
}

function normalizeUploadedDataSource(payload) {
  const datasetId = payload?.dataset_id;
  if (!datasetId) {
    return null;
  }
  const rowCount = payload?.warehouse?.row_count || payload?.row_count || null;
  const columnCount = payload?.warehouse?.column_count || payload?.column_count || null;
  const fileName = payload?.file_name || payload?.source_name || datasetId;
  const sizeText = rowCount && columnCount
    ? `${formatNumber(rowCount)} 行，${formatNumber(columnCount)} 列`
    : '已生成可查询数据';
  return {
    id: `uploaded:${datasetId}`,
    type: 'uploaded',
    datasetId,
    domainName: payload?.domain_name || 'admissions',
    label: `上传：${fileName}`,
    description: `${sizeText}，使用上传表格查询。`,
    rowCount,
    columnCount,
    updatedAt: payload?.updated_at || new Date().toISOString(),
  };
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isNaN(number) ? value : number.toLocaleString('zh-CN');
}

function localStorageSafe() {
  return typeof window === 'undefined' ? null : window.localStorage;
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
      <el-tab-pane label="我要查询" name="query">
        <section class="workspace-panel query-workspace">
          <WorkbenchRunBar
            v-model:mode="mode"
            v-model:extractor="extractor"
            v-model:generator="generator"
            v-model:model="model"
            :selected-data-source-id="selectedDataSourceId"
            :data-source-options="dataSourceOptions"
            :data-source-tag="dataSourceTag"
            :data-source-description="dataSourceDescription"
            :extractor-options="workbenchOptions.extractors"
            :generator-options="workbenchOptions.generators"
            :model-options="workbenchOptions.models"
            :options-source="workbenchOptions.source"
            :options-error="shouldShowOptionsLoadError(mode, optionsLoadError) ? optionsLoadError : ''"
            :run-status="displayedRunBarStatus"
            :loading="loading"
            :primary-action-label="primaryRunLabel"
            @update:selected-data-source-id="handleDataSourceChange"
            @run="submitCurrentForm"
            @demo="showDemoRun"
            @upload="goToUpload"
          />
          <div class="query-main-grid">
            <aside class="control-column">
              <UserInputPanel
                ref="inputPanelRef"
                :default-hard-filters="defaultHardFilters"
                :default-soft-preferences="defaultSoftPreferences"
                :mode="mode"
                :loading="loading"
                :show-panel-actions="false"
                :rank-window-options="workbenchOptions.rank_windows"
                :sort-mode-options="workbenchOptions.sort_modes"
                @draft-change="handleInputDraftChange"
                @run="runWorkbench"
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

            <section class="result-column">
              <template v-if="!lastRunFailed">
                <PreflightPanel
                  :preflight="preflightState.response"
                  :selections="preflightState.selections"
                  @update-selection="updatePreflightSelection"
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
                    <EvidenceReport :report="runData?.natural_language_report || createEmptyEvidenceReport()" />
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
      </el-tab-pane>

      <el-tab-pane label="上传表格" name="dataset">
        <section class="workspace-panel single-scroll">
          <DatasetIngestionPanel @source-ready="activateUploadedSource" />
        </section>
      </el-tab-pane>

      <el-tab-pane label="筛选依据" name="details">
        <section class="workspace-panel detail-workspace">
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
      </el-tab-pane>
    </el-tabs>

    <TraceDrawer v-model="traceVisible" :result="activeResult" />
  </main>
</template>
