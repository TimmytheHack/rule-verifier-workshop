import { candidateConfirmationSummary } from './workbenchState.js';

export function formatModeTag(mode) {
  return mode === 'api'
    ? { type: 'warning', label: '后端查询' }
    : { type: 'info', label: '演示数据' };
}

export function formatOptionsSourceTag(source) {
  const labels = {
    api: { type: 'success', label: '后端选项' },
    partial_fallback: { type: 'warning', label: '部分本地选项' },
    fallback: { type: 'info', label: '本地保守选项' },
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

export function normalizeRunBarStatus({ loading = false, lastRunFailed = false, runData = null } = {}) {
  if (loading) {
    return { type: 'warning', label: '查询中' };
  }
  if (lastRunFailed) {
    return { type: 'danger', label: '查询失败' };
  }
  if (!runData || runData.frontend_state?.source === 'empty' || runData.status === 'idle') {
    return { type: 'info', label: '待查询' };
  }

  if (runData.status === 'needs_confirmation') {
    const summary = candidateConfirmationSummary(runData);
    if (summary.hasConfirmable) {
      return { type: 'warning', label: '待确认' };
    }
    if (summary.hasWarningOnly) {
      return { type: 'info', label: '有提示' };
    }
    return { type: 'success', label: '已完成' };
  }

  const statusLabels = {
    blocked: { type: 'danger', label: '已阻断' },
    no_results: { type: 'info', label: '无结果' },
    ok: { type: 'success', label: '已完成' },
  };
  if (statusLabels[runData.status]) {
    return statusLabels[runData.status];
  }
  if (hasDisplayableRunData(runData)) {
    return { type: 'success', label: '已完成' };
  }
  return { type: 'info', label: '待查询' };
}
