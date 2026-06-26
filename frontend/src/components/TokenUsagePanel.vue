<script setup>
import { computed } from 'vue';

import {
  tokenUsageSectionState,
  tokenUsageSummaryState,
} from '../utils/workbenchState';

const props = defineProps({
  tokenUsage: {
    type: Object,
    default: null,
  },
  mode: {
    type: String,
    required: true,
  },
  selectedOptions: {
    type: Object,
    default: null,
  },
});

const usageLabels = {
  prompt_tokens: '输入用量',
  completion_tokens: '输出用量',
  total_tokens: '总用量',
  prompt_cache_hit_tokens: '缓存命中',
  prompt_cache_miss_tokens: '缓存未命中',
  reasoning_tokens: '推理用量',
};

const usageSections = [
  { key: 'extractor', label: '抽取调用' },
  { key: 'generator', label: '回答生成调用' },
  { key: 'total', label: '合计' },
];

const usageSectionStates = computed(() => usageSections.map((section) => ({
  ...section,
  usage: props.tokenUsage?.[section.key],
  state: tokenUsageSectionState(props.tokenUsage, section.key),
})));

const hasUsage = computed(() => usageSectionStates.value.some((section) => (
  section.state.status === 'has_usage'
)));
const usageSummary = computed(() => tokenUsageSummaryState(props.tokenUsage));

function usageRows(usage) {
  if (!usage) return [];
  return Object.entries(usageLabels).map(([key, label]) => ({
    key,
    label,
    value: Number(usage[key] || 0),
  }));
}

function sectionTagType(status) {
  if (status === 'has_usage') return 'success';
  if (status === 'zero_usage') return 'info';
  return 'warning';
}

function sectionMessage(status) {
  return status === 'zero_usage'
    ? '本段未发生模型调用。'
    : '本段没有返回 token usage。';
}
</script>

<template>
  <el-card v-if="mode === 'api' || hasUsage" class="workbench-card token-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>模型用量</h2>
        </div>
        <el-tag :type="usageSummary.type" effect="plain">
          {{ usageSummary.label }}
        </el-tag>
      </div>
    </template>

    <div v-if="selectedOptions" class="selected-options">
      <el-tag effect="plain">抽取：{{ selectedOptions.extractor }}</el-tag>
      <el-tag effect="plain">生成：{{ selectedOptions.generator }}</el-tag>
      <el-tag v-if="selectedOptions.model" type="warning" effect="plain">
        当前模型：{{ selectedOptions.model }}
      </el-tag>
    </div>

    <el-alert
      v-if="!hasUsage"
      type="info"
      :closable="false"
      show-icon
      title="各阶段用量状态如下；未返回用量不代表前端执行了额外逻辑。"
    />

    <div class="usage-grid">
      <section
        v-for="section in usageSectionStates"
        :key="section.key"
        class="usage-block"
      >
        <div class="usage-block-header">
          <h3>{{ section.label }}</h3>
          <el-tag :type="sectionTagType(section.state.status)" size="small" effect="plain">
            {{ section.state.label }}
          </el-tag>
        </div>
        <dl v-if="section.state.status === 'has_usage'">
          <div v-for="row in usageRows(section.usage)" :key="row.key">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
          </div>
        </dl>
        <p v-else class="beginner-empty">{{ sectionMessage(section.state.status) }}</p>
      </section>
    </div>
  </el-card>
</template>
