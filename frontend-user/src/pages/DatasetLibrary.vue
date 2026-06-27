<script setup>
import { summarizeDatasetCapability } from '../domain/queryOptions.js';

defineProps({
  datasets: {
    type: Array,
    default: () => [],
  },
  loading: Boolean,
  error: String,
});

const emit = defineEmits(['open-dataset', 'open-import', 'open-settings']);

function statusLabel(status) {
  if (status === 'queryable') return '可查询';
  if (status === 'uploaded') return '已导入';
  if (status === 'profiled') return '已分析';
  if (status === 'needs_review') return '待审查';
  if (status === 'approved') return '已批准';
  if (status === 'blocked') return '已阻断';
  return status || '未知状态';
}

function capabilityLabel(dataset) {
  return summarizeDatasetCapability(dataset).label;
}

function actionLabel(status) {
  return status === 'queryable' ? '开始查询' : '待完成导入';
}
</script>

<template>
  <section class="page-section">
    <div class="section-heading">
      <div>
        <h2>我的数据源</h2>
        <p>先选择本机表格，再进入查询页。</p>
      </div>
      <button class="primary-button" type="button" @click="emit('open-import')">
        导入表格
      </button>
    </div>

    <p v-if="loading" class="state-line">正在读取本机数据源...</p>
    <p v-else-if="error" class="error-line">{{ error }}</p>

    <div v-else-if="datasets.length" class="dataset-grid">
      <article
        v-for="dataset in datasets"
        :key="dataset.dataset_id"
        class="dataset-card"
      >
        <div class="status-strip" :data-status="dataset.status"></div>
        <div class="dataset-card-body">
          <div class="dataset-card-title">
            <div>
              <h3>{{ dataset.original_filename || dataset.dataset_id }}</h3>
              <p>本地表格</p>
            </div>
            <span>{{ statusLabel(dataset.status) }}</span>
          </div>
          <dl class="metric-grid">
            <div>
              <dt>记录</dt>
              <dd>{{ dataset.row_count ?? '-' }}</dd>
            </div>
            <div>
              <dt>字段</dt>
              <dd>{{ dataset.column_count ?? '-' }}</dd>
            </div>
            <div>
              <dt>能力</dt>
              <dd>{{ capabilityLabel(dataset) }}</dd>
            </div>
          </dl>
          <button
            class="primary-button full-width"
            type="button"
            :disabled="dataset.status !== 'queryable'"
            @click="emit('open-dataset', dataset.dataset_id)"
          >
            {{ actionLabel(dataset.status) }}
          </button>
        </div>
      </article>
    </div>

    <div v-else class="empty-panel">
      <h3>还没有本机数据源</h3>
      <p>导入 Excel 或 CSV 后，系统会在本机生成可查询数据，下次打开不用重新上传。</p>
      <div class="action-row">
        <button class="primary-button" type="button" @click="emit('open-import')">
          导入表格
        </button>
        <button class="secondary-button" type="button" @click="emit('open-settings')">
          配置 LLM
        </button>
      </div>
    </div>
  </section>
</template>
