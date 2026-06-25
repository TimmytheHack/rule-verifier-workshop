<script setup>
defineProps({
  selectedDataSource: {
    type: Object,
    default: null,
  },
});
</script>

<template>
  <section class="workspace-panel single-scroll review-workspace">
    <el-card class="workbench-card" shadow="never">
      <template #header>
        <div class="card-header">
          <h2>字段审查</h2>
          <el-tag effect="plain">高级</el-tag>
        </div>
      </template>
      <p class="beginner-empty">字段映射不匹配时，从导入数据页进入这里处理。</p>
      <p v-if="selectedDataSource" class="beginner-empty">
        当前数据源：{{ selectedDataSource.label }}
      </p>
    </el-card>
  </section>
</template>
