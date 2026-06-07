<script setup>
import { computed } from 'vue';

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
});

const emit = defineEmits([
  'update:mode',
  'update:extractor',
  'update:generator',
  'update:model',
]);

const demoExtractors = [
  { value: 'regex', label: '规则解析软偏好' },
  { value: 'deepseek', label: 'LLM 辅助解析软偏好' },
  { value: 'template_coverage', label: '字段覆盖演示' },
];

const apiExtractors = [
  { value: 'regex', label: '规则解析软偏好' },
  { value: 'deepseek', label: 'LLM 辅助解析软偏好' },
];

const demoGenerators = [
  { value: 'template_evidence', label: '模板证据回答' },
  { value: 'deepseek_evidence', label: 'LLM 证据回答' },
  { value: 'template_coverage', label: '证据覆盖清单' },
];

const apiGenerators = [
  { value: 'template_evidence', label: '模板证据回答' },
  { value: 'deepseek_evidence', label: 'LLM 证据回答' },
];

const models = [
  { value: 'deepseek-v4-flash', label: 'LLM 快速模型' },
  { value: 'deepseek-v4-pro', label: 'LLM 高质量模型' },
];

const extractorOptions = computed(() =>
  props.mode === 'demo' ? demoExtractors : apiExtractors,
);

const generatorOptions = computed(() =>
  props.mode === 'demo' ? demoGenerators : apiGenerators,
);

const usesDeepSeek = computed(
  () =>
    props.mode === 'api' &&
    (props.extractor === 'deepseek' || props.generator === 'deepseek_evidence'),
);

function updateMode(value) {
  emit('update:mode', value);
  if (value === 'api') {
    if (!apiExtractors.some((option) => option.value === props.extractor)) {
      emit('update:extractor', apiExtractors[0].value);
    }
    if (!apiGenerators.some((option) => option.value === props.generator)) {
      emit('update:generator', apiGenerators[0].value);
    }
  }
}
</script>

<template>
  <el-card class="workbench-card mode-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">运行设置</p>
          <h2>模式与可选项</h2>
        </div>
        <el-tag :type="mode === 'api' ? 'warning' : 'info'" effect="plain">
          {{ mode === 'api' ? 'API 模式' : '演示模式' }}
        </el-tag>
      </div>
    </template>

    <div class="mode-grid">
      <div class="control-block wide-control">
        <span class="control-label">运行模式</span>
        <el-segmented
          :model-value="mode"
          :options="[
            { value: 'demo', label: '演示模式' },
            { value: 'api', label: 'API 模式' },
          ]"
          @update:model-value="updateMode"
        />
      </div>

      <div class="control-block">
        <span class="control-label">规则提取方式</span>
        <el-select
          :model-value="extractor"
          class="full-control"
          @update:model-value="emit('update:extractor', $event)"
        >
          <el-option
            v-for="option in extractorOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>

      <div class="control-block">
        <span class="control-label">证据回答</span>
        <el-select
          :model-value="generator"
          class="full-control"
          @update:model-value="emit('update:generator', $event)"
        >
          <el-option
            v-for="option in generatorOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>

      <div class="control-block">
        <span class="control-label">LLM 模型</span>
        <el-select
          :model-value="model"
          class="full-control"
          :disabled="mode === 'api' && !usesDeepSeek"
          @update:model-value="emit('update:model', $event)"
        >
          <el-option
            v-for="option in models"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>
    </div>

    <el-alert
      class="inline-alert mode-warning"
      type="info"
      :closable="false"
      show-icon
      title="API 模式不会提供 LLM-only 路径；LLM 只可用于软偏好解析或基于证据包生成回答。"
    />
  </el-card>
</template>
