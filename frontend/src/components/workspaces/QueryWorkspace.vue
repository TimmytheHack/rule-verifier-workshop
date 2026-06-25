<script setup>
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
  'run-current-form',
  'show-demo',
  'go-import',
  'draft-change',
  'run-workbench',
  'update-preflight-selection',
  'confirm-candidates',
  'view-trace',
]);

const emitUpdateMode = (value) => emit('update:mode', value);
const emitUpdateExtractor = (value) => emit('update:extractor', value);
const emitUpdateGenerator = (value) => emit('update:generator', value);
const emitUpdateModel = (value) => emit('update:model', value);
const emitUpdateSelectedDataSourceId = (value) => emit('update:selected-data-source-id', value);
const runCurrentForm = () => emit('run-current-form');
const showDemo = () => emit('show-demo');
const goImport = () => emit('go-import');
const draftChange = (payload) => emit('draft-change', payload);
const runWorkbench = (payload) => emit('run-workbench', payload);
const updatePreflightSelection = (payload) => emit('update-preflight-selection', payload);
const confirmCandidates = (payload) => emit('confirm-candidates', payload);
const viewTrace = (payload) => emit('view-trace', payload);
</script>

<template>
  <section class="workspace-panel query-workspace c-lite-query">
    <slot
      :run-data="props.runData"
      :preflight-state="props.preflightState"
      :workbench-options="props.workbenchOptions"
      :mode="props.mode"
      :extractor="props.extractor"
      :generator="props.generator"
      :model="props.model"
      :loading="props.loading"
      :last-run-failed="props.lastRunFailed"
      :api-error="props.apiError"
      :selected-data-source-id="props.selectedDataSourceId"
      :data-source-options="props.dataSourceOptions"
      :data-source-tag="props.dataSourceTag"
      :data-source-description="props.dataSourceDescription"
      :options-load-error="props.optionsLoadError"
      :run-status="props.runStatus"
      :primary-run-label="props.primaryRunLabel"
      :quick-stats="props.quickStats"
      :result-rows="props.resultRows"
      :can-confirm-candidates="props.canConfirmCandidates"
      :default-hard-filters="props.defaultHardFilters"
      :default-soft-preferences="props.defaultSoftPreferences"
      :emit-update-mode="emitUpdateMode"
      :emit-update-extractor="emitUpdateExtractor"
      :emit-update-generator="emitUpdateGenerator"
      :emit-update-model="emitUpdateModel"
      :emit-update-selected-data-source-id="emitUpdateSelectedDataSourceId"
      :run-current-form="runCurrentForm"
      :show-demo="showDemo"
      :go-import="goImport"
      :draft-change="draftChange"
      :run-workbench="runWorkbench"
      :update-preflight-selection="updatePreflightSelection"
      :confirm-candidates="confirmCandidates"
      :view-trace="viewTrace"
    />
  </section>
</template>
