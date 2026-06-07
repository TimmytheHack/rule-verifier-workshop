<script setup>
import { computed } from 'vue';

const props = defineProps({
  candidateRules: {
    type: Array,
    required: true,
  },
  confirmations: {
    type: Object,
    required: true,
  },
});

const confirmationText = computed(() => {
  const items = [];
  if (props.confirmations.safety_margin_percent) {
    items.push(`位次窗口 = ${props.confirmations.safety_margin_percent}%`);
  }
  if (props.confirmations.tuition_cap) {
    items.push(`学费上限 = ${props.confirmations.tuition_cap}`);
  }
  return items;
});

function subtitle(candidate) {
  if (candidate.id === 'candidate_major_expansion' || candidate.id === 'c_major_expansion') {
    return '是否扩展到 软件工程 / 人工智能 / 网络安全';
  }
  return candidate.reason;
}
</script>

<template>
  <el-card class="workbench-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">规则提升</p>
          <h2>候选规则模拟确认</h2>
        </div>
        <div class="confirmation-tags">
          <el-tag
            v-for="item in confirmationText"
            :key="item"
            type="warning"
            effect="plain"
          >
            {{ item }}
          </el-tag>
        </div>
      </div>
    </template>

    <el-alert
      class="inline-alert"
      type="warning"
      :closable="false"
      show-icon
      title="演示确认来自管线输出，前端不根据点击结果创建新规则。"
    />

    <div class="confirmation-grid">
      <article
        v-for="candidate in candidateRules"
        :key="candidate.id"
        class="confirmation-card"
      >
        <div class="confirmation-title-row">
          <h3>{{ candidate.preference }}</h3>
          <el-tag type="warning" effect="light">待确认</el-tag>
        </div>
        <p>{{ subtitle(candidate) }}</p>
        <el-radio-group
          class="confirmation-options"
          :model-value="candidate.simulated_selection"
          disabled
        >
          <el-radio-button
            v-for="option in candidate.options"
            :key="option"
            :label="option"
            :value="option"
          />
        </el-radio-group>
      </article>
    </div>
  </el-card>
</template>
