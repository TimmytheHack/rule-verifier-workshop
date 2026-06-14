<script setup>
defineProps({
  preferences: {
    type: Array,
    required: true,
  },
});

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.join(' / ');
  }
  return String(value);
}

function statusType(status) {
  if (status === 'schema_grounded' || status === '已对齐字段') return 'success';
  if (status === 'candidate_confirmation_required' || status === '待确认') return 'warning';
  return 'danger';
}

function statusLabel(status) {
  const labels = {
    schema_grounded: '已对齐数据字段',
    candidate_confirmation_required: '待确认',
    not_executable_missing_schema: '不可执行',
    已对齐字段: '已对齐数据字段',
    待确认: '待确认',
    不可执行: '不可执行',
  };
  return labels[status] || status;
}
</script>

<template>
  <el-card class="workbench-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>识别到的偏好</h2>
        </div>
        <el-tag effect="plain">保留来源片段</el-tag>
      </div>
    </template>

    <div class="preference-grid">
      <article
        v-for="preference in preferences"
        :key="preference.id"
        class="preference-item"
      >
        <div class="preference-topline">
          <strong>{{ preference.slot }}</strong>
          <el-tag :type="statusType(preference.status)" size="small" effect="plain">
            {{ statusLabel(preference.status) }}
          </el-tag>
        </div>
        <p class="preference-value">{{ formatValue(preference.value) }}</p>
        <p class="source-span">来源：{{ preference.source_span }}</p>
      </article>
    </div>
  </el-card>
</template>
