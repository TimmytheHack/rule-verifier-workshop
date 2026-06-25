<script setup>
import { computed, ref } from 'vue';
import {
  Check,
  DataAnalysis,
  Refresh,
  Search,
  UploadFilled,
  Warning,
} from '@element-plus/icons-vue';
import { formatApiError } from '../utils/apiError';
import { selectedRawUploadFile } from '../utils/uploadFiles';
import { buildConfirmedWorkbenchRequest } from '../utils/workbenchRequests';
import {
  candidateIdentifier,
  splitCandidateConfirmationState,
} from '../utils/workbenchState';

const file = ref(null);
const domainName = ref('admissions');
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
const selectedCandidateIds = ref([]);
const auditEvents = ref([]);
const lastUploadedQueryContext = ref(null);
const DEFAULT_DEV_ACTOR_TOKEN = import.meta.env.DEV ? 'operator-token' : '';
const ADMISSIONS_SCHEMA_TEMPLATE_ID = 'admissions_schema_v1';

const emit = defineEmits(['source-ready']);

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
const candidatesToConfirm = computed(() => queryResult.value?.candidates_to_confirm || []);
const candidateConfirmationState = computed(() => splitCandidateConfirmationState({
  candidates_to_confirm: candidatesToConfirm.value,
}));
const selectableCandidates = computed(() => candidateConfirmationState.value.confirmable);
const blockedCandidates = computed(() => candidateConfirmationState.value.blocked);
const selectableCandidateIds = computed(() => new Set(
  selectableCandidates.value.map((candidate) => candidate.confirmationId),
));
const selectedConfirmableCandidateIds = computed(() => (
  selectedCandidateIds.value.filter((candidateId) => selectableCandidateIds.value.has(candidateId))
));
const canConfirmUploadedCandidates = computed(() => {
  const context = lastUploadedQueryContext.value;
  return Boolean(
    context?.requestBody
    && context.datasetId === datasetId.value
    && context.domainName === domainName.value
    && context.queryText === queryText.value,
  );
});
const queryItems = computed(() => queryResult.value?.items || []);
const sectionEntries = computed(() => Object.entries(queryResult.value?.result_sections || {}));
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
const queryStatusMessage = computed(() => {
  if (!queryResult.value) {
    return '';
  }
  const messages = {
    ok: '已按通过检查的条件筛选，可展示结果。',
    needs_confirmation: '存在待确认项或缺少必要信息，确认/补充前不会执行。',
    no_results: '查询正常但结果为 0，前端不能编造推荐。',
    blocked: '已拦截，没有参与筛选，请检查表格状态或确认记录。',
    error: '后端返回错误，前端不展示内部错误详情。',
  };
  return messages[queryResult.value.status] || '未知状态，请检查证据。';
});
const datasetSteps = computed(() => {
  const hasDataset = Boolean(dataset.value);
  const hasDatasetId = Boolean(datasetId.value);
  const hasProfileDraft = Boolean(profile.value || reviewSummary.value);
  const hasReviewSummary = Boolean(reviewSummary.value);
  const domainPackStatus = dataset.value?.domain_pack_status || '';
  const isDomainApproved = domainPackStatus === 'approved';
  const isQueryable = dataset.value?.status === 'queryable';
  const queryStatus = queryResult.value?.status || '';
  const queryStepStatus = queryResult.value
    ? stepStatusForQuery(queryStatus)
    : isQueryable ? 'process' : 'wait';

  return [
    {
      key: 'upload',
      title: '上传文件',
      description: file.value?.name || dataset.value?.source_name || '选择 CSV 或 Excel 文件',
      status: hasDataset ? 'success' : file.value ? 'process' : 'wait',
    },
    {
      key: 'draft',
      title: '生成草稿',
      description: hasDatasetId ? '生成 domain pack 和 schema profile' : '上传后可生成',
      status: hasProfileDraft ? 'success' : hasDatasetId ? 'process' : 'wait',
    },
    {
      key: 'review',
      title: '字段审查',
      description: hasReviewSummary ? `${reviewFields.value.length} 个可审查字段` : '生成草稿后查看',
      status: hasReviewSummary ? 'success' : hasProfileDraft ? 'process' : 'wait',
    },
    {
      key: 'approve',
      title: '批准领域',
      description: domainPackStatus || '审查后批准',
      status: isDomainApproved ? 'success' : hasReviewSummary ? 'process' : 'wait',
    },
    {
      key: 'warehouse',
      title: '生成可查询数据',
      description: isQueryable ? '已可查询' : '批准后建仓',
      status: isQueryable ? 'success' : isDomainApproved ? 'process' : 'wait',
    },
    {
      key: 'query',
      title: '试查',
      description: queryResult.value ? statusLabel(queryResult.value.status) : '建仓后试查',
      status: queryStepStatus,
    },
  ];
});
const activeDatasetStep = computed(() => {
  const nextStepIndex = datasetSteps.value.findIndex((step) => step.status !== 'success');
  return nextStepIndex === -1 ? datasetSteps.value.length : nextStepIndex;
});

const STATUS_LABELS = {
  ok: '已完成',
  queryable: '可查询',
  needs_confirmation: '待确认',
  no_results: '无结果',
  blocked: '已阻断',
  error: '错误',
  draft: '草稿',
  approved: '已批准',
  pass: '通过',
  fail: '失败',
};

const STAGE_LABELS = {
  upload: '上传',
  generate_domain_pack: '生成草稿',
  profile: '表格检查',
  review_summary: '字段检查',
  approve_field: '批准字段',
  'approve-field': '批准字段',
  approve_op: '批准条件',
  'approve-op': '批准条件',
  block_field: '阻断字段',
  'block-field': '阻断字段',
  approve_domain: '批准领域',
  build_warehouse: '生成可查询数据',
  query: '查询',
  confirm_query: '确认后再查',
};

function stepStatusForQuery(status) {
  if (status === 'ok') return 'success';
  if (status === 'needs_confirmation') return 'process';
  if (status === 'no_results') return 'wait';
  if (status === 'blocked' || status === 'error') return 'error';
  return 'process';
}

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

const OP_OPTIONS = [
  { value: 'in', label: '包含列表' },
  { value: '<=', label: '小于等于' },
  { value: '>=', label: '大于等于' },
  { value: '=', label: '等于' },
];

function handleFileChange(uploadFile) {
  const selectedFile = selectedRawUploadFile(uploadFile);
  if (selectedFile) {
    file.value = selectedFile;
    errorText.value = '';
  }
}

function handleFileRemove() {
  file.value = null;
}

function handleFileExceed(selectedFiles) {
  const selectedFile = selectedFiles?.[0] || null;
  if (selectedFile) {
    file.value = selectedFile;
    errorText.value = '';
  }
}

async function uploadDataset() {
  if (!file.value) {
    errorText.value = '请先选择 CSV 或 Excel 文件。';
    return;
  }
  await runStep('upload', async () => {
    const params = new URLSearchParams({ filename: file.value.name });
    dataset.value = await requestJson(`/datasets/upload?${params}`, {
      method: 'POST',
      body: file.value,
    });
    profile.value = null;
    reviewSummary.value = null;
    queryResult.value = null;
    clearUploadedQueryContext();
  });
}

async function generateDomainPack() {
  await runStep('generate_domain_pack', async () => {
    clearUploadedQueryContext();
    dataset.value = await requestJson(
      `/datasets/${datasetId.value}/generate-domain-pack`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain_name: domainName.value || null,
          template_id: domainName.value === 'admissions'
            ? ADMISSIONS_SCHEMA_TEMPLATE_ID
            : null,
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
  appendAuditEvent('profile', 'pass', {
    field_count: profile.value?.fields?.length || 0,
    warnings: profile.value?.warnings?.length || 0,
  });
}

async function refreshReviewSummary() {
  reviewSummary.value = await requestJson(`/datasets/${datasetId.value}/review-summary`);
  appendAuditEvent('review_summary', 'pass', {
    reviewable_fields: reviewSummary.value?.reviewable_fields?.length || 0,
    missing_fields: reviewSummary.value?.missing_fields?.length || 0,
    risky_fields: reviewSummary.value?.risky_fields?.length || 0,
  });
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
  await runStep('approve_domain', async () => {
    clearUploadedQueryContext();
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
  await runStep('build_warehouse', async () => {
    clearUploadedQueryContext();
    dataset.value = await requestJson(`/datasets/${datasetId.value}/build-warehouse`, {
      method: 'POST',
    });
    if (dataset.value?.status === 'queryable') {
      emit('source-ready', sourceReadyPayload(dataset.value));
    }
  });
}

async function runUploadedQuery(confirmedCandidateIds = []) {
  const isConfirmedRerun = confirmedCandidateIds.length > 0;
  const requestBody = isConfirmedRerun
    ? confirmedUploadedQueryRequest(confirmedCandidateIds)
    : uploadedQueryRequest();
  if (!requestBody) {
    return;
  }
  if (!isConfirmedRerun) {
    clearUploadedQueryContext();
  }
  await runStep(
    isConfirmedRerun ? 'query_confirmed_rerun' : 'query',
    async () => {
      queryResult.value = await requestJson('/workbench/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });
      lastUploadedQueryContext.value = uploadedQueryContext(requestBody);
      selectedCandidateIds.value = [];
    },
  );
}

async function confirmSelectedCandidates() {
  const candidateIds = selectedConfirmableCandidateIds.value;
  if (!candidateIds.length) {
    errorText.value = '请先勾选要确认的项目。';
    return;
  }
  await runUploadedQuery(candidateIds);
}

async function reviewMutation(action, payload) {
  await runStep(action, async () => {
    clearUploadedQueryContext();
    await requestJson(`/datasets/${datasetId.value}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    await refreshReviewSummary();
  });
}

async function runStep(stage, fn) {
  loading.value = true;
  errorText.value = '';
  const started = Date.now();
  try {
    await fn();
    appendAuditEvent(stage, 'pass', {
      duration_ms: Date.now() - started,
      dataset_id: datasetId.value || null,
      status: queryResult.value?.status || dataset.value?.status || null,
    });
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : '数据集流程执行失败';
    appendAuditEvent(stage, 'fail', {
      duration_ms: Date.now() - started,
      message: errorText.value,
    });
  } finally {
    loading.value = false;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(formatApiError(payload, 'API 请求失败'));
  }
  return payload;
}

function jsonText(value) {
  return JSON.stringify(value || {}, null, 2);
}

function appendAuditEvent(stage, status, details = {}) {
  auditEvents.value = [
    {
      id: `${Date.now()}_${stage}`,
      created_at: new Date().toLocaleTimeString(),
      stage,
      status,
      details,
    },
    ...auditEvents.value,
  ].slice(0, 20);
}

function sourceReadyPayload(payload) {
  return {
    dataset_id: payload?.dataset_id || datasetId.value,
    domain_name: payload?.domain_name || domainName.value || 'admissions',
    file_name: file.value?.name || payload?.source_name || payload?.dataset_id,
    row_count: payload?.warehouse?.row_count || payload?.row_count || null,
    column_count: payload?.warehouse?.column_count || payload?.column_count || null,
    status: payload?.status,
    updated_at: payload?.updated_at,
  };
}

function uploadedQueryRequest() {
  return {
    dataset_id: datasetId.value,
    domain_name: domainName.value,
    user_input: queryText.value,
    soft_preferences: { prompt: queryText.value },
    extractor: 'regex',
    generator: 'template_evidence',
    confirmed_candidates: [],
  };
}

function confirmedUploadedQueryRequest(candidateIds) {
  if (!canConfirmUploadedCandidates.value) {
    errorText.value = '查询文本或数据集状态已变化，请先重新查询后再确认。';
    selectedCandidateIds.value = [];
    return null;
  }
  return buildConfirmedWorkbenchRequest(
    lastUploadedQueryContext.value.requestBody,
    candidateIds,
  );
}

function uploadedQueryContext(requestBody) {
  return {
    requestBody,
    datasetId: requestBody.dataset_id,
    domainName: requestBody.domain_name,
    queryText: requestBody.user_input,
  };
}

function clearUploadedQueryContext() {
  lastUploadedQueryContext.value = null;
  selectedCandidateIds.value = [];
}

function authHeaders() {
  const token = window.localStorage.getItem('actor_token') || DEFAULT_DEV_ACTOR_TOKEN;
  return token ? { 'X-Actor-Token': token } : {};
}

function statusType(status) {
  if (status === 'ok' || status === 'queryable') return 'success';
  if (status === 'needs_confirmation') return 'warning';
  if (status === 'no_results') return 'info';
  if (status === 'blocked' || status === 'error') return 'danger';
  return 'warning';
}

function candidateTitle(candidate) {
  return (
    candidate.label
    || candidate.preference
    || candidate.value
    || candidate.normalized_value
    || candidateIdentifier(candidate)
  );
}

function candidateSummary(candidate) {
  return candidate.reason || candidate.match_type || candidate.field_id || '待用户确认';
}

function itemAttributes(item) {
  return [
    ...(item.primary_attributes || []),
    ...(item.secondary_attributes || []),
  ].slice(0, 6).map((attribute) => ({
    ...attribute,
    displayLabel: (
      ATTRIBUTE_LABELS[attribute.key]
      || ATTRIBUTE_LABELS[attribute.label]
      || attribute.label
      || attribute.key
    ),
  }));
}

function queryTypeLabel(value) {
  const labels = {
    verified_filter: '筛选查询',
    group_detail_report: '专业组明细',
    recommendation: '推荐分组',
  };
  return labels[value] || value || '未知查询';
}

function statusLabel(value) {
  return STATUS_LABELS[value] || value || '未上传';
}

function stageLabel(value) {
  return STAGE_LABELS[value] || value || '未知操作';
}
</script>

<template>
  <el-card class="workbench-card dataset-card" shadow="never">
    <template #header>
      <div class="card-header">
        <div>
          <h2>上传数据</h2>
        </div>
        <el-tag :type="statusType(dataset?.status)" effect="plain">
          {{ statusLabel(dataset?.status) }}
        </el-tag>
      </div>
    </template>

    <el-alert
      class="inline-alert"
      type="warning"
      :closable="false"
      show-icon
      title="前端只提交操作，规则是否执行由后端验证。"
    />

    <div class="dataset-steps">
      <el-steps :active="activeDatasetStep" finish-status="success" align-center>
        <el-step
          v-for="step in datasetSteps"
          :key="step.key"
          :title="step.title"
          :description="step.description"
          :status="step.status"
        />
      </el-steps>
    </div>

    <div class="dataset-flow-grid">
      <section class="dataset-panel">
        <h3>上传与生成</h3>
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :on-exceed="handleFileExceed"
          accept=".csv,.xlsx,.xls,.xlsm"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入或选择 CSV / Excel</div>
        </el-upload>

        <div class="compact-controls">
          <el-input v-model="domainName" placeholder="数据类型" />
          <el-alert
            class="template-hint"
            type="info"
            :closable="false"
            title="使用 admissions_schema_v1 字段模板；只读取上传文件，不读取内置招生表行。"
          />
        </div>
        <div class="button-row">
          <el-button :icon="UploadFilled" type="primary" :loading="loading" @click="uploadDataset">
            上传
          </el-button>
          <el-button :icon="DataAnalysis" :disabled="!datasetId" :loading="loading" @click="generateDomainPack">
            生成草稿
          </el-button>
        </div>
      </section>

      <section class="dataset-panel">
        <h3>审查与批准</h3>
        <div class="compact-controls">
          <el-input v-model="fieldId" placeholder="字段名" />
          <el-input v-model="opFieldId" placeholder="条件字段" />
          <el-select v-model="opName" placeholder="选择条件">
            <el-option
              v-for="option in OP_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </div>
        <div class="button-row">
          <el-button :disabled="!datasetId" :loading="loading" @click="approveField">
            批准字段
          </el-button>
          <el-button :disabled="!datasetId" :loading="loading" @click="approveOp">
            批准条件
          </el-button>
          <el-button :icon="Warning" :disabled="!datasetId" :loading="loading" @click="blockField">
            阻断字段
          </el-button>
          <el-button :icon="Check" type="success" :disabled="!datasetId" :loading="loading" @click="approveDomain">
            批准领域
          </el-button>
        </div>
        <el-button class="wide-button" :disabled="!datasetId" :loading="loading" @click="buildWarehouse">
          生成可查询数据
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
        <el-button
          class="wide-button"
          type="primary"
          :icon="Search"
          :disabled="!datasetId"
          :loading="loading"
          @click="runUploadedQuery()"
        >
          查询
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

    <el-collapse v-if="dataset" class="dataset-debug-collapse">
      <el-collapse-item title="调试数据" name="debug">
        <section class="dataset-json-grid">
          <article>
            <h3>工作表与表头</h3>
            <div class="summary-line">
              <span>工作表</span>
              <strong>{{ profile?.sheet_name || dataset?.sheet_name || '-' }}</strong>
            </div>
            <div class="summary-line">
              <span>表头行</span>
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
            <h3>必需字段</h3>
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
              缺失：{{ missingFields.map((field) => field.field_id).join(', ') }}
            </p>
          </article>
          <article>
            <h3>风险字段</h3>
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
            <h3>数据概况</h3>
            <pre>{{ jsonText(dataset) }}</pre>
          </article>
          <article>
            <h3>表格检查</h3>
            <pre>{{ jsonText(profile) }}</pre>
          </article>
          <article>
            <h3>审查摘要</h3>
            <pre>{{ jsonText(reviewSummary) }}</pre>
          </article>
          <article>
            <h3>前端操作审计记录</h3>
            <div v-if="auditEvents.length" class="audit-event-list">
              <div v-for="event in auditEvents" :key="event.id" class="audit-event">
                <div class="audit-event-main">
                  <strong>{{ stageLabel(event.stage) }}</strong>
                  <span>{{ event.created_at }}</span>
                </div>
                <el-tag :type="event.status === 'pass' ? 'success' : 'danger'" effect="plain">
                  {{ statusLabel(event.status) }}
                </el-tag>
                <pre>{{ jsonText(event.details) }}</pre>
              </div>
            </div>
            <el-empty v-else description="尚无前端操作记录" />
          </article>
        </section>
      </el-collapse-item>
    </el-collapse>

    <el-table v-if="reviewFields.length" class="review-table" :data="reviewFields" border stripe>
      <el-table-column prop="field_id" label="字段" width="170" />
      <el-table-column prop="source_column" label="来源列" width="180" />
      <el-table-column prop="type" label="类型" width="120" />
      <el-table-column label="建议条件" min-width="180">
        <template #default="{ row }">
          <el-tag v-for="op in row.seed_ops" :key="op" class="field-tag" effect="plain">
            {{ op }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="风险" min-width="180">
        <template #default="{ row }">
          <el-tag v-for="flag in row.risk_flags" :key="flag" class="field-tag" type="warning" effect="plain">
            {{ flag }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <section v-if="queryResult" class="query-response-panel">
      <div class="query-status-row">
        <el-tag size="large" :type="statusType(queryResult.status)" effect="light">
          {{ statusLabel(queryResult.status) }}
        </el-tag>
        <strong>{{ queryTypeLabel(queryResult.query_type) }}</strong>
        <span>{{ queryStatusMessage }}</span>
      </div>

      <el-alert
        v-for="warning in queryResult.warnings || []"
        :key="warning.code + warning.message"
        class="inline-alert"
        :type="warning.severity === 'error' ? 'error' : 'warning'"
        :closable="false"
        show-icon
        :title="`${warning.code}: ${warning.message}`"
      />

      <section v-if="candidatesToConfirm.length" class="confirmation-workflow">
        <div class="card-header">
          <div>
            <h3>待确认项</h3>
          </div>
          <el-button
            :icon="Refresh"
            type="warning"
            :disabled="!canConfirmUploadedCandidates || !selectedConfirmableCandidateIds.length"
            :loading="loading"
            @click="confirmSelectedCandidates"
          >
            确认后再查
          </el-button>
        </div>
        <el-alert
          v-if="selectableCandidates.length && !canConfirmUploadedCandidates"
          class="inline-alert"
          type="warning"
          :closable="false"
          show-icon
          title="查询文本或数据集状态已变化，请先重新查询后再确认。"
        />
        <el-checkbox-group
          v-if="selectableCandidates.length"
          v-model="selectedCandidateIds"
          class="candidate-checkboxes"
        >
          <label
            v-for="candidate in selectableCandidates"
            :key="candidate.confirmationId"
            class="candidate-confirm-row"
          >
            <el-checkbox :label="candidate.confirmationId">
              确认使用
            </el-checkbox>
            <strong>{{ candidateTitle(candidate) }}</strong>
            <span>{{ candidateSummary(candidate) }}</span>
          </label>
        </el-checkbox-group>
        <div v-if="blockedCandidates.length" class="warning-list">
          <el-alert
            v-for="candidate in blockedCandidates"
            :key="candidate.preference || candidate.reason || candidate.label"
            type="warning"
            :closable="false"
            show-icon
            :title="`${candidateTitle(candidate)}：缺少系统生成的 candidate_id，只展示不确认。`"
          />
        </div>
      </section>

      <section v-if="queryItems.length" class="item-card-grid">
        <article v-for="item in queryItems" :key="item.item_id" class="item-card">
          <div class="item-card-title">
            <strong>{{ item.title }}</strong>
            <el-tag effect="plain">{{ item.item_id }}</el-tag>
          </div>
          <p>{{ item.subtitle }}</p>
          <div class="field-list">
            <el-tag
              v-for="attribute in itemAttributes(item)"
              :key="attribute.key"
              effect="plain"
              class="field-tag"
            >
              {{ attribute.displayLabel }}：{{ attribute.value ?? '暂无' }}
            </el-tag>
          </div>
        </article>
      </section>

      <section v-if="sectionEntries.length" class="section-summary-grid">
        <article v-for="[key, value] in sectionEntries" :key="key">
          <h3>{{ key }}</h3>
          <pre>{{ jsonText(value) }}</pre>
        </article>
      </section>
    </section>

    <section v-if="queryResult" class="dataset-json-grid result-json-grid">
      <article>
        <h3>查询状态</h3>
        <pre>{{ jsonText(queryOverview) }}</pre>
      </article>
      <article>
        <h3>结果条目</h3>
        <pre>{{ jsonText(queryResult.items) }}</pre>
      </article>
      <article>
        <h3>兼容结果</h3>
        <pre>{{ jsonText(queryResult.top_results) }}</pre>
      </article>
      <article>
        <h3>分组结果</h3>
        <pre>{{ jsonText(queryResult.result_sections) }}</pre>
      </article>
      <article>
        <h3>筛选依据与提醒</h3>
        <pre>{{ jsonText({ evidence_pack: queryResult.evidence_pack, warnings: queryResult.warnings }) }}</pre>
      </article>
    </section>
  </el-card>
</template>
