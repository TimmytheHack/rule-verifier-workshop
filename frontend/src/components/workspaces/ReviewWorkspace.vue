<script setup>
import DatasetIngestionPanel from '../DatasetIngestionPanel.vue';

defineProps({
  selectedDataSource: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['source-ready']);
</script>

<template>
  <section class="workspace-panel single-scroll review-workspace">
    <el-card class="workbench-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>字段审查</h2>
            <p class="panel-copy">只有导入失败或字段映射不对时使用这里。</p>
          </div>
          <el-tag effect="plain" type="warning">高级操作</el-tag>
        </div>
      </template>
      <p class="beginner-empty">
        当前普通路径会自动套用招生字段模板。这里保留原审查工具，方便处理模板不匹配的表格。
      </p>
      <p v-if="selectedDataSource" class="beginner-empty">
        当前数据源：{{ selectedDataSource.label }}
      </p>
    </el-card>

    <el-collapse class="developer-collapse">
      <el-collapse-item title="开发者字段审查工具" name="legacy-review">
        <DatasetIngestionPanel @source-ready="emit('source-ready', $event)" />
      </el-collapse-item>
    </el-collapse>
  </section>
</template>
