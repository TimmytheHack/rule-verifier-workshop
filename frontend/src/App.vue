<script setup>
import { computed, ref } from 'vue';

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
  tuition_cap_yuan: null,
};

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
const mode = ref('demo');
const extractor = ref('regex');
const generator = ref('template_evidence');
const model = ref('deepseek-v4-flash');
const loading = ref(false);
const apiError = ref('');

const resultRows = computed(() => (
  runData.value?.items?.length ? runData.value.items : runData.value?.top_results || []
));
const quickStats = computed(() => {
  const data = runData.value || {};
  return [
    { label: '状态', value: statusLabel(data.status || 'ok'), tone: data.status || 'ok' },
    { label: '结果', value: data.result_count ?? 0, tone: 'ok' },
    { label: '已执行', value: data.executable_rules?.length || data.executed_filters?.length || 0, tone: 'ok' },
    { label: '待确认', value: data.candidate_rules?.length || data.candidates_to_confirm?.length || 0, tone: 'needs_confirmation' },
    { label: '未执行', value: data.not_executed_preferences?.length || data.unexecuted_preferences?.length || 0, tone: 'blocked' },
  ];
});

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
  try {
    const response = await fetch('/workbench/query', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({
        domain_name: 'admissions',
        user_input: runRequest.user_input,
        hard_filters: runRequest.hard_filters,
        soft_preferences: runRequest.soft_preferences,
        extractor: extractor.value,
        generator: generator.value,
        model: model.value,
      }),
    });
    const apiPayload = await response.json();
    if (!response.ok) {
      throw new Error(apiPayload.detail || '后端运行失败');
    }
    runData.value = apiPayload;
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : '后端运行失败';
  } finally {
    loading.value = false;
  }
}

function openTrace(result) {
  activeResult.value = result;
  traceVisible.value = true;
}

function authHeaders() {
  const token = window.localStorage.getItem('actor_token') || '';
  return token ? { 'X-Actor-Token': token } : {};
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
        <p class="header-copy">填排位和偏好，先看可验证筛选结果。</p>
      </div>
      <el-tag size="large" effect="plain" type="warning">不是志愿建议</el-tag>
    </header>

    <el-tabs v-model="activeWorkspace" class="workspace-tabs">
      <el-tab-pane label="开始查询" name="query">
        <section class="workspace-panel query-workspace">
          <aside class="control-column">
            <UserInputPanel
              :default-hard-filters="defaultHardFilters"
              :default-soft-preferences="defaultSoftPreferences"
              :mode="mode"
              :loading="loading"
              @run="runWorkbench"
            />
            <el-collapse class="advanced-collapse">
              <el-collapse-item title="高级设置" name="advanced">
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
          </section>

          <aside class="evidence-column">
            <BeginnerDecisionPanel :run-data="runData" />
            <el-collapse class="detail-collapse">
              <el-collapse-item title="查看证据回答" name="evidence">
                <EvidenceReport :report="runData?.natural_language_report" />
              </el-collapse-item>
              <el-collapse-item title="查看质量检查" name="audit">
                <EvalSummary :run-data="runData" />
                <TokenUsagePanel
                  :token-usage="runData?.token_usage"
                  :mode="mode"
                  :selected-options="runData?.selected_options"
                />
              </el-collapse-item>
            </el-collapse>
          </aside>
        </section>
      </el-tab-pane>

      <el-tab-pane label="上传表格" name="dataset">
        <section class="workspace-panel single-scroll">
          <DatasetIngestionPanel />
        </section>
      </el-tab-pane>

      <el-tab-pane label="查看详情" name="details">
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
