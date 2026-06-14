<script setup>
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
} from '@element-plus/icons-vue';

defineProps({
  runData: {
    type: Object,
    required: true,
  },
});

function listOrEmpty(items) {
  return Array.isArray(items) ? items : [];
}

function ruleLabel(item) {
  return item?.label || item?.display || item?.preference || item?.id || '未命名条件';
}

function itemReason(item, fallback) {
  return item?.reason || fallback;
}
</script>

<template>
  <el-card class="workbench-card beginner-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>这次筛选</h2>
        </div>
        <el-tag type="success" effect="plain">已检查</el-tag>
      </div>
    </template>

    <section class="beginner-section good">
      <div class="beginner-section-title">
        <el-icon><CircleCheckFilled /></el-icon>
        <h3>已经用上的条件</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="rule in listOrEmpty(runData.executable_rules)"
          :key="rule.id || rule.label"
          class="beginner-row"
        >
          <strong>{{ ruleLabel(rule) }}</strong>
        </article>
        <p
          v-if="!listOrEmpty(runData.executable_rules).length"
          class="beginner-empty"
        >
          暂无已用条件
        </p>
      </div>
    </section>

    <section class="beginner-section warn">
      <div class="beginner-section-title">
        <el-icon><WarningFilled /></el-icon>
        <h3>需要你确认</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="candidate in listOrEmpty(runData.candidate_rules)"
          :key="candidate.id || candidate.preference"
          class="beginner-row"
        >
          <strong>{{ ruleLabel(candidate) }}</strong>
          <p>{{ itemReason(candidate, '确认后才会参与筛选。') }}</p>
        </article>
        <p
          v-if="!listOrEmpty(runData.candidate_rules).length"
          class="beginner-empty"
        >
          暂无待确认项
        </p>
      </div>
    </section>

    <section class="beginner-section bad">
      <div class="beginner-section-title">
        <el-icon><CircleCloseFilled /></el-icon>
        <h3>没有参与筛选</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="item in listOrEmpty(runData.not_executed_preferences)"
          :key="item.id || item.display"
          class="beginner-row"
        >
          <strong>{{ ruleLabel(item) }}</strong>
          <p>{{ itemReason(item, '当前数据表没有可验证字段。') }}</p>
        </article>
        <p
          v-if="!listOrEmpty(runData.not_executed_preferences).length"
          class="beginner-empty"
        >
          暂无未使用偏好
        </p>
      </div>
    </section>
  </el-card>
</template>
