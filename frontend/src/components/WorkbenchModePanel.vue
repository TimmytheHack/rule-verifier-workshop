<script setup>
import { computed, nextTick } from 'vue';

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
const modeOptions = [
  { value: 'demo', label: '演示' },
  { value: 'api', label: '后端' },
];

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

function handleModeKeydown(event) {
  const currentValue = event.currentTarget?.dataset?.modeValue;
  const currentIndex = modeOptions.findIndex((option) => option.value === currentValue);
  if (currentIndex === -1) return;

  const nextIndexByKey = {
    ArrowRight: (currentIndex + 1) % modeOptions.length,
    ArrowDown: (currentIndex + 1) % modeOptions.length,
    ArrowLeft: (currentIndex - 1 + modeOptions.length) % modeOptions.length,
    ArrowUp: (currentIndex - 1 + modeOptions.length) % modeOptions.length,
    Home: 0,
    End: modeOptions.length - 1,
  };

  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    updateMode(currentValue);
    return;
  }
  if (!(event.key in nextIndexByKey)) return;

  event.preventDefault();
  const nextValue = modeOptions[nextIndexByKey[event.key]].value;
  updateMode(nextValue);
  focusModeButton(event.currentTarget, nextValue);
}

function focusModeButton(currentTarget, value) {
  nextTick(() => {
    currentTarget
      ?.closest('[role="radiogroup"]')
      ?.querySelector(`[data-mode-value="${value}"]`)
      ?.focus();
  });
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
        <div class="mode-segmented-control" role="radiogroup" aria-label="模式">
          <button
            v-for="option in modeOptions"
            :key="option.value"
            type="button"
            :class="['mode-segment', { 'is-active': mode === option.value }]"
            role="radio"
            :aria-checked="mode === option.value"
            :tabindex="mode === option.value ? 0 : -1"
            :data-mode-value="option.value"
            @click="updateMode(option.value)"
            @keydown="handleModeKeydown"
          >
            {{ option.label }}
          </button>
        </div>
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

<style scoped>
.mode-segmented-control {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px;
  width: 100%;
  min-height: 32px;
  padding: 2px;
  border: 1px solid #d5dde4;
  border-radius: 6px;
  background: #f3f6f8;
}

.mode-segment {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  min-height: 28px;
  padding: 4px 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #41525d;
  line-height: 1.3;
  cursor: pointer;
}

.mode-segment.is-active {
  background: #ffffff;
  color: #1f3440;
  font-weight: 700;
  box-shadow: 0 1px 3px rgb(31 52 64 / 14%);
}

.mode-segment:focus-visible {
  outline: 2px solid #2f8065;
  outline-offset: 2px;
}
</style>
