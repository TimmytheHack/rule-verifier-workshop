<script setup>
import { ref } from 'vue';
import { DocumentChecked, WarningFilled } from '@element-plus/icons-vue';

import UserInputPanel from './components/UserInputPanel.vue';
import WorkbenchModePanel from './components/WorkbenchModePanel.vue';
import ExtractedPreferences from './components/ExtractedPreferences.vue';
import VerificationAudit from './components/VerificationAudit.vue';
import RuleSummaryCards from './components/RuleSummaryCards.vue';
import CandidateConfirmation from './components/CandidateConfirmation.vue';
import ResultTable from './components/ResultTable.vue';
import TraceDrawer from './components/TraceDrawer.vue';
import EvidenceReport from './components/EvidenceReport.vue';
import EvalSummary from './components/EvalSummary.vue';
import TokenUsagePanel from './components/TokenUsagePanel.vue';
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

const runData = ref(null);
const activeResult = ref(null);
const traceVisible = ref(false);
const mode = ref('demo');
const extractor = ref('regex');
const generator = ref('template_evidence');
const model = ref('deepseek-v4-flash');
const loading = ref(false);
const apiError = ref('');

const stages = [
  '基础信息',
  '偏好解析',
  '字段接地',
  '规则解析',
  '规则审查',
  '确定性规则',
  '待确认规则',
  '不可执行偏好',
  '最终可执行规则',
  '筛选结果',
  'Trace',
  '证据回答',
  '当前审计',
];

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
    const response = await fetch('/api/workbench/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
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
      throw new Error(apiPayload.detail || 'API 模式运行失败');
    }
    runData.value = apiPayload;
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : 'API 模式运行失败';
  } finally {
    loading.value = false;
  }
}

function openTrace(result) {
  activeResult.value = result;
  traceVisible.value = true;
}
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <div>
        <p class="eyebrow">偏好到规则验证</p>
        <h1>偏好到规则验证工作台</h1>
        <p class="header-copy">
          只展示现有管线输出：抽取、属性对齐、验证、提升、执行、行级追踪与评估对比。
        </p>
      </div>
      <div class="header-tags" aria-label="技术栈">
        <el-tag size="large" effect="plain">Vue 3</el-tag>
        <el-tag size="large" effect="plain" type="success">Vite</el-tag>
        <el-tag size="large" effect="plain" type="warning">Element Plus</el-tag>
      </div>
    </header>

    <el-alert
      class="safety-alert"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #title>
        本前端仅可视化 mock/pipeline 输出，不新增推荐逻辑，不推断新规则；不可执行偏好必须保留展示。
      </template>
    </el-alert>

    <WorkbenchModePanel
      v-model:mode="mode"
      v-model:extractor="extractor"
      v-model:generator="generator"
      v-model:model="model"
    />

    <UserInputPanel
      :default-hard-filters="defaultHardFilters"
      :default-soft-preferences="defaultSoftPreferences"
      :mode="mode"
      :loading="loading"
      @run="runWorkbench"
    />

    <el-alert
      v-if="apiError"
      class="safety-alert"
      type="error"
      :closable="false"
      show-icon
      :title="apiError"
    />

    <section class="pipeline-strip" aria-label="管线阶段">
      <span v-for="stage in stages" :key="stage" class="stage-pill">
        {{ stage }}
      </span>
    </section>

    <el-empty
      v-if="!runData"
      class="empty-run"
      description="点击“运行规则验证”加载演示数据或调用后端 API"
    />

    <template v-else>
      <TokenUsagePanel
        :token-usage="runData.token_usage"
        :mode="mode"
        :selected-options="runData.selected_options"
      />

      <ExtractedPreferences :preferences="runData.extracted_preferences" />

      <VerificationAudit
        :grounding="runData.attribute_grounding"
        :proposed-rules="runData.proposed_rules"
      />

      <RuleSummaryCards
        :deterministic-rules="runData.deterministic_rules"
        :candidate-rules="runData.candidate_rules"
        :not-executed-preferences="runData.not_executed_preferences"
        :executable-rules="runData.executable_rules"
      />

      <CandidateConfirmation
        :candidate-rules="runData.candidate_rules"
        :confirmations="runData.simulated_confirmations"
      />

      <ResultTable
        :results="runData.top_results"
        :total="runData.result_count"
        @view-trace="openTrace"
      />

      <EvidenceReport :report="runData.natural_language_report" />

      <EvalSummary
        :run-data="runData"
      />
    </template>

    <TraceDrawer v-model="traceVisible" :result="activeResult" />

    <footer class="app-footer">
      <el-icon><DocumentChecked /></el-icon>
      <span>页面标签：规则验证结果，不是最终志愿建议。</span>
      <el-icon class="footer-warning"><WarningFilled /></el-icon>
    </footer>
  </main>
</template>
