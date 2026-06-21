<script setup>
import { computed } from 'vue';
import { DataAnalysis, Search, Setting, Upload } from '@element-plus/icons-vue';

import WorkbenchModePanel from './WorkbenchModePanel.vue';
import {
  formatModeTag,
  formatOptionsSourceTag,
} from '../utils/workbenchRunBar';

const props = defineProps({
  mode: {
    type: String,
    required: true,
  },
  extractor: {
    type: String,
    required: true,
  },
  generator: {
    type: String,
    required: true,
  },
  model: {
    type: String,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  selectedDataSourceId: {
    type: String,
    required: true,
  },
  dataSourceOptions: {
    type: Array,
    default: () => [],
  },
  dataSourceTag: {
    type: Object,
    default: () => ({ type: 'info', label: '' }),
  },
  dataSourceDescription: {
    type: String,
    default: '',
  },
  extractorOptions: {
    type: Array,
    default: () => [],
  },
  generatorOptions: {
    type: Array,
    default: () => [],
  },
  modelOptions: {
    type: Array,
    default: () => [],
  },
  optionsSource: {
    type: String,
    default: 'fallback',
  },
  optionsError: {
    type: String,
    default: '',
  },
  runStatus: {
    type: Object,
    default: () => ({ type: 'info', label: '待查询' }),
  },
});

const emit = defineEmits([
  'run',
  'demo',
  'upload',
  'update:mode',
  'update:extractor',
  'update:generator',
  'update:model',
  'update:selectedDataSourceId',
]);

const modeTag = computed(() => formatModeTag(props.mode));
const optionsSourceTag = computed(() => formatOptionsSourceTag(props.optionsSource));
const runStatusTag = computed(() => props.runStatus);
</script>

<template>
  <section class="workbench-run-bar" aria-label="运行控制">
    <div class="run-bar-source">
      <span class="control-label">数据源</span>
      <div class="run-bar-source-row">
        <el-select
          :model-value="selectedDataSourceId"
          class="run-bar-source-select"
          size="large"
          @update:model-value="emit('update:selectedDataSourceId', $event)"
        >
          <el-option
            v-for="source in dataSourceOptions"
            :key="source.id"
            :label="source.label"
            :value="source.id"
          />
        </el-select>
        <el-tag :type="dataSourceTag.type" effect="plain">
          {{ dataSourceTag.label }}
        </el-tag>
      </div>
      <p>{{ dataSourceDescription }}</p>
    </div>

    <div class="run-bar-status" aria-label="运行状态">
      <el-tag :type="modeTag.type" effect="plain">{{ modeTag.label }}</el-tag>
      <el-tag :type="optionsSourceTag.type" effect="plain">{{ optionsSourceTag.label }}</el-tag>
      <el-tag :type="runStatusTag.type" effect="plain">{{ runStatusTag.label }}</el-tag>
      <span v-if="optionsError" class="run-bar-warning">{{ optionsError }}</span>
    </div>

    <div class="run-bar-actions">
      <el-popover placement="bottom-end" :width="420" trigger="click">
        <template #reference>
          <el-button :icon="Setting">运行选项</el-button>
        </template>
        <WorkbenchModePanel
          :mode="mode"
          :extractor="extractor"
          :generator="generator"
          :model="model"
          :extractor-options="extractorOptions"
          :generator-options="generatorOptions"
          :model-options="modelOptions"
          @update:mode="emit('update:mode', $event)"
          @update:extractor="emit('update:extractor', $event)"
          @update:generator="emit('update:generator', $event)"
          @update:model="emit('update:model', $event)"
        />
      </el-popover>
      <el-button :icon="Upload" @click="emit('upload')">上传表格</el-button>
      <el-button :icon="DataAnalysis" @click="emit('demo')">查看演示数据</el-button>
      <el-button
        type="primary"
        :icon="Search"
        :loading="loading"
        @click="emit('run')"
      >
        {{ loading ? '正在查询' : '开始查询' }}
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.workbench-run-bar {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) auto auto;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 12px;
  border: 1px solid #d8e4df;
  border-radius: 8px;
  background: #ffffff;
}

.run-bar-source,
.run-bar-status,
.run-bar-actions {
  min-width: 0;
}

.run-bar-source {
  display: grid;
  gap: 5px;
}

.run-bar-source-row {
  display: grid;
  grid-template-columns: minmax(180px, 320px) auto;
  gap: 8px;
  align-items: center;
  justify-content: start;
}

.run-bar-source-select {
  width: 100%;
}

.run-bar-source p {
  margin: 0;
  color: #66717c;
  font-size: 12px;
  line-height: 1.4;
}

.run-bar-status,
.run-bar-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.run-bar-status {
  justify-content: center;
}

.run-bar-warning {
  max-width: 240px;
  color: #9a6812;
  font-size: 12px;
  line-height: 1.4;
}

.run-bar-actions {
  justify-content: flex-end;
}

.run-bar-actions .el-button {
  margin-left: 0 !important;
}

:deep(.mode-card) {
  margin-top: 0;
  border: 0;
  box-shadow: none;
}

@media (max-width: 1100px) {
  .workbench-run-bar {
    grid-template-columns: 1fr;
  }

  .run-bar-status,
  .run-bar-actions {
    justify-content: flex-start;
  }
}
</style>
