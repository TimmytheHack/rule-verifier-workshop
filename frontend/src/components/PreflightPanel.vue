<script setup>
import { computed } from 'vue';

const props = defineProps({
  preflight: {
    type: Object,
    default: null,
  },
  selections: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(['update-selection']);

const facts = computed(() => props.preflight?.recognized_facts || []);
const boundaries = computed(() => props.preflight?.boundary_confirmations || []);
const notExecutable = computed(() => props.preflight?.not_executable_preferences || []);
const missingRequirements = computed(() => props.preflight?.missing_requirements || []);
const hasPreflight = computed(() => Boolean(props.preflight));
const statusTag = computed(() => {
  const status = props.preflight?.status || 'idle';
  const labels = {
    ready: '可以查询',
    needs_confirmation: '需要确认',
    blocked: '已阻断',
    error: '错误',
    idle: '未预检',
  };
  const types = {
    ready: 'success',
    needs_confirmation: 'warning',
    blocked: 'danger',
    error: 'danger',
    idle: 'info',
  };
  return {
    label: labels[status] || status,
    type: types[status] || 'info',
  };
});

function boundaryValue(boundary) {
  return props.selections[boundary.confirmation_id]
    || boundary.default_option_id
    || boundary.options?.[0]?.option_id
    || 'do_not_use';
}

function updateSelection(boundary, optionId) {
  emit('update-selection', {
    confirmationId: boundary.confirmation_id,
    optionId,
  });
}

function displayValue(value) {
  if (Array.isArray(value)) return value.join('、');
  if (value === true) return '是';
  if (value === false) return '否';
  return value ?? '-';
}
</script>

<template>
  <section v-if="hasPreflight" class="preflight-panel" aria-label="查询前检查">
    <header class="preflight-header">
      <div>
        <h2>查询前检查</h2>
        <p>系统先判断哪些内容有证据可以执行，哪些需要你确认，哪些不会进入筛选。</p>
      </div>
      <el-tag :type="statusTag.type" effect="plain">{{ statusTag.label }}</el-tag>
    </header>

    <div class="preflight-grid">
      <section class="preflight-section">
        <h3>已识别事实</h3>
        <ul v-if="facts.length" class="preflight-list">
          <li v-for="fact in facts" :key="fact.fact_id || fact.label">
            <span>{{ fact.label }}</span>
            <strong>{{ displayValue(fact.value) }}</strong>
          </li>
        </ul>
        <p v-else class="preflight-empty">暂无已识别事实。</p>
      </section>

      <section class="preflight-section boundary-section">
        <h3>需要你确认</h3>
        <template v-if="boundaries.length">
          <article
            v-for="boundary in boundaries"
            :key="boundary.confirmation_id"
            class="boundary-item"
          >
            <div class="boundary-copy">
              <strong>{{ boundary.label || boundary.source_text }}</strong>
              <p>{{ boundary.reason }}</p>
            </div>
            <el-radio-group
              :model-value="boundaryValue(boundary)"
              @update:model-value="updateSelection(boundary, $event)"
            >
              <el-radio-button
                v-for="option in boundary.options || []"
                :key="option.option_id"
                :label="option.option_id"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
          </article>
        </template>
        <p v-else class="preflight-empty">没有需要确认的边界。</p>
      </section>

      <section class="preflight-section">
        <h3>不会参与筛选</h3>
        <ul v-if="notExecutable.length" class="preflight-list blocked-list">
          <li
            v-for="preference in notExecutable"
            :key="preference.preference_id || preference.source_text"
          >
            <span>{{ preference.source_text || preference.label }}</span>
            <strong>{{ preference.reason }}</strong>
          </li>
        </ul>
        <p v-else class="preflight-empty">没有被排除的偏好。</p>
      </section>

      <section class="preflight-section">
        <h3>还缺少信息</h3>
        <ul v-if="missingRequirements.length" class="preflight-list warning-list">
          <li
            v-for="requirement in missingRequirements"
            :key="requirement.requirement_id || requirement.label"
          >
            <span>{{ requirement.label }}</span>
            <strong>{{ requirement.message }}</strong>
          </li>
        </ul>
        <p v-else class="preflight-empty">没有阻断查询的缺失信息。</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.preflight-panel {
  display: grid;
  gap: 14px;
  padding: 14px;
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #fbfdfc;
}

.preflight-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.preflight-header h2,
.preflight-section h3 {
  margin: 0;
  color: #1f332c;
}

.preflight-header h2 {
  font-size: 16px;
}

.preflight-header p,
.boundary-copy p,
.preflight-empty {
  margin: 4px 0 0;
  color: #66717c;
  font-size: 13px;
  line-height: 1.5;
}

.preflight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.preflight-section {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.preflight-section h3 {
  font-size: 14px;
}

.preflight-list {
  display: grid;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.preflight-list li {
  display: grid;
  grid-template-columns: minmax(88px, 130px) minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 8px 10px;
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #ffffff;
}

.preflight-list span {
  color: #66717c;
  font-size: 12px;
}

.preflight-list strong {
  min-width: 0;
  color: #1f332c;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.warning-list li {
  border-color: #f4d7a1;
  background: #fffaf0;
}

.blocked-list li {
  border-color: #efc3c3;
  background: #fff7f7;
}

.boundary-section {
  padding-top: 2px;
}

.boundary-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px;
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #ffffff;
}

.boundary-copy {
  min-width: 0;
}

.boundary-copy strong {
  color: #1f332c;
  font-size: 13px;
}

@media (max-width: 900px) {
  .preflight-grid,
  .boundary-item {
    grid-template-columns: 1fr;
  }
}
</style>
