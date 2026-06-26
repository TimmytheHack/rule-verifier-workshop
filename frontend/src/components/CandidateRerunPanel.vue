<script setup>
import { computed, ref, watch } from 'vue';
import { Refresh } from '@element-plus/icons-vue';

import { splitCandidateConfirmationState } from '../utils/workbenchState';

const props = defineProps({
  runData: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  canConfirm: {
    type: Boolean,
    default: true,
  },
  disabledReason: {
    type: String,
    default: '当前查询上下文已变化，请重新查询后再确认。',
  },
});

const emit = defineEmits(['confirm']);

const selectedCandidateIds = ref([]);
const candidateState = computed(() => splitCandidateConfirmationState(props.runData));
const selectableCandidates = computed(() => candidateState.value.confirmable);
const blockedCandidates = computed(() => candidateState.value.blocked);
const hasSelectableCandidates = computed(() => selectableCandidates.value.length > 0);
const hasCandidates = computed(() => (
  hasSelectableCandidates.value || blockedCandidates.value.length > 0
));
const panelTitle = computed(() => (hasSelectableCandidates.value ? '可确认条件' : '仅提示'));
const panelCopy = computed(() => {
  if (!hasSelectableCandidates.value) {
    return '这些条件没有系统生成的 candidate_id，不会被前端提交确认。';
  }
  return props.canConfirm ? '只提交后端生成的 candidate_id。' : props.disabledReason;
});
const selectableCandidateIds = computed(() => new Set(
  selectableCandidates.value.map((candidate) => candidate.confirmationId),
));
const selectedConfirmableIds = computed(() => (
  selectedCandidateIds.value.filter((candidateId) => selectableCandidateIds.value.has(candidateId))
));
const candidateResetKey = computed(() => JSON.stringify({
  confirmable: selectableCandidates.value.map((candidate) => [
    candidate.confirmationId,
    candidate.preference,
    candidate.label,
    candidate.reason,
  ]),
  blocked: blockedCandidates.value.map((candidate) => [
    candidate.preference,
    candidate.label,
    candidate.reason,
    candidate.field_id,
    candidate.value,
    candidate.normalized_value,
  ]),
}));

watch([candidateResetKey, () => props.canConfirm], () => {
  selectedCandidateIds.value = [];
});

function confirmSelectedCandidates() {
  if (!props.canConfirm) {
    return;
  }
  const candidateIds = selectedConfirmableIds.value;
  if (!candidateIds.length) {
    return;
  }
  emit('confirm', candidateIds);
}

function candidateTitle(candidate) {
  return (
    candidate.label
    || candidate.preference
    || candidate.value
    || candidate.normalized_value
    || candidate.confirmationId
    || '待确认项'
  );
}

function candidateSummary(candidate) {
  return candidate.reason || candidate.match_type || candidate.field_id || '确认后才会参与筛选';
}
</script>

<template>
  <el-card v-if="hasCandidates" class="workbench-card candidate-rerun-panel" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>{{ panelTitle }}</h2>
          <p class="candidate-rerun-copy">
            {{ panelCopy }}
          </p>
        </div>
        <el-button
          v-if="hasSelectableCandidates"
          :icon="Refresh"
          type="warning"
          :disabled="!canConfirm || !selectedConfirmableIds.length"
          :loading="loading"
          @click="confirmSelectedCandidates"
        >
          确认后再查
        </el-button>
      </div>
    </template>

    <el-checkbox-group
      v-if="selectableCandidates.length"
      v-model="selectedCandidateIds"
      class="candidate-checkboxes candidate-rerun-list"
    >
      <div
        v-for="candidate in selectableCandidates"
        :key="candidate.confirmationId"
        class="candidate-confirm-row candidate-rerun-row"
      >
        <el-checkbox :value="candidate.confirmationId">
          确认使用 {{ candidateTitle(candidate) }}
        </el-checkbox>
        <span>{{ candidateSummary(candidate) }}</span>
      </div>
    </el-checkbox-group>

    <div v-if="blockedCandidates.length" class="candidate-warning-list">
      <el-alert
        v-for="(candidate, index) in blockedCandidates"
        :key="`${candidate.preference || candidate.reason || candidate.label || 'blocked'}-${index}`"
        type="warning"
        :closable="false"
        show-icon
        :title="`${candidateTitle(candidate)}：缺少系统生成的 candidate_id，只展示不确认。`"
      />
    </div>
  </el-card>
</template>
