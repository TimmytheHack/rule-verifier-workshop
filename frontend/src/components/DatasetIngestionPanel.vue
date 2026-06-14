<script setup>
import { computed, ref } from 'vue';
import {
  Check,
  DataAnalysis,
  UploadFilled,
  Warning,
} from '@element-plus/icons-vue';

const file = ref(null);
const domainName = ref('admissions');
const baseDomain = ref('admissions');
const fieldId = ref('city');
const opFieldId = ref('city');
const opName = ref('in');
const queryText = ref('列出 2025 年深圳大学录取最高的专业组及专业组里面的各个专业最低录取分数');
const loading = ref(false);
const errorText = ref('');
const dataset = ref(null);
const profile = ref(null);
const reviewSummary = ref(null);
const queryResult = ref(null);

const datasetId = computed(() => dataset.value?.dataset_id || '');
const reviewFields = computed(() => reviewSummary.value?.reviewable_fields || []);
const sheetSummaries = computed(() => (
  profile.value?.sheet_summaries
  || dataset.value?.sheet_summaries
  || []
));
const datasetWarnings = computed(() => (
  profile.value?.warnings
  || dataset.value?.warnings
  || []
));
const requiredFields = computed(() => reviewSummary.value?.required_fields || []);
const missingFields = computed(() => reviewSummary.value?.missing_fields || []);
const riskyFields = computed(() => reviewSummary.value?.risky_fields || []);
const queryOverview = computed(() => {
  if (!queryResult.value) {
    return null;
  }
  return {
    status: queryResult.value.status,
    query_type: queryResult.value.query_type,
    result_count: queryResult.value.result_count,
    warnings: queryResult.value.warnings || [],
    section_keys: Object.keys(queryResult.value.result_sections || {}),
  };
});

function beforeUpload(selectedFile) {
  file.value = selectedFile;
  return false;
}

async function uploadDataset() {
  if (!file.value) {
    errorText.value = '请先选择 CSV 或 Excel 文件。';
    return;
  }
  await runStep(async () => {
    const params = new URLSearchParams({ filename: file.value.name });
    dataset.value = await requestJson(`/datasets/upload?${params}`, {
      method: 'POST',
      body: file.value,
    });
    profile.value = null;
    reviewSummary.value = null;
    queryResult.value = null;
  });
}

async function generateDomainPack() {
  await runStep(async () => {
    dataset.value = await requestJson(
      `/datasets/${datasetId.value}/generate-domain-pack`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain_name: domainName.value || null,
          base_domain: baseDomain.value || null,
          llm: 'off',
        }),
      },
    );
    await refreshProfile();
    await refreshReviewSummary();
  });
}

async function refreshProfile() {
  profile.value = await requestJson(`/datasets/${datasetId.value}/profile`);
}

async function refreshReviewSummary() {
  reviewSummary.value = await requestJson(`/datasets/${datasetId.value}/review-summary`);
}

async function approveField() {
  await reviewMutation('approve-field', { field_id: fieldId.value });
}

async function blockField() {
  await reviewMutation('block-field', { field_id: fieldId.value });
}

async function approveOp() {
  await reviewMutation('approve-op', {
    field_id: opFieldId.value,
    op: opName.value,
  });
}

async function approveDomain() {
  await runStep(async () => {
    dataset.value = await requestJson(`/datasets/${datasetId.value}/approve-domain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title_field: domainName.value === 'admissions' ? 'university_name' : null,
        primary_fields: domainName.value === 'admissions'
          ? ['group_code', 'major_name', 'city']
          : [],
        default_safe_sort: true,
      }),
    });
    await refreshReviewSummary();
  });
}

async function buildWarehouse() {
  await runStep(async () => {
    dataset.value = await requestJson(`/datasets/${datasetId.value}/build-warehouse`, {
      method: 'POST',
    });
  });
}

async function runUploadedQuery() {
  await runStep(async () => {
    queryResult.value = await requestJson('/workbench/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_id: datasetId.value,
        domain_name: domainName.value,
        user_input: queryText.value,
        soft_preferences: { prompt: queryText.value },
        extractor: 'regex',
        generator: 'template_evidence',
      }),
    });
  });
}

async function reviewMutation(action, payload) {
  await runStep(async () => {
    await requestJson(`/datasets/${datasetId.value}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    await refreshReviewSummary();
  });
}

async function runStep(fn) {
  loading.value = true;
  errorText.value = '';
  try {
    await fn();
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '数据集流程执行失败';
  } finally {
    loading.value = false;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail?.message || payload.detail || 'API 请求失败');
  }
  return payload;
}

function jsonText(value) {
  return JSON.stringify(value || {}, null, 2);
}
</script>

<template>
  <el-card class="workbench-card dataset-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <p class="section-kicker">Dataset / Ingestion API</p>
          <h2>上传数据集接入流程</h2>
        </div>
        <el-tag :type="dataset?.status === 'queryable' ? 'success' : 'warning'" effect="plain">
          {{ dataset?.status || '未上传' }}
        </el-tag>
      </div>
    </template>

    <el-alert
      class="inline-alert"
      type="warning"
      :closable="false"
      show-icon
      title="前端只调用上传、review、warehouse 和 Workbench API；自然语言不会在前端生成 hard filter。"
    />

    <div class="dataset-flow-grid">
      <section class="dataset-panel">
        <h3>上传与生成</h3>
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          :before-upload="beforeUpload"
          accept=".csv,.xlsx,.xls,.xlsm"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入或选择 CSV / Excel</div>
        </el-upload>

        <div class="compact-controls">
          <el-input v-model="domainName" placeholder="domain_name" />
          <el-input v-model="baseDomain" placeholder="base_domain，可为空" />
        </div>
        <div class="button-row">
          <el-button :icon="UploadFilled" type="primary" :loading="loading" @click="uploadDataset">
            上传
          </el-button>
          <el-button :icon="DataAnalysis" :disabled="!datasetId" :loading="loading" @click="generateDomainPack">
            生成 draft
          </el-button>
        </div>
      </section>

      <section class="dataset-panel">
        <h3>审查与批准</h3>
        <div class="compact-controls">
          <el-input v-model="fieldId" placeholder="field_id" />
          <el-input v-model="opFieldId" placeholder="op field_id" />
          <el-input v-model="opName" placeholder="op，例如 in / <=" />
        </div>
        <div class="button-row">
          <el-button :disabled="!datasetId" :loading="loading" @click="approveField">
            approve-field
          </el-button>
          <el-button :disabled="!datasetId" :loading="loading" @click="approveOp">
            approve-op
          </el-button>
          <el-button :icon="Warning" :disabled="!datasetId" :loading="loading" @click="blockField">
            block-field
          </el-button>
          <el-button :icon="Check" type="success" :disabled="!datasetId" :loading="loading" @click="approveDomain">
            approve-domain
          </el-button>
        </div>
        <el-button class="wide-button" :disabled="!datasetId" :loading="loading" @click="buildWarehouse">
          构建 warehouse
        </el-button>
      </section>

      <section class="dataset-panel query-panel">
        <h3>上传数据集查询</h3>
        <el-input
          v-model="queryText"
          type="textarea"
          :rows="4"
          placeholder="输入招生查询"
        />
        <el-button class="wide-button" type="primary" :disabled="!datasetId" :loading="loading" @click="runUploadedQuery">
          运行 WorkbenchResponse
        </el-button>
      </section>
    </div>

    <el-alert
      v-if="errorText"
      class="inline-alert"
      type="error"
      :closable="false"
      show-icon
      :title="errorText"
    />

    <section v-if="dataset" class="dataset-json-grid">
      <article>
        <h3>sheet list / header</h3>
        <div class="summary-line">
          <span>sheet</span>
          <strong>{{ profile?.sheet_name || dataset?.sheet_name || '-' }}</strong>
        </div>
        <div class="summary-line">
          <span>detected_header_row</span>
          <strong>{{ profile?.detected_header_row || dataset?.detected_header_row || '-' }}</strong>
        </div>
        <div class="sheet-list">
          <el-tag
            v-for="sheet in sheetSummaries"
            :key="sheet.sheet_name"
            class="field-tag"
            :type="sheet.selected ? 'success' : 'info'"
            effect="plain"
          >
            {{ sheet.sheet_name }} · {{ sheet.row_count }}x{{ sheet.column_count }}
          </el-tag>
        </div>
        <div class="warning-list">
          <el-tag
            v-for="warning in datasetWarnings"
            :key="warning.code + warning.message"
            class="field-tag"
            type="warning"
            effect="plain"
          >
            {{ warning.code }}
          </el-tag>
        </div>
      </article>
      <article>
        <h3>required / missing</h3>
        <div class="field-list">
          <el-tag
            v-for="field in requiredFields"
            :key="field.field_id"
            class="field-tag"
            :type="field.present ? 'success' : 'danger'"
            effect="plain"
          >
            {{ field.field_id }}
          </el-tag>
        </div>
        <p v-if="missingFields.length" class="risk-copy">
          missing：{{ missingFields.map((field) => field.field_id).join(', ') }}
        </p>
      </article>
      <article>
        <h3>risky fields</h3>
        <div class="field-list">
          <el-tag
            v-for="field in riskyFields"
            :key="field.field_id"
            class="field-tag"
            type="warning"
            effect="plain"
          >
            {{ field.field_id }} · {{ field.risk_flags.join('/') }}
          </el-tag>
        </div>
      </article>
      <article>
        <h3>dataset</h3>
        <pre>{{ jsonText(dataset) }}</pre>
      </article>
      <article>
        <h3>schema profile</h3>
        <pre>{{ jsonText(profile) }}</pre>
      </article>
      <article>
        <h3>review summary</h3>
        <pre>{{ jsonText(reviewSummary) }}</pre>
      </article>
    </section>

    <el-table v-if="reviewFields.length" class="review-table" :data="reviewFields" border stripe>
      <el-table-column prop="field_id" label="field_id" width="170" />
      <el-table-column prop="source_column" label="source_column" width="180" />
      <el-table-column prop="type" label="type" width="120" />
      <el-table-column label="seed ops" min-width="180">
        <template #default="{ row }">
          <el-tag v-for="op in row.seed_ops" :key="op" class="field-tag" effect="plain">
            {{ op }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="risk" min-width="180">
        <template #default="{ row }">
          <el-tag v-for="flag in row.risk_flags" :key="flag" class="field-tag" type="warning" effect="plain">
            {{ flag }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <section v-if="queryResult" class="dataset-json-grid result-json-grid">
      <article>
        <h3>query_type / status</h3>
        <pre>{{ jsonText(queryOverview) }}</pre>
      </article>
      <article>
        <h3>items</h3>
        <pre>{{ jsonText(queryResult.items) }}</pre>
      </article>
      <article>
        <h3>top_results</h3>
        <pre>{{ jsonText(queryResult.top_results) }}</pre>
      </article>
      <article>
        <h3>result_sections</h3>
        <pre>{{ jsonText(queryResult.result_sections) }}</pre>
      </article>
      <article>
        <h3>EvidencePack / warnings</h3>
        <pre>{{ jsonText({ evidence_pack: queryResult.evidence_pack, warnings: queryResult.warnings }) }}</pre>
      </article>
    </section>
  </el-card>
</template>
