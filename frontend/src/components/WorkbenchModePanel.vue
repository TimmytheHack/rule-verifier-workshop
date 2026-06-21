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
  { value: 'hybrid', label: '规则优先' },
  { value: 'regex', label: '规则解析' },
  { value: 'deepseek', label: '模型辅助' },
  { value: 'template_coverage', label: '字段覆盖' },
];

const apiExtractors = [
  { value: 'hybrid', label: '规则优先' },
  { value: 'regex', label: '规则解析' },
  { value: 'deepseek', label: '模型辅助' },
];

const demoGenerators = [
  { value: 'template_evidence', label: '固定模板' },
  { value: 'deepseek_evidence', label: '模型润色' },
  { value: 'template_coverage', label: '覆盖清单' },
];

const apiGenerators = [
  { value: 'template_evidence', label: '固定模板' },
  { value: 'deepseek_evidence', label: '模型润色' },
];

const models = [
  { value: 'deepseek-v4-flash', label: '快速模型' },
  { value: 'deepseek-v4-pro', label: '高质量模型' },
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
          <h2>运行方式</h2>
        </div>
        <el-tag :type="mode === 'api' ? 'warning' : 'info'" effect="plain">
          {{ mode === 'api' ? '连接后端' : '演示数据' }}
        </el-tag>
      </div>
    </template>

    <div class="mode-grid">
      <div class="control-block wide-control">
        <span class="control-label">模式</span>
        <el-segmented
          :model-value="mode"
          :options="[
            { value: 'demo', label: '演示' },
            { value: 'api', label: '后端' },
          ]"
          @update:model-value="updateMode"
        />
      </div>

      <div class="control-block">
        <span class="control-label">解析</span>
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
        <span class="control-label">回答</span>
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
        <span class="control-label">模型</span>
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

  </el-card>
</template>
