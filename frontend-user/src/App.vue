<script setup>
import { computed, onMounted, ref } from 'vue';
import { listDatasets } from './api/datasets.js';
import { getLlmSettings } from './api/settings.js';
import ImportPanel from './components/ImportPanel.vue';
import { collapseDuplicateDatasets } from './domain/datasetList.js';
import DatasetLibrary from './pages/DatasetLibrary.vue';
import DatasetDetail from './pages/DatasetDetail.vue';
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
const datasetListView = computed(() => collapseDuplicateDatasets(datasets.value));

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

async function handleImportDone(payload) {
  await refresh();
  if (payload?.dataset_id) {
    selectedDatasetId.value = payload.dataset_id;
    view.value = 'detail';
    return;
  }
  view.value = 'library';
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div class="app-title">
        <p class="kicker">本机数据</p>
        <h1>本地表格工作台</h1>
      </div>
      <div class="topbar-actions">
        <button v-if="view !== 'settings'" class="secondary-button" type="button" @click="refresh">
          刷新
        </button>
        <button class="secondary-button" type="button" @click="view = 'settings'">
          设置
        </button>
      </div>
    </header>

    <DatasetLibrary
      v-if="view === 'library'"
      :datasets="datasetListView.datasets"
      :hidden-duplicate-count="datasetListView.hiddenCount"
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
    <DatasetDetail
      v-else-if="view === 'detail' && selectedDatasetId"
      :dataset-id="selectedDataset?.dataset_id || selectedDatasetId"
      @back="view = 'library'"
    />
    <ImportPanel
      v-else-if="view === 'import'"
      @done="handleImportDone"
      @cancel="view = 'library'"
    />
  </main>
</template>
