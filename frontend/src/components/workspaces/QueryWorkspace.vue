<script setup>
import { ref } from 'vue';

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

const props = defineProps({
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
  'show-demo',
  'go-import',
  'draft-change',
  'run-workbench',
  'update-preflight-selection',
  'confirm-candidates',
  'view-trace',
]);

const inputPanelRef = ref(null);

function submitCurrentForm() {
  inputPanelRef.value?.submitRun?.();
}
</script>

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

          <BeginnerDecisionPanel :run-data="runData" />

          <el-collapse class="query-evidence-collapse">
            <el-collapse-item title="筛选依据" name="evidence">
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
