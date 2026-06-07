<script setup>
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
} from '@element-plus/icons-vue';

defineProps({
  grounding: {
    type: Object,
    default: () => ({ attributes: [], summary: {} }),
  },
  proposedRules: {
    type: Array,
    default: () => [],
  },
});

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.join(' / ');
  }
  if (value === null || value === undefined || value === '') {
    return '无';
  }
  return String(value);
}

function statusIcon(type) {
  if (type === 'success') return CircleCheckFilled;
  if (type === 'warning') return WarningFilled;
  return CircleCloseFilled;
}
</script>

<template>
  <el-card class="workbench-card verification-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">属性接地 → 规则验证</p>
          <h2>字段接地与规则审查</h2>
        </div>
        <el-tag type="warning" effect="plain">LLM 只提议，验证器决定</el-tag>
      </div>
    </template>

    <div class="verification-grid">
      <section class="audit-panel">
        <div class="audit-panel-header">
          <h3>字段接地审查</h3>
          <el-tag effect="plain">
            {{ grounding.attributes?.length || 0 }} 项
          </el-tag>
        </div>

        <div v-if="grounding.attributes?.length" class="audit-list">
          <article
            v-for="item in grounding.attributes"
            :key="`${item.slot_path}-${formatValue(item.value)}`"
            class="audit-row"
          >
            <div class="audit-row-main">
              <component :is="statusIcon(item.status_type)" class="audit-icon" />
              <div>
                <strong>{{ item.slot }}</strong>
                <p>{{ formatValue(item.value) }}</p>
              </div>
            </div>
            <div class="audit-row-side">
              <el-tag :type="item.status_type" effect="plain">
                {{ item.status }}
              </el-tag>
              <span>{{ item.field }}</span>
            </div>
            <p class="audit-reason">{{ item.reason }}</p>
          </article>
        </div>
        <el-empty v-else description="暂无字段接地记录" />
      </section>

      <section class="audit-panel">
        <div class="audit-panel-header">
          <h3>规则提议审查</h3>
          <el-tag effect="plain">
            {{ proposedRules.length }} 条
          </el-tag>
        </div>

        <div v-if="proposedRules.length" class="audit-list">
          <article
            v-for="rule in proposedRules"
            :key="rule.id"
            class="audit-row"
          >
            <div class="audit-row-main">
              <component :is="statusIcon(rule.status_type)" class="audit-icon" />
              <div>
                <strong>{{ rule.label }}</strong>
                <p>来源：{{ rule.source_text }}</p>
              </div>
            </div>
            <div class="audit-row-side">
              <el-tag :type="rule.status_type" effect="plain">
                {{ rule.status }}
              </el-tag>
              <span>{{ rule.category }}</span>
            </div>
            <div class="check-row">
              <el-tag
                v-for="check in rule.checks"
                :key="`${rule.id}-${check.label}`"
                :type="check.passed ? 'success' : 'danger'"
                effect="plain"
                size="small"
              >
                {{ check.label }}
              </el-tag>
            </div>
            <p class="audit-reason">{{ rule.reason }}</p>
          </article>
        </div>
        <el-empty v-else description="当前提取方式未返回规则提议" />
      </section>
    </div>
  </el-card>
</template>
