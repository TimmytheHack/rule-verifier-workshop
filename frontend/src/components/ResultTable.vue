<script setup>
import { View } from '@element-plus/icons-vue';

defineProps({
  results: {
    type: Array,
    required: true,
  },
  total: {
    type: Number,
    required: true,
  },
});

const emit = defineEmits(['view-trace']);

function formatNumber(value) {
  if (value === null || value === undefined || value === '') {
    return '暂无';
  }
  return new Intl.NumberFormat('zh-CN').format(value);
}
</script>

<template>
  <el-card class="workbench-card result-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">执行层</p>
          <h2>基于已验证规则的筛选结果</h2>
        </div>
        <el-tag size="large" type="success">总数：{{ total }}</el-tag>
      </div>
    </template>

    <div class="table-scroll">
      <el-table :data="results" border stripe>
        <el-table-column label="院校名称" min-width="180">
          <template #default="{ row }">
            <strong>{{ row.university_name }}</strong>
            <p class="table-subtext">专业组代码：{{ row.group_code }}</p>
          </template>
        </el-table-column>
        <el-table-column label="专业" min-width="260">
          <template #default="{ row }">
            <strong>{{ row.major_name }}</strong>
            <p class="table-subtext">专业代码：{{ row.major_code || '暂无' }}</p>
            <p v-if="row.full_major_name" class="table-subtext compact-major">
              {{ row.full_major_name }}
            </p>
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="110" />
        <el-table-column label="选科要求" width="120">
          <template #default="{ row }">
            {{ row.subject_requirement || '不限' }}
          </template>
        </el-table-column>
        <el-table-column label="学费" width="120">
          <template #default="{ row }">
            ¥{{ formatNumber(row.tuition) }}
          </template>
        </el-table-column>
        <el-table-column label="专业组最低位次" width="150">
          <template #default="{ row }">
            {{ formatNumber(row.group_min_rank) }}
          </template>
        </el-table-column>
        <el-table-column label="专业最低位次" width="140">
          <template #default="{ row }">
            {{ formatNumber(row.major_min_rank) }}
          </template>
        </el-table-column>
        <el-table-column label="位次差距" width="120">
          <template #default="{ row }">
            <el-tag :type="row.safety_margin ? 'success' : 'info'" effect="plain">
              {{ row.safety_margin || '未计算' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              :icon="View"
              @click="emit('view-trace', row)"
            >
              查看 Trace
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-card>
</template>
