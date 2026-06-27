<script setup>
import { ref } from 'vue';
import {
  approveDomain,
  buildWarehouse,
  generateDomainPack,
  uploadDataset,
} from '../api/datasets.js';

const emit = defineEmits(['done', 'cancel']);

const file = ref(null);
const busy = ref(false);
const error = ref('');
const steps = ref([]);

function setFile(event) {
  file.value = event.target.files?.[0] || null;
}

async function runImport() {
  if (!file.value) {
    error.value = '请选择 Excel 或 CSV 文件。';
    return;
  }
  busy.value = true;
  error.value = '';
  steps.value = [];
  try {
    const uploaded = await recordStep('保存本机文件', () => uploadDataset({ file: file.value }));
    await recordStep('生成字段能力', () => generateDomainPack(uploaded.dataset_id, { llm: 'off' }));
    await recordStep('批准本机数据源', () => approveDomain(uploaded.dataset_id, {
      default_safe_sort: true,
    }));
    const built = await recordStep('生成可查询数据', () => buildWarehouse(uploaded.dataset_id));
    emit('done', { dataset_id: uploaded.dataset_id, ...built });
  } catch (exc) {
    error.value = exc.message || '导入失败。';
  } finally {
    busy.value = false;
  }
}

async function recordStep(label, action) {
  steps.value.push({ label, status: 'running' });
  const index = steps.value.length - 1;
  try {
    const result = await action();
    steps.value[index] = { label, status: 'done' };
    return result;
  } catch (exc) {
    steps.value[index] = { label, status: 'error' };
    throw exc;
  }
}

function stepLabel(status) {
  if (status === 'done') return '完成';
  if (status === 'running') return '进行中';
  if (status === 'error') return '失败';
  return status || '等待';
}
</script>

<template>
  <section class="page-section narrow-section">
    <button class="secondary-button inline-button" type="button" :disabled="busy" @click="emit('cancel')">
      返回数据源
    </button>
    <div>
      <p class="kicker">本机导入</p>
      <h2>导入表格</h2>
      <p class="state-line">表格会保存在本机，系统会按后端审查后的字段能力生成可查询数据源。</p>
    </div>
    <label class="file-picker">
      <span>Excel 或 CSV 文件</span>
      <input type="file" accept=".xlsx,.xls,.xlsm,.csv" :disabled="busy" @change="setFile" />
    </label>
    <p v-if="file" class="selected-file">{{ file.name }}</p>
    <button class="primary-button" type="button" :disabled="busy" @click="runImport">
      {{ busy ? '导入中' : '开始导入' }}
    </button>
    <ol v-if="steps.length" class="step-list">
      <li v-for="step in steps" :key="step.label" :data-status="step.status">
        <span>{{ step.label }}</span>
        <strong>{{ stepLabel(step.status) }}</strong>
      </li>
    </ol>
    <p v-if="error" class="error-line">{{ error }}</p>
  </section>
</template>
