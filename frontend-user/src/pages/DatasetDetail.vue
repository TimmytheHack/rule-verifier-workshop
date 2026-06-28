<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import {
  datasetProfile,
  preflightDatasetQuery,
  runDatasetQuery,
} from '../api/datasets.js';
import EvidenceSummary from '../components/EvidenceSummary.vue';
import QueryComposer from '../components/QueryComposer.vue';
import { workbenchPayloadSignature } from '../domain/queryOptions.js';

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
const executing = ref(false);
const error = ref('');
const preflightNotice = ref('');
const lastQueryPayload = ref(null);
const lastPreflightSignature = ref('');
const currentPayloadSignature = ref('');
const boundarySelections = ref({});

const boundaryConfirmations = computed(() =>
  Array.isArray(result.value?.boundary_confirmations) ? result.value.boundary_confirmations : [],
);
const profileTitle = computed(() => profile.value?.original_filename || props.datasetId);
const profileStatusLabel = computed(() => statusLabel(profile.value?.status));
const fieldLabels = computed(() => buildFieldLabels(profile.value));
const handledBoundaryCount = computed(() =>
  boundaryConfirmations.value.filter((item) => boundarySelections.value[item.confirmation_id]).length,
);
const allBoundariesHandled = computed(() =>
  handledBoundaryCount.value === boundaryConfirmations.value.length,
);
const canExecute = computed(() => {
  if (!result.value?.preflight_id || !lastQueryPayload.value) return false;
  if (hasBlockingRequirement(result.value)) return false;
  return allBoundariesHandled.value;
});

onMounted(loadProfile);

watch(
  () => props.datasetId,
  () => {
    profile.value = null;
    result.value = null;
    prompt.value = '';
    boundarySelections.value = {};
    lastQueryPayload.value = null;
    lastPreflightSignature.value = '';
    currentPayloadSignature.value = '';
    preflightNotice.value = '';
    loadProfile();
  },
);

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
  if (!profile.value?.domain_name) {
    error.value = '数据源缺少已审查 domain，无法查询。';
    return;
  }
  const submittedSignature = workbenchPayloadSignature(payload);
  currentPayloadSignature.value = submittedSignature;
  running.value = true;
  error.value = '';
  preflightNotice.value = '';
  result.value = null;
  boundarySelections.value = {};
  lastQueryPayload.value = null;
  const queryPayload = {
    domainName: profile.value.domain_name,
    userInput: payload.user_input,
    hardFilters: payload.hard_filters,
    softPreferences: payload.soft_preferences,
    plannerMode: 'auto',
  };
  try {
    const preflight = await preflightDatasetQuery({
      datasetId: props.datasetId,
      ...queryPayload,
    });
    if (currentPayloadSignature.value !== submittedSignature) {
      preflightNotice.value = '查询条件已变化，请重新运行查询前检查。';
      return;
    }
    lastQueryPayload.value = queryPayload;
    lastPreflightSignature.value = submittedSignature;
    result.value = preflight;
  } catch (exc) {
    lastPreflightSignature.value = '';
    error.value = exc.message || '查询前检查失败。';
  } finally {
    running.value = false;
  }
}

async function executeQuery() {
  if (!canExecute.value) return;
  executing.value = true;
  error.value = '';
  try {
    const confirmedBoundaries = [];
    const disabledBoundaries = [];
    for (const boundary of boundaryConfirmations.value) {
      const optionId = boundarySelections.value[boundary.confirmation_id];
      const record = {
        confirmation_id: boundary.confirmation_id,
        option_id: optionId,
      };
      if (optionId === 'do_not_use') {
        disabledBoundaries.push(record);
      } else {
        confirmedBoundaries.push(record);
      }
    }
    result.value = await runDatasetQuery({
      datasetId: props.datasetId,
      ...lastQueryPayload.value,
      preflightId: result.value.preflight_id,
      confirmedBoundaries,
      disabledBoundaries,
    });
  } catch (exc) {
    error.value = exc.message || '执行查询失败。';
  } finally {
    executing.value = false;
  }
}

function selectBoundary(confirmationId, optionId) {
  boundarySelections.value = {
    ...boundarySelections.value,
    [confirmationId]: optionId,
  };
}

function handlePayloadChange(payload) {
  const signature = workbenchPayloadSignature(payload);
  currentPayloadSignature.value = signature;
  if (!lastPreflightSignature.value || signature === lastPreflightSignature.value) {
    return;
  }
  result.value = null;
  boundarySelections.value = {};
  lastQueryPayload.value = null;
  lastPreflightSignature.value = '';
  preflightNotice.value = '查询条件已变化，请重新运行查询前检查。';
}

function hasBlockingRequirement(payload) {
  return (Array.isArray(payload?.missing_requirements) ? payload.missing_requirements : [])
    .some((item) => item.blocking !== false);
}

function statusLabel(status) {
  if (status === 'queryable') return '可查询';
  if (status === 'uploaded') return '已导入';
  if (status === 'profiled') return '已分析';
  if (status === 'needs_review') return '待审查';
  if (status === 'approved') return '已批准';
  if (status === 'blocked') return '已阻断';
  return status || '未知状态';
}

function buildFieldLabels(profilePayload) {
  const options = profilePayload?.semantic_query_options || {};
  const labels = {};
  for (const collection of [options.filters, options.sort_fields]) {
    for (const [fieldId, spec] of Object.entries(collection || {})) {
      labels[fieldId] = spec.label || spec.source_column || fieldId;
    }
  }
  for (const field of profilePayload?.fields || []) {
    if (!field?.field_id) continue;
    labels[field.field_id] = labels[field.field_id] || field.label || field.source_column || field.field_id;
  }
  return labels;
}
</script>

<template>
  <section class="page-section">
    <button class="secondary-button inline-button" type="button" @click="emit('back')">
      返回数据源
    </button>
    <p v-if="loading" class="state-line">正在读取能力摘要...</p>
    <p v-else-if="error" class="error-line">{{ error }}</p>
    <template v-else-if="profile">
      <div class="detail-heading">
        <div>
          <p class="kicker">已选择数据源</p>
          <h2>{{ profileTitle }}</h2>
        </div>
        <span class="status-pill">{{ profileStatusLabel }}</span>
      </div>
      <QueryComposer
        v-model:prompt="prompt"
        :profile="profile"
        :running="running"
        @payload-change="handlePayloadChange"
        @submit="runPreflight"
      />
      <p v-if="preflightNotice" class="state-line">{{ preflightNotice }}</p>
      <div v-if="result?.preflight_id" class="execution-bar">
        <p>
          {{ boundaryConfirmations.length ? `已处理 ${handledBoundaryCount} / ${boundaryConfirmations.length} 个确认项` : '查询前检查已完成' }}
        </p>
        <button class="primary-button" type="button" :disabled="executing || !canExecute" @click="executeQuery">
          {{ executing ? '执行中' : '执行查询' }}
        </button>
      </div>
      <EvidenceSummary
        :result="result"
        :field-labels="fieldLabels"
        :boundary-selections="boundarySelections"
        @select-boundary="selectBoundary"
      />
    </template>
  </section>
</template>
