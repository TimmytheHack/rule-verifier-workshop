<script setup>
import { computed } from 'vue';
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
} from '@element-plus/icons-vue';

const props = defineProps({
  runData: {
    type: Object,
    required: true,
  },
});

const usedRules = computed(() => listOrEmpty(
  props.runData.executed_filters?.length
    ? props.runData.executed_filters
    : props.runData.executable_rules,
));
const confirmItems = computed(() => listOrEmpty(
  props.runData.candidates_to_confirm?.length
    ? props.runData.candidates_to_confirm
    : props.runData.candidate_rules,
));
const unusedItems = computed(() => [
  ...listOrEmpty(props.runData.unexecuted_preferences),
  ...listOrEmpty(props.runData.not_executed_preferences),
  ...listOrEmpty(props.runData.no_schema_field_preferences),
]);
const informationRequests = computed(() => listOrEmpty(
  props.runData.evidence_pack?.decision_guidance?.information_requests,
));

function listOrEmpty(items) {
  return Array.isArray(items) ? items : [];
}

function ruleLabel(item) {
  return item?.label || item?.display || item?.preference || item?.text || item?.field || item?.id || '未命名条件';
}

function itemReason(item, fallback) {
  return item?.reason || item?.message || item?.match_type || fallback;
}
</script>

<template>
  <el-card class="workbench-card beginner-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>本次怎么筛</h2>
        </div>
        <el-tag type="success" effect="plain">已核对</el-tag>
      </div>
    </template>

    <section class="beginner-section good">
      <div class="beginner-section-title">
        <el-icon><CircleCheckFilled /></el-icon>
        <h3>已经参与筛选</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="rule in usedRules"
          :key="rule.id || rule.label"
          class="beginner-row"
        >
          <strong>{{ ruleLabel(rule) }}</strong>
        </article>
        <p
          v-if="!usedRules.length"
          class="beginner-empty"
        >
          暂无已用条件
        </p>
      </div>
    </section>

    <section class="beginner-section warn">
      <div class="beginner-section-title">
        <el-icon><WarningFilled /></el-icon>
        <h3>还要你确认</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="candidate in confirmItems"
          :key="candidate.candidate_id || candidate.id || candidate.preference"
          class="beginner-row"
        >
          <strong>{{ ruleLabel(candidate) }}</strong>
          <p>{{ itemReason(candidate, '确认后才会参与筛选。') }}</p>
        </article>
        <p
          v-if="!confirmItems.length"
          class="beginner-empty"
        >
          暂无待确认项
        </p>
      </div>
    </section>

    <section
      v-if="informationRequests.length"
      class="beginner-section warn"
    >
      <div class="beginner-section-title">
        <el-icon><WarningFilled /></el-icon>
        <h3>还需补充信息</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="request in informationRequests"
          :key="request.question_id"
          class="beginner-row"
        >
          <strong>{{ request.label || request.question_id }}</strong>
          <p>{{ request.question }}</p>
        </article>
      </div>
    </section>

    <section class="beginner-section bad">
      <div class="beginner-section-title">
        <el-icon><CircleCloseFilled /></el-icon>
        <h3>没有参与筛选</h3>
      </div>
      <div class="beginner-list">
        <article
          v-for="(item, index) in unusedItems"
          :key="`${item.id || item.display || item.preference || 'unused'}-${index}`"
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
