export function mergeApprovedDatasetState(currentDataset, approvalResult) {
  if (!currentDataset) {
    return approvalResult || null;
  }
  if (!approvalResult?.ok) {
    return {
      ...currentDataset,
      last_review_result: approvalResult || null,
    };
  }
  const domainPackStatus = (
    approvalResult.payload?.domain_pack_status
    || approvalResult.domain_pack_status
    || 'approved'
  );
  return {
    ...currentDataset,
    status: 'approved',
    domain_pack_status: domainPackStatus,
    last_review_result: approvalResult,
  };
}

export function approvalFailureMessage(approvalResult) {
  if (!approvalResult || approvalResult.ok !== false) {
    return '';
  }
  const failures = Array.isArray(approvalResult.payload?.failures)
    ? approvalResult.payload.failures.filter(Boolean)
    : [];
  if (failures.length) {
    return `字段模板审核未通过：${failures.join('；')}`;
  }
  return approvalResult.message
    ? `字段模板审核未通过：${approvalResult.message}`
    : '字段模板审核未通过。';
}

export function admissionsTemplateMismatchMessage(dataset, domainName, expectedTemplateId) {
  if (
    domainName !== 'admissions'
    || !dataset
    || dataset.domain_name !== 'admissions'
    || dataset.domain_template_id === expectedTemplateId
  ) {
    return '';
  }
  return `后端没有应用 ${expectedTemplateId} 字段模板。请重启后端后重新生成草稿。`;
}
