import { ADMISSIONS_DOMAIN } from '../../domain/admissionsAdapter.js';
import {
  approvalFailureMessage,
  mergeApprovedDatasetState,
} from '../../utils/uploadDatasetState.js';

export const ADMISSIONS_IMPORT_STEPS = [
  { key: 'upload', label: '上传文件' },
  { key: 'domain_pack', label: '检查字段' },
  { key: 'profile', label: '读取表格结构' },
  { key: 'review_summary', label: '生成字段摘要' },
  { key: 'approve_domain', label: '确认字段模板' },
  { key: 'build_warehouse', label: '生成可查询数据' },
];

export async function runAdmissionsImportPipeline({ file, requestJson, onStep }) {
  if (!file) {
    throw new Error('请先选择 CSV 或 Excel 文件。');
  }
  const mark = (key, status, details = {}) => onStep?.({ key, status, details });
  const runStep = async (key, action, successDetails = {}) => {
    mark(key, 'running');
    try {
      const result = await action();
      mark(
        key,
        'success',
        typeof successDetails === 'function' ? successDetails(result) : successDetails,
      );
      return result;
    } catch (error) {
      mark(key, 'error', { message: errorMessage(error) });
      throw error;
    }
  };

  const params = new URLSearchParams({ filename: file.name });
  let dataset = await runStep(
    'upload',
    () => requestJson(`/datasets/upload?${params}`, {
      method: 'POST',
      body: file,
    }),
    (uploadedDataset) => ({ dataset_id: uploadedDataset.dataset_id }),
  );

  const datasetId = dataset.dataset_id;
  dataset = await runStep('domain_pack', () => (
    requestJson(`/datasets/${datasetId}/generate-domain-pack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        domain_name: ADMISSIONS_DOMAIN.domainName,
        template_id: ADMISSIONS_DOMAIN.templateId,
        llm: 'off',
      }),
    })
  ));

  const profile = await runStep(
    'profile',
    () => requestJson(`/datasets/${datasetId}/profile`),
    (profilePayload) => ({ field_count: profilePayload?.fields?.length ?? 0 }),
  );

  const reviewSummary = await runStep(
    'review_summary',
    () => requestJson(`/datasets/${datasetId}/review-summary`),
    (reviewSummaryPayload) => ({
      reviewable_fields: reviewSummaryPayload?.reviewable_fields?.length ?? 0,
    }),
  );

  await runStep('approve_domain', async () => {
    const approval = await requestJson(`/datasets/${datasetId}/approve-domain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title_field: 'university_name',
        primary_fields: ['group_code', 'major_name', 'city'],
        default_safe_sort: true,
      }),
    });
    dataset = mergeApprovedDatasetState(dataset, approval);
    const approvalMessage = approvalFailureMessage(approval);
    if (approvalMessage) {
      throw new Error(approvalMessage);
    }
    return approval;
  });

  dataset = await runStep(
    'build_warehouse',
    async () => {
      const warehouseDataset = await requestJson(`/datasets/${datasetId}/build-warehouse`, {
        method: 'POST',
      });
      assertQueryableWarehouseBuild(warehouseDataset);
      return warehouseDataset;
    },
    (warehouseDataset) => ({
      row_count: warehouseDataset?.warehouse?.row_count ?? warehouseDataset?.row_count ?? null,
    }),
  );

  return { dataset, profile, reviewSummary };
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error || '导入失败');
}

function assertQueryableWarehouseBuild(dataset) {
  if (dataset?.status !== 'queryable' || dataset?.warehouse_audit?.ok === false) {
    throw new Error(warehouseBuildFailureMessage(dataset));
  }
}

function warehouseBuildFailureMessage(dataset) {
  const warningCodes = (dataset?.warehouse_audit?.warnings || [])
    .map((warning) => warning?.code)
    .filter(Boolean);
  const suffix = warningCodes.length > 0
    ? `：${warningCodes.join('、')}`
    : '';
  return `生成可查询数据未通过校验${suffix}`;
}
