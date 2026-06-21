export function formatModeTag(mode) {
  return mode === 'api'
    ? { type: 'warning', label: 'API 查询' }
    : { type: 'info', label: '演示数据' };
}

export function formatOptionsSourceTag(source) {
  const labels = {
    api: { type: 'success', label: '后端选项' },
    partial_fallback: { type: 'warning', label: '部分 fallback' },
    fallback: { type: 'info', label: 'fallback' },
  };
  return labels[source] || labels.fallback;
}

export function hasDisplayableRunData(runData) {
  if (!runData || runData.frontend_state?.source === 'empty' || runData.status === 'idle') {
    return false;
  }
  return Boolean(
    runData.frontend_state?.is_explicit_demo
    || runData.status === 'no_results'
    || (runData.items?.length || 0)
    || (runData.top_results?.length || 0)
    || (runData.result_count || 0),
  );
}
