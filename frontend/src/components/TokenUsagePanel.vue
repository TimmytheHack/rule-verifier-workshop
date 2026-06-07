<script setup>
import { computed } from 'vue';

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
  prompt_tokens: '输入 token',
  completion_tokens: '输出 token',
  total_tokens: '总 token',
  prompt_cache_hit_tokens: '缓存命中 token',
  prompt_cache_miss_tokens: '缓存未命中 token',
  reasoning_tokens: '推理 token',
};

const hasUsage = computed(() => {
  if (!props.tokenUsage) return false;
  return ['extractor', 'generator', 'total'].some((key) => {
    const usage = props.tokenUsage[key];
    return usage && Object.values(usage).some((value) => Number(value) > 0);
  });
});

function usageRows(usage) {
  if (!usage) return [];
  return Object.entries(usageLabels).map(([key, label]) => ({
    key,
    label,
    value: Number(usage[key] || 0),
  }));
}
</script>

<template>
  <el-card v-if="mode === 'api' || hasUsage" class="workbench-card token-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">LLM 调用统计</p>
          <h2>Token 用量</h2>
        </div>
        <el-tag :type="hasUsage ? 'success' : 'info'" effect="plain">
          {{ hasUsage ? '已返回用量' : '本次未调用 LLM' }}
        </el-tag>
      </div>
    </template>

    <div v-if="selectedOptions" class="selected-options">
      <el-tag effect="plain">抽取：{{ selectedOptions.extractor }}</el-tag>
      <el-tag effect="plain">生成：{{ selectedOptions.generator }}</el-tag>
      <el-tag v-if="selectedOptions.model" type="warning" effect="plain">
        模型：{{ selectedOptions.model }}
      </el-tag>
    </div>

    <el-alert
      v-if="!hasUsage"
      type="info"
      :closable="false"
      show-icon
      title="只有选择 LLM 辅助解析软偏好或 LLM 证据回答时，后端才会返回 token 用量。"
    />

    <div v-else class="usage-grid">
      <section
        v-for="section in [
          ['extractor', '抽取调用'],
          ['generator', '回答生成调用'],
          ['total', '合计'],
        ]"
        :key="section[0]"
        class="usage-block"
      >
        <h3>{{ section[1] }}</h3>
        <dl>
          <div v-for="row in usageRows(tokenUsage[section[0]])" :key="row.key">
            <dt>{{ row.label }}</dt>
            <dd>{{ row.value }}</dd>
          </div>
        </dl>
      </section>
    </div>
  </el-card>
</template>
