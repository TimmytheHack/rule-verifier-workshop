<script setup>
defineProps({
  steps: {
    type: Array,
    required: true,
  },
});

function statusLabel(status) {
  const labels = {
    idle: '等待',
    running: '处理中',
    success: '完成',
    error: '需要处理',
  };
  return labels[status] || status;
}

function tagType(status) {
  if (status === 'success') return 'success';
  if (status === 'running') return 'warning';
  if (status === 'error') return 'danger';
  return 'info';
}
</script>

<template>
  <ol class="import-step-list">
    <li v-for="step in steps" :key="step.key" class="import-step-item">
      <span class="import-step-dot" :class="`is-${step.status}`" />
      <div>
        <strong>{{ step.label }}</strong>
        <small v-if="step.message">{{ step.message }}</small>
      </div>
      <el-tag :type="tagType(step.status)" effect="plain">{{ statusLabel(step.status) }}</el-tag>
    </li>
  </ol>
</template>
