<script setup>
import { computed, reactive, watch, watchEffect } from 'vue';
import {
  buildQueryControls,
  buildWorkbenchPayload,
  summarizeDatasetCapability,
} from '../domain/queryOptions.js';

const props = defineProps({
  profile: {
    type: Object,
    required: true,
  },
  running: Boolean,
});
const emit = defineEmits(['submit', 'payload-change']);

const prompt = defineModel('prompt', { default: '' });
const userContext = reactive({});
const filterValues = reactive({});
const filterOps = reactive({});

const queryOptions = computed(() => props.profile.semantic_query_options || {});
const controls = computed(() => buildQueryControls(queryOptions.value));
const summary = computed(() => summarizeDatasetCapability(props.profile));
const currentPayload = computed(() => buildWorkbenchPayload({
  prompt: prompt.value,
  userContext,
  filterValues,
  filterOps,
  options: queryOptions.value,
}));

watchEffect(() => {
  for (const filter of controls.value.filters) {
    if (!filterOps[filter.id]) {
      filterOps[filter.id] = filter.defaultOp;
    }
  }
});

watch(currentPayload, (payload) => {
  emit('payload-change', payload);
}, { immediate: true });

function submit() {
  emit('submit', currentPayload.value);
}
</script>

<template>
  <section class="query-panel">
    <div class="status-strip" :data-status="summary.capabilityLevel"></div>
    <div class="query-panel-body">
      <div class="query-title-row">
        <div>
          <p class="kicker">Schema 驱动查询</p>
          <h2>你想怎么查？</h2>
          <p>{{ summary.label }}</p>
        </div>
        <span class="status-pill">{{ summary.readiness }}</span>
      </div>

      <div v-if="controls.requiredInputs.length" class="required-grid">
        <label v-for="input in controls.requiredInputs" :key="input.id">
          <span>{{ input.label }}</span>
          <input
            v-model="userContext[input.id]"
            :type="input.type"
            :inputmode="input.type === 'number' ? 'numeric' : undefined"
          />
        </label>
      </div>

      <label class="prompt-box">
        <span>一句话描述需求</span>
        <textarea
          v-model="prompt"
          rows="5"
          placeholder="例如：偏好低学费、城市范围或关键词"
        ></textarea>
      </label>

      <div v-if="controls.filters.length" class="schema-filter-grid">
        <label v-for="filter in controls.filters" :key="filter.id">
          <span>{{ filter.label }}</span>
          <div class="filter-input-row">
            <select v-model="filterOps[filter.id]" :aria-label="`${filter.label} 操作`">
              <option v-for="op in filter.allowedOps" :key="op" :value="op">
                {{ op }}
              </option>
            </select>
            <input
              v-model="filterValues[filter.id]"
              :type="filter.inputType"
              :placeholder="filter.sourceColumn || filter.label"
            />
          </div>
        </label>
      </div>

      <div class="field-summary">
        <span>可筛字段 {{ controls.filters.length }}</span>
        <span>可排序字段 {{ controls.sortFields.length }}</span>
      </div>

      <button class="primary-button" type="button" :disabled="running" @click="submit">
        {{ running ? '检查中' : '查询前检查' }}
      </button>
    </div>
  </section>
</template>
