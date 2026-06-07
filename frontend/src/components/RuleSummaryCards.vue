<script setup>
import {
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
} from '@element-plus/icons-vue';

defineProps({
  deterministicRules: {
    type: Array,
    required: true,
  },
  candidateRules: {
    type: Array,
    required: true,
  },
  notExecutedPreferences: {
    type: Array,
    required: true,
  },
  executableRules: {
    type: Array,
    required: true,
  },
});

function originLabel(origin) {
  if (origin === 'deterministic') return '已验证';
  if (origin === 'verified_llm_proposal') return '提议已验证';
  return '模拟确认后提升';
}
</script>

<template>
  <section class="summary-section">
    <el-row :gutter="16">
      <el-col :xs="24" :md="8">
        <el-card class="summary-card success-card" shadow="never">
          <div class="summary-title success-title">
            <el-icon><CircleCheckFilled /></el-icon>
            <span>A. 可执行规则</span>
          </div>
          <div class="summary-block">
            <p class="summary-subtitle">确定性规则</p>
            <el-tag
              v-for="rule in deterministicRules"
              :key="rule.id"
              class="rule-tag"
              type="success"
              effect="light"
            >
              {{ rule.label }}
            </el-tag>
          </div>
          <div class="summary-block">
            <p class="summary-subtitle">最终可执行规则</p>
            <div
              v-for="rule in executableRules"
              :key="rule.id"
              class="rule-line"
            >
              <el-tag size="small" type="success" effect="plain">
                {{ originLabel(rule.origin) }}
              </el-tag>
              <span>{{ rule.label }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card class="summary-card warning-card" shadow="never">
          <div class="summary-title warning-title">
            <el-icon><WarningFilled /></el-icon>
            <span>B. 待确认规则</span>
          </div>
          <div
            v-for="candidate in candidateRules"
            :key="candidate.id"
            class="candidate-line"
          >
            <div class="candidate-line-title">
              <el-tag type="warning" effect="light">{{ candidate.preference }}</el-tag>
              <strong>{{ candidate.label }}</strong>
            </div>
            <p>{{ candidate.reason }}</p>
            <p class="source-span">模拟选择：{{ candidate.simulated_selection }}</p>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card class="summary-card danger-card" shadow="never">
          <div class="summary-title danger-title">
            <el-icon><CircleCloseFilled /></el-icon>
            <span>C. 不可执行/需解释偏好</span>
          </div>
          <el-alert
            v-for="item in notExecutedPreferences"
            :key="item.id"
            class="not-executed-alert"
            type="error"
            :closable="false"
            show-icon
          >
            <template #title>{{ item.display }}</template>
            <p>{{ item.reason }}</p>
            <el-tag type="danger" effect="plain">
              不进入执行层
            </el-tag>
          </el-alert>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>
