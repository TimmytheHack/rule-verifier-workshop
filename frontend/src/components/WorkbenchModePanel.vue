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
  extractorOptions: {
    type: Array,
    default: () => [
      { value: 'regex', label: '规则解析' },
      { value: 'deepseek', label: '模型辅助' },
    ],
  },
  generatorOptions: {
    type: Array,
    default: () => [
      { value: 'template_evidence', label: '固定模板' },
      { value: 'deepseek_evidence', label: '模型润色' },
    ],
  },
  modelOptions: {
    type: Array,
    default: () => [
      { value: 'deepseek-v4-flash', label: '快速模型' },
      { value: 'deepseek-v4-pro', label: '高质量模型' },
    ],
  },
});

const emit = defineEmits([
  'update:mode',
  'update:extractor',
  'update:generator',
  'update:model',
]);

const availableExtractorOptions = computed(() => props.extractorOptions);
const availableGeneratorOptions = computed(() => props.generatorOptions);
const availableModelOptions = computed(() => props.modelOptions);

const usesDeepSeek = computed(
  () =>
    props.mode === 'api' &&
    (
      props.extractor === 'deepseek'
      || props.extractor === 'deepseek_slots'
      || props.extractor === 'hybrid'
      || props.generator === 'deepseek_evidence'
    ),
);

function updateMode(value) {
  emit('update:mode', value);
  if (value === 'api') {
    if (!props.extractorOptions.some((option) => option.value === props.extractor)) {
      emit('update:extractor', props.extractorOptions[0]?.value || 'regex');
    }
    if (!props.generatorOptions.some((option) => option.value === props.generator)) {
      emit('update:generator', props.generatorOptions[0]?.value || 'template_evidence');
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
            v-for="option in availableExtractorOptions"
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
            v-for="option in availableGeneratorOptions"
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
            v-for="option in availableModelOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>
    </div>

  </el-card>
</template>
