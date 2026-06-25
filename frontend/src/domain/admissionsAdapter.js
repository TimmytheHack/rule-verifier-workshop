export const ADMISSIONS_DOMAIN = {
  domainName: 'admissions',
  label: '招生录取数据',
  uploadMode: 'one_click_template',
  templateId: 'admissions_schema_v1',
  supportsPreflight: true,
  resultRenderer: 'admissions',
  requiredUserInputs: ['source_province', 'subject_type', 'user_rank'],
};

export const BUILTIN_ADMISSIONS_SOURCE = {
  id: 'builtin_admissions',
  type: 'builtin',
  datasetId: null,
  domainName: ADMISSIONS_DOMAIN.domainName,
  label: '内置招生数据',
  description: '使用仓库内置 admissions 数据。',
};

export function createUploadedAdmissionsSource(payload = {}) {
  if (!payload) {
    return null;
  }
  const datasetId = payload.dataset_id || payload.datasetId;
  if (!datasetId) {
    return null;
  }
  const rowCount = payload.warehouse?.row_count ?? payload.row_count ?? payload.rowCount ?? null;
  const columnCount = payload.warehouse?.column_count ?? payload.column_count ?? payload.columnCount ?? null;
  const fileName = payload.file_name || payload.source_name || payload.fileName || datasetId;
  const sizeText = rowCount && columnCount
    ? `${formatNumber(rowCount)} 行，${formatNumber(columnCount)} 列`
    : '已生成可查询数据';

  return {
    id: `uploaded:${datasetId}`,
    type: 'uploaded',
    datasetId,
    domainName: payload.domain_name || payload.domainName || ADMISSIONS_DOMAIN.domainName,
    label: `上传：${fileName}`,
    description: `${sizeText}，使用上传表格查询。`,
    rowCount,
    columnCount,
    updatedAt: payload.updated_at || payload.updatedAt || new Date().toISOString(),
  };
}

export function shouldUseUploadedAdmissionsPreflight(source, mode) {
  return mode === 'api'
    && source?.type === 'uploaded'
    && Boolean(source?.datasetId)
    && source?.domainName === ADMISSIONS_DOMAIN.domainName
    && ADMISSIONS_DOMAIN.supportsPreflight;
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isNaN(number) ? value : number.toLocaleString('zh-CN');
}
