<script setup>
import { computed, onMounted, ref } from 'vue';
import { listDatasets } from './api/datasets.js';
import { getLlmSettings } from './api/settings.js';
import DatasetLibrary from './pages/DatasetLibrary.vue';
import SettingsPage from './pages/SettingsPage.vue';

const view = ref('library');
const datasets = ref([]);
const settings = ref({});
const loading = ref(false);
const error = ref('');
const selectedDatasetId = ref('');

const selectedDataset = computed(() =>
  datasets.value.find((dataset) => dataset.dataset_id === selectedDatasetId.value),
);

onMounted(refresh);

async function refresh() {
  loading.value = true;
  error.value = '';
  try {
    const [datasetPayload, settingsPayload] = await Promise.all([
      listDatasets(),
      getLlmSettings().catch(() => ({})),
    ]);
    datasets.value = Array.isArray(datasetPayload.datasets) ? datasetPayload.datasets : [];
    settings.value = settingsPayload || {};
  } catch (exc) {
    error.value = exc.message || '读取本机数据源失败。';
  } finally {
    loading.value = false;
  }
}

function openDataset(datasetId) {
  selectedDatasetId.value = datasetId;
  view.value = 'detail';
}

function handleSettingsSaved(payload) {
  settings.value = payload || {};
  view.value = 'library';
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="kicker">本机数据</p>
        <h1>本地表格工作台</h1>
      </div>
      <div class="topbar-actions">
        <button class="secondary-button" type="button" @click="refresh">
          刷新
        </button>
        <button class="secondary-button" type="button" @click="view = 'settings'">
          设置
        </button>
      </div>
    </header>

    <DatasetLibrary
      v-if="view === 'library'"
      :datasets="datasets"
      :loading="loading"
      :error="error"
      @open-dataset="openDataset"
      @open-import="view = 'import'"
      @open-settings="view = 'settings'"
    />
    <SettingsPage
      v-else-if="view === 'settings'"
      :settings="settings"
      @saved="handleSettingsSaved"
      @back="view = 'library'"
    />
    <section v-else-if="view === 'detail'" class="page-section detail-shell">
      <button class="secondary-button inline-button" type="button" @click="view = 'library'">
        返回数据源
      </button>
      <div class="detail-heading">
        <div>
          <p class="kicker">已选择数据源</p>
          <h2>{{ selectedDataset?.original_filename || selectedDatasetId }}</h2>
        </div>
        <span class="status-pill">{{ selectedDataset?.status || '未知状态' }}</span>
      </div>
      <p class="state-line">
        查询页将在下一步根据该数据源的后端 schema 能力生成，不在前端写死字段。
      </p>
    </section>
    <section v-else class="page-section detail-shell">
      <button class="secondary-button inline-button" type="button" @click="view = 'library'">
        返回数据源
      </button>
      <div>
        <p class="kicker">导入表格</p>
        <h2>导入流程将在下一步接入</h2>
      </div>
      <p class="state-line">
        当前页面先确保用户从本机数据源进入后续查询流程。
      </p>
    </section>
  </main>
</template>
