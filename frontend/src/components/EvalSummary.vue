<script setup>
import { computed } from 'vue';

const props = defineProps({
  runData: {
    type: Object,
    required: true,
  },
});

const auditCards = computed(() => {
  const results = props.runData.items?.length ? props.runData.items : (props.runData.top_results || []);
  const tracedRows = results.filter((row) => {
    if (Array.isArray(row.matched_filters)) {
      return row.matched_filters.length > 0;
    }
    return Array.isArray(row.trace) && row.trace.length > 0;
  });
  const notExecuted = props.runData.not_executed_preferences || [];
  return [
    {
      label: '已执行规则',
      value: props.runData.executable_rules?.length || 0,
      type: 'success',
      note: '进入筛选执行的规则数',
    },
    {
      label: '待确认规则',
      value: props.runData.candidate_rules?.length || 0,
      type: 'warning',
      note: '需要确认或模拟确认',
    },
    {
      label: '未执行偏好',
      value: notExecuted.length,
      type: notExecuted.length ? 'danger' : 'success',
      note: notExecuted.length ? '保留展示，未参与筛选' : '无未执行偏好',
    },
    {
      label: '结果数量',
      value: props.runData.result_count || 0,
      type: 'info',
      note: '基于已验证规则',
    },
    {
      label: '追踪覆盖',
      value: `${tracedRows.length}/${results.length}`,
      type: tracedRows.length === results.length ? 'success' : 'danger',
      note: '当前表格结果',
    },
  ];
});

const cooperationStatus = computed(() => {
  const found = (props.runData.not_executed_preferences || []).some((item) =>
    String(item.preference || item.display || '').includes('中外合作'),
  );
  return found ? '中外合作未执行，未参与过滤' : '本次未出现中外合作偏好';
});
</script>

<template>
  <el-card class="workbench-card eval-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>质量检查</h2>
        </div>
        <el-tag effect="plain">当前结果</el-tag>
      </div>
    </template>

    <div class="audit-grid">
      <article v-for="card in auditCards" :key="card.label" class="audit-card">
        <span class="audit-label">{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
        <el-tag :type="card.type" effect="plain">{{ card.note }}</el-tag>
      </article>
    </div>

    <el-alert
      class="inline-alert"
      :type="cooperationStatus.includes('未执行') ? 'warning' : 'info'"
      :closable="false"
      show-icon
      :title="cooperationStatus"
    />
  </el-card>
</template>
