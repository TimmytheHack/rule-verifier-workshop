<script setup>
import { computed, ref } from 'vue';
import { UploadFilled } from '@element-plus/icons-vue';

import { ADMISSIONS_DOMAIN, createUploadedAdmissionsSource } from '../../domain/admissionsAdapter.js';
import { formatApiError } from '../../utils/apiError.js';
import { selectedRawUploadFile } from '../../utils/uploadFiles.js';
import ImportStepList from '../upload/ImportStepList.vue';
import { ADMISSIONS_IMPORT_STEPS, runAdmissionsImportPipeline } from '../upload/importPipeline.js';

const props = defineProps({
  activeSource: {
    type: Object,
    default: null,
  },
  authHeaders: {
    type: Function,
    required: true,
  },
});

const emit = defineEmits(['source-ready', 'open-review']);

const file = ref(null);
const loading = ref(false);
const errorText = ref('');
const importedSource = ref(null);
const steps = ref(initialSteps());

const canImport = computed(() => Boolean(file.value) && !loading.value);

function initialSteps() {
  return ADMISSIONS_IMPORT_STEPS.map((step) => ({
    ...step,
    status: 'idle',
    message: '',
  }));
}

function updateStep({ key, status, details = {} }) {
  steps.value = steps.value.map((step) => {
    if (step.key !== key) return step;
    return {
      ...step,
      status,
      message: details.message || step.message,
    };
  });
}

function handleFileChange(uploadFile) {
  const selectedFile = selectedRawUploadFile(uploadFile);
  if (selectedFile) {
    file.value = selectedFile;
    errorText.value = '';
    importedSource.value = null;
    steps.value = initialSteps();
  }
}

async function importAdmissionsFile() {
  if (!file.value) {
    errorText.value = '请先选择 CSV 或 Excel 文件。';
    return;
  }
  loading.value = true;
  errorText.value = '';
  importedSource.value = null;
  steps.value = initialSteps();
  try {
    const result = await runAdmissionsImportPipeline({
      file: file.value,
      requestJson,
      onStep: updateStep,
    });
    const datasetPayload = {
      ...result.dataset,
      file_name: result.dataset?.file_name ?? result.dataset?.source_name ?? file.value.name,
      domain_name: result.dataset?.domain_name ?? ADMISSIONS_DOMAIN.domainName,
    };
    const source = createUploadedAdmissionsSource(datasetPayload);
    if (!source) {
      throw new Error('导入完成但无法识别数据集编号。');
    }
    importedSource.value = source;
    emit('source-ready', datasetPayload);
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '导入失败';
  } finally {
    loading.value = false;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...props.authHeaders(),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const payload = parseResponseText(text);
  if (!response.ok) {
    if (payload && typeof payload === 'object') {
      throw new Error(formatApiError(payload, 'API 请求失败'));
    }
    throw new Error(`API 请求失败（HTTP ${response.status}）：${payload || response.statusText || '非 JSON 响应'}`);
  }
  return payload && typeof payload === 'object' ? payload : {};
}

function parseResponseText(text) {
  try {
    const payload = text ? JSON.parse(text) : {};
    return payload;
  } catch {
    return text || {};
  }
}
</script>

<template>
  <section class="workspace-panel single-scroll import-workspace">
    <el-card class="workbench-card import-main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h2>导入招生表</h2>
            <p class="panel-copy">选择招生 CSV / Excel 后，系统会自动检查字段并生成可查询数据。</p>
          </div>
          <el-tag effect="plain">上传招生表</el-tag>
        </div>
      </template>

      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        :on-change="handleFileChange"
        accept=".csv,.xlsx,.xls,.xlsm"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖入或选择 CSV / Excel</div>
      </el-upload>

      <div class="button-row">
        <el-button type="primary" :disabled="!canImport" :loading="loading" @click="importAdmissionsFile">
          导入并生成可查询数据
        </el-button>
        <el-button @click="emit('open-review')">打开字段审查</el-button>
      </div>

      <el-alert
        v-if="errorText"
        class="inline-alert"
        type="error"
        :closable="false"
        show-icon
        :title="errorText"
      />
      <el-alert
        v-if="importedSource"
        class="inline-alert"
        type="success"
        :closable="false"
        show-icon
        :title="`${importedSource.label} 已可查询`"
      />

      <ImportStepList :steps="steps" />
    </el-card>
  </section>
</template>
