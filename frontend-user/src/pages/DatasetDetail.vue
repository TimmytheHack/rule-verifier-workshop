<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import {
  datasetProfile,
  preflightDatasetQuery,
  runDatasetQuery,
} from '../api/datasets.js';
import EvidenceSummary from '../components/EvidenceSummary.vue';
import QueryComposer from '../components/QueryComposer.vue';

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
const lastQueryPayload = ref(null);
const boundarySelections = ref({});

const boundaryConfirmations = computed(() =>
  Array.isArray(result.value?.boundary_confirmations) ? result.value.boundary_confirmations : [],
);
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
  running.value = true;
  error.value = '';
  result.value = null;
  boundarySelections.value = {};
  lastQueryPayload.value = {
    domainName: profile.value.domain_name,
    userInput: payload.user_input,
    hardFilters: payload.hard_filters,
    softPreferences: payload.soft_preferences,
    plannerMode: 'auto',
  };
  try {
    result.value = await preflightDatasetQuery({
      datasetId: props.datasetId,
      ...lastQueryPayload.value,
    });
  } catch (exc) {
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

function hasBlockingRequirement(payload) {
  return (Array.isArray(payload?.missing_requirements) ? payload.missing_requirements : [])
    .some((item) => item.blocking !== false);
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
          <h2>{{ profile.domain_name || datasetId }}</h2>
        </div>
        <span class="status-pill">{{ profile.status || '未知状态' }}</span>
      </div>
      <QueryComposer
        v-model:prompt="prompt"
        :profile="profile"
        :running="running"
        @submit="runPreflight"
      />
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
        :boundary-selections="boundarySelections"
        @select-boundary="selectBoundary"
      />
    </template>
  </section>
</template>
