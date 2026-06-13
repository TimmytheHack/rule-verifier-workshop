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

function isItem(row) {
  return row && Object.prototype.hasOwnProperty.call(row, 'item_id');
}

function rowTitle(row) {
  return isItem(row) ? row.title : row.university_name;
}

function rowSubtitle(row) {
  if (isItem(row)) {
    return row.subtitle;
  }
  return `专业组代码：${row.group_code || '暂无'}`;
}

function rowAttributes(row) {
  if (isItem(row)) {
    return [
      ...(row.primary_attributes || []),
      ...(row.secondary_attributes || []),
    ].slice(0, 8);
  }
  return [
    { key: 'major_name', label: '专业', value: row.major_name },
    { key: 'city', label: '城市', value: row.city },
    { key: 'tuition', label: '学费', value: row.tuition },
    { key: 'group_min_rank', label: '专业组最低位次', value: row.group_min_rank },
    { key: 'major_min_rank', label: '专业最低位次', value: row.major_min_rank },
    { key: 'safety_margin', label: '位次差距', value: row.safety_margin },
  ];
}

function matchedCount(row) {
  if (isItem(row)) {
    return (row.matched_filters || []).filter((item) => item.matched).length;
  }
  return (row.trace || []).filter((item) => item.status === 'pass').length;
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
        <el-table-column label="条目" min-width="220">
          <template #default="{ row }">
            <strong>{{ rowTitle(row) }}</strong>
            <p class="table-subtext">{{ rowSubtitle(row) }}</p>
          </template>
        </el-table-column>
        <el-table-column label="属性" min-width="420">
          <template #default="{ row }">
            <div class="attribute-list">
              <el-tag
                v-for="item in rowAttributes(row)"
                :key="item.key"
                effect="plain"
              >
                {{ item.label }}：{{ item.value ?? '暂无' }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="匹配规则" width="120">
          <template #default="{ row }">{{ matchedCount(row) }}</template>
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
