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
    return attrValue(row, ['full_major_name', 'major_name']) || row.subtitle;
  }
  return row.full_major_name || row.major_name || `专业组代码：${row.group_code || '暂无'}`;
}

function collectAttributes(row) {
  if (isItem(row)) {
    const attributes = [
      ...(row.primary_attributes || []),
      ...(row.secondary_attributes || []),
    ];
    const byKey = Object.fromEntries(attributes.map((item) => [item.key, item.value]));
    return { ...(row.raw || {}), ...byKey };
  }
  return row || {};
}

function attrValue(row, keys) {
  const attributes = collectAttributes(row);
  for (const key of keys) {
    const value = attributes[key];
    if (value !== null && value !== undefined && value !== '') {
      return value;
    }
  }
  return '';
}

function rowGroup(row) {
  const code = attrValue(row, ['group_code', '院校专业组代码']);
  const name = attrValue(row, ['group_name', '专业组名称']);
  if (code && name) return `${code} · ${name}`;
  return code || name || '专业组暂无';
}

function resultFacts(row) {
  return [
    {
      key: 'city',
      label: '城市',
      value: attrValue(row, ['city', '城市']) || '暂无',
    },
    {
      key: 'tuition',
      label: '学费',
      value: formatMoney(attrValue(row, ['tuition', '学费'])),
    },
    {
      key: 'group_rank',
      label: '组位次',
      value: formatRank(attrValue(row, ['group_min_rank', 'rank_2024', '专业组最低位次1'])),
    },
    {
      key: 'major_rank',
      label: '专业位次',
      value: formatRank(attrValue(row, ['major_min_rank', 'major_rank_2024', '最低位次1'])),
    },
  ];
}

function rowMargin(row) {
  return attrValue(row, ['safety_margin']);
}

function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '暂无';
  const number = Number(value);
  if (!Number.isNaN(number)) {
    if (number >= 10000) {
      const valueInWan = number / 10000;
      const digits = Number.isInteger(valueInWan) ? 0 : 1;
      return `${valueInWan.toFixed(digits)}万`;
    }
    return `${Math.round(number)}元`;
  }
  return String(value);
}

function formatRank(value) {
  if (value === null || value === undefined || value === '') return '暂无';
  const number = Number(value);
  if (!Number.isNaN(number)) {
    return number.toLocaleString('zh-CN');
  }
  return String(value);
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
          <h2>可查看结果</h2>
        </div>
        <el-tag size="large" type="success">共 {{ total }} 条</el-tag>
      </div>
    </template>

    <el-empty v-if="!results.length" description="暂无结果" />

    <div v-else class="result-list">
      <article
        v-for="(row, index) in results"
        :key="row.item_id || row.id || `${rowTitle(row)}-${rowSubtitle(row)}`"
        class="result-item-card"
      >
        <div class="result-rank">{{ index + 1 }}</div>
        <div class="result-item-main">
          <div class="result-title-line">
            <strong>{{ rowTitle(row) }}</strong>
            <el-tag effect="plain">{{ rowGroup(row) }}</el-tag>
          </div>
          <p>{{ rowSubtitle(row) }}</p>
        </div>
        <div class="result-facts">
          <div
            v-for="item in resultFacts(row)"
            :key="item.key"
            class="result-fact"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div class="result-item-actions">
          <el-tag v-if="rowMargin(row)" type="warning" effect="plain">
            差距 {{ rowMargin(row) }}
          </el-tag>
          <el-tag type="success" effect="plain">命中 {{ matchedCount(row) }} 条</el-tag>
          <el-button
            type="primary"
            link
            :icon="View"
            @click="emit('view-trace', row)"
          >
            为什么
          </el-button>
        </div>
      </article>
    </div>
  </el-card>
</template>
