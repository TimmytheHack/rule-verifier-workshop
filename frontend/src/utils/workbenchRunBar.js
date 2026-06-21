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
