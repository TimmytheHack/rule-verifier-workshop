<script setup>
import { computed } from 'vue';

const props = defineProps({
  result: {
    type: Object,
    default: null,
  },
  boundarySelections: {
    type: Object,
    default: () => ({}),
  },
});
const emit = defineEmits(['select-boundary']);

const recognizedFacts = computed(() => {
  const facts = safeList(props.result?.recognized_facts);
  if (facts.length) return facts;
  return safeList(props.result?.executed_filters).map((item) => ({
    label: item.label || item.field || item.id || '已执行规则',
    value: item.value ?? item.operator ?? item.id,
    executable: true,
  }));
});
const boundaryConfirmations = computed(() => safeList(props.result?.boundary_confirmations));
const pendingCandidates = computed(() => safeList(props.result?.candidates_to_confirm));
const missingRequirements = computed(() => safeList(props.result?.missing_requirements));
const notExecuted = computed(() => [
  ...safeList(props.result?.not_executable_preferences),
  ...safeList(props.result?.unexecuted_preferences),
  ...safeList(props.result?.no_schema_field_preferences),
]);
const displayResults = computed(() => {
  const top = safeList(props.result?.top_results);
  return top.length ? top : safeList(props.result?.items);
});

function safeList(value) {
  return Array.isArray(value) ? value : [];
}

function valueText(value) {
  if (Array.isArray(value)) return value.join('、');
  if (value && typeof value === 'object') return JSON.stringify(value);
  if (value === false) return '否';
  if (value === true) return '是';
  return value ?? '-';
}

function itemText(item) {
  return item.message
    || item.reason
    || item.source_text
    || item.preference
    || item.label
    || item.id
    || '未执行偏好';
}

function resultTitle(item) {
  return item.university_name
    || item.major_name
    || item.full_major_name
    || item.title
    || item.name
    || item.row_id
    || '结果项';
}
</script>

<template>
  <section v-if="result" class="evidence-panel">
    <div class="section-heading">
      <div>
        <p class="kicker">证据边界</p>
        <h2>本次检查与结果</h2>
      </div>
      <span class="status-pill">{{ result.status || '未知状态' }}</span>
    </div>

    <dl class="metric-grid">
      <div>
        <dt>已识别</dt>
        <dd>{{ recognizedFacts.length }}</dd>
      </div>
      <div>
        <dt>待确认</dt>
        <dd>{{ boundaryConfirmations.length + pendingCandidates.length }}</dd>
      </div>
      <div>
        <dt>结果数</dt>
        <dd>{{ result.result_count ?? displayResults.length }}</dd>
      </div>
    </dl>

    <div class="evidence-section">
      <h3>已识别并交给后端校验</h3>
      <ul v-if="recognizedFacts.length" class="evidence-list">
        <li
          v-for="(fact, index) in recognizedFacts"
          :key="fact.fact_id || fact.id || `${fact.label}-${fact.source}-${index}`"
        >
          <span>{{ fact.label || fact.field || fact.source }}</span>
          <strong>{{ valueText(fact.value) }}</strong>
        </li>
      </ul>
      <p v-else class="state-line">暂无已识别事实。</p>
    </div>

    <div v-if="boundaryConfirmations.length || pendingCandidates.length" class="evidence-section">
      <h3>待确认边界</h3>
      <div
        v-for="boundary in boundaryConfirmations"
        :key="boundary.confirmation_id"
        class="boundary-card"
      >
        <div>
          <strong>{{ boundary.label || boundary.source_text }}</strong>
          <p>{{ boundary.reason || '需要确认后才会进入查询。' }}</p>
        </div>
        <div class="choice-grid">
          <label
            v-for="option in boundary.options || []"
            :key="option.option_id"
            class="choice-row"
          >
            <input
              type="radio"
              :name="boundary.confirmation_id"
              :value="option.option_id"
              :checked="boundarySelections[boundary.confirmation_id] === option.option_id"
              @change="emit('select-boundary', boundary.confirmation_id, option.option_id)"
            />
            <span>{{ option.label || option.option_id }}</span>
          </label>
        </div>
      </div>
      <ul v-if="pendingCandidates.length" class="evidence-list">
        <li v-for="(candidate, index) in pendingCandidates" :key="candidate.candidate_id || candidate.id || index">
          <span>{{ candidate.source_text || candidate.label || '候选规则' }}</span>
          <strong>未确认，不执行</strong>
        </li>
      </ul>
    </div>

    <div v-if="missingRequirements.length" class="evidence-section warning-section">
      <h3>缺少必要信息</h3>
      <ul class="evidence-list">
        <li v-for="(item, index) in missingRequirements" :key="item.requirement_id || item.message || index">
          <span>{{ item.label || '缺少信息' }}</span>
          <strong>{{ item.message || item.reason }}</strong>
        </li>
      </ul>
    </div>

    <div class="evidence-section">
      <h3>未执行或不会执行的偏好</h3>
      <ul v-if="notExecuted.length" class="evidence-list">
        <li
          v-for="(item, index) in notExecuted"
          :key="`${item.source_text || item.preference || item.field_id}-${item.reason}-${index}`"
        >
          <span>{{ item.source_text || item.preference || item.field_id || '偏好' }}</span>
          <strong>{{ itemText(item) }}</strong>
        </li>
      </ul>
      <p v-else class="state-line">暂无未执行偏好。</p>
    </div>

    <div class="evidence-section">
      <h3>结果</h3>
      <div v-if="displayResults.length" class="result-list">
        <article
          v-for="(item, index) in displayResults.slice(0, 8)"
          :key="item.row_id || item.id || `${resultTitle(item)}-${index}`"
          class="result-item"
        >
          <h4>{{ resultTitle(item) }}</h4>
          <dl>
            <template v-for="(value, key) in item" :key="key">
              <dt>{{ key }}</dt>
              <dd>{{ valueText(value) }}</dd>
            </template>
          </dl>
        </article>
      </div>
      <p v-else class="state-line">还没有执行结果。</p>
    </div>
  </section>
</template>
