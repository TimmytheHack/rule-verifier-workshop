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

const ATTRIBUTE_LABELS = {
  year: '年份',
  batch: '批次',
  university_code: '院校代码',
  university_name: '院校名称',
  group_code: '专业组代码',
  group_name: '专业组名称',
  major_code: '专业代码',
  major_name: '专业名称',
  full_major_name: '专业全称',
  city: '城市',
  tuition: '学费',
  rank_2024: '2024 位次',
  score_2024: '2024 分数',
  plan_count: '招生计划',
  subject_requirement: '选科要求',
  group_min_rank: '专业组最低位次',
  major_min_rank: '专业最低位次',
  safety_margin: '位次差距',
};

function isItem(row) {
  return row && Object.prototype.hasOwnProperty.call(row, 'item_id');
}

function attributeLabel(item) {
  return ATTRIBUTE_LABELS[item.key] || ATTRIBUTE_LABELS[item.label] || item.label || item.key;
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
    const attributes = [
      ...(row.primary_attributes || []),
      ...(row.secondary_attributes || []),
    ];
    const byKey = new Map(attributes.map((item) => [item.key, item]));
    const preferredKeys = [
      'major_code',
      'major_name',
      'city',
      'tuition',
      'group_min_rank',
      'major_min_rank',
      'rank_2024',
      'plan_count',
    ];
    const preferred = preferredKeys
      .map((key) => byKey.get(key))
      .filter(Boolean);
    return (preferred.length ? preferred : attributes.slice(0, 6)).map((item) => ({
      ...item,
      displayLabel: attributeLabel(item),
    }));
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
          <h2>筛选结果</h2>
        </div>
        <el-tag size="large" type="success">总数：{{ total }}</el-tag>
      </div>
    </template>

    <div class="result-list">
      <article
        v-for="row in results"
        :key="row.item_id || row.id || `${rowTitle(row)}-${rowSubtitle(row)}`"
        class="result-item-card"
      >
        <div class="result-item-main">
          <strong>{{ rowTitle(row) }}</strong>
          <p>{{ rowSubtitle(row) }}</p>
        </div>
        <div class="attribute-list">
          <el-tag
            v-for="item in rowAttributes(row)"
            :key="item.key"
            effect="plain"
          >
            {{ item.displayLabel || item.label }}：{{ item.value ?? '暂无' }}
          </el-tag>
        </div>
        <div class="result-item-actions">
          <el-tag type="success" effect="plain">通过 {{ matchedCount(row) }} 条</el-tag>
          <el-button
            type="primary"
            link
            :icon="View"
            @click="emit('view-trace', row)"
          >
            查看原因
          </el-button>
        </div>
      </article>
    </div>
  </el-card>
</template>
