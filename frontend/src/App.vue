<script setup>
import { computed, ref, watch } from 'vue';

import UserInputPanel from './components/UserInputPanel.vue';
import WorkbenchModePanel from './components/WorkbenchModePanel.vue';
import DatasetIngestionPanel from './components/DatasetIngestionPanel.vue';
import ExtractedPreferences from './components/ExtractedPreferences.vue';
import VerificationAudit from './components/VerificationAudit.vue';
import RuleSummaryCards from './components/RuleSummaryCards.vue';
import CandidateConfirmation from './components/CandidateConfirmation.vue';
import ResultTable from './components/ResultTable.vue';
import TraceDrawer from './components/TraceDrawer.vue';
import EvidenceReport from './components/EvidenceReport.vue';
import EvalSummary from './components/EvalSummary.vue';
import TokenUsagePanel from './components/TokenUsagePanel.vue';
import BeginnerDecisionPanel from './components/BeginnerDecisionPanel.vue';
import { formatApiError } from './utils/apiError';
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
  tuition_cap_yuan: null,
};
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

const runData = ref({
  ...demoRun,
  token_usage: null,
  selected_options: {
    extractor: 'regex',
    generator: 'template_evidence',
    model: 'deepseek-v4-flash',
  },
});
const activeResult = ref(null);
const traceVisible = ref(false);
const activeWorkspace = ref('query');
const mode = ref(initialDataSourceId === BUILTIN_DATA_SOURCE.id ? 'demo' : 'api');
const extractor = ref('regex');
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
const dataSourceTitle = computed(() => (
  mode.value === 'demo' ? '演示数据' : selectedDataSource.value.label
));
const dataSourceDescription = computed(() => {
  if (mode.value === 'demo') {
    return '当前显示演示结果；切到后端后使用所选数据。';
  }
  return selectedDataSource.value.description;
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

watch(uploadedDataSources, persistUploadedDataSources, { deep: true });
watch(selectedDataSourceId, persistSelectedDataSourceId);

function runDemo(runRequest, selectedOptions = {}) {
  runData.value = {
    ...demoRun,
    user_input: runRequest.user_input,
    hard_filters: runRequest.hard_filters,
    soft_preferences: runRequest.soft_preferences,
    selected_options: selectedOptions,
    token_usage: null,
  };
  apiError.value = '';
  lastRunFailed.value = false;
}

async function runWorkbench(runRequest) {
  if (mode.value === 'demo') {
    runDemo(runRequest, {
      extractor: extractor.value,
      generator: generator.value,
      model: model.value,
    });
    return;
  }

  loading.value = true;
  apiError.value = '';
  lastRunFailed.value = false;
  const source = selectedDataSource.value;
  const requestBody = {
    domain_name: source.domainName || 'admissions',
    user_input: runRequest.user_input,
    hard_filters: runRequest.hard_filters,
    soft_preferences: runRequest.soft_preferences,
    extractor: normalizedExtractor(),
    generator: generator.value,
    model: model.value,
  };
  if (source.datasetId) {
    requestBody.dataset_id = source.datasetId;
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
    runData.value = {
      ...apiPayload,
      selected_options: {
        ...(apiPayload.selected_options || {}),
        data_source: source.label,
      },
    };
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : formatApiError(error, '后端运行失败');
    lastRunFailed.value = true;
  } finally {
    loading.value = false;
  }
}

function normalizedExtractor() {
  return EXTRACTOR_ALIASES[extractor.value] || extractor.value;
}

function openTrace(result) {
  activeResult.value = result;
  traceVisible.value = true;
}

function handleDataSourceChange() {
  mode.value = 'api';
  apiError.value = '';
  lastRunFailed.value = false;
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
          <aside class="control-column">
            <UserInputPanel
              :default-hard-filters="defaultHardFilters"
              :default-soft-preferences="defaultSoftPreferences"
              :mode="mode"
              :loading="loading"
              @run="runWorkbench"
            />
            <section class="data-source-panel" aria-label="查询数据源">
              <div class="data-source-copy">
                <span class="control-label">数据源</span>
                <strong>{{ dataSourceTitle }}</strong>
                <p>{{ dataSourceDescription }}</p>
              </div>
              <div class="data-source-actions">
                <el-select
                  v-model="selectedDataSourceId"
                  class="data-source-select"
                  size="small"
                  @change="handleDataSourceChange"
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
                <el-button size="small" @click="goToUpload">
                  上传
                </el-button>
              </div>
            </section>
            <el-collapse class="advanced-collapse">
              <el-collapse-item title="高级选项" name="advanced">
                <WorkbenchModePanel
                  v-model:mode="mode"
                  v-model:extractor="extractor"
                  v-model:generator="generator"
                  v-model:model="model"
                />
              </el-collapse-item>
            </el-collapse>
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
            :deterministic-rules="runData?.deterministic_rules"
            :candidate-rules="runData?.candidate_rules"
            :not-executed-preferences="runData?.not_executed_preferences"
            :executable-rules="runData?.executable_rules"
          />
          <CandidateConfirmation
            :candidate-rules="runData?.candidate_rules"
            :confirmations="runData?.simulated_confirmations"
          />
          <ExtractedPreferences :preferences="runData?.extracted_preferences" />
          <VerificationAudit
            :grounding="runData?.attribute_grounding"
            :proposed-rules="runData?.proposed_rules"
          />
        </section>
      </el-tab-pane>
    </el-tabs>

    <TraceDrawer v-model="traceVisible" :result="activeResult" />
  </main>
</template>
