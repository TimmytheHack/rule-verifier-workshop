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
