const TERMINAL_PUNCTUATION = /[。！？!?]+$/u;
const TRAILING_PUNCTUATION_OR_SPACE = /[。！？!?；;，,\s]+$/u;

export function primaryWorkbenchRunLabel({
  loading,
  shouldUsePreflight,
  currentPreflightCanQuery,
  currentPreflightReady,
  mode,
}) {
  if (loading) {
    return shouldUsePreflight && !currentPreflightCanQuery ? '正在预检' : '正在查询';
  }
  if (!shouldUsePreflight) {
    return mode === 'api' ? '开始查询' : '演示结果';
  }
  if (currentPreflightCanQuery) {
    return '确认后查询';
  }
  return currentPreflightReady ? '重新预检' : '先做预检';
}

export function workbenchProcessingStatus({
  status = 'ok',
  confirmationSummary = {},
} = {}) {
  if (status === 'needs_confirmation') {
    if (confirmationSummary.confirmableCount > 0) {
      return { label: '待确认', tone: 'needs_confirmation' };
    }
    if (confirmationSummary.warningOnlyCount > 0) {
      return { label: '有提示', tone: 'info' };
    }
    return { label: '已完成', tone: 'ok' };
  }

  const labels = {
    idle: '待查询',
    ready: '可查询',
    ok: '通过',
    no_results: '无结果',
    blocked: '已阻断',
    error: '错误',
  };
  const tones = {
    idle: 'info',
    ready: 'info',
    ok: 'ok',
    no_results: 'info',
    blocked: 'blocked',
    error: 'error',
  };
  return {
    label: labels[status] || status,
    tone: tones[status] || 'info',
  };
}

export function mergePromptText(currentPrompt, addition) {
  const current = cleanPrompt(currentPrompt);
  const next = cleanPrompt(addition);
  if (!next) return current;
  if (!current) return sentenceWithPeriod(next);
  if (hasPromptText(current, next)) return sentenceWithPeriod(current);
  return `${sentenceWithPeriod(current)}${sentenceWithPeriod(next)}`;
}

function cleanPrompt(value) {
  return String(value || '').trim();
}

function hasPromptText(left, right) {
  const normalizedLeft = comparablePrompt(left);
  const normalizedRight = comparablePrompt(right);
  return Boolean(normalizedRight) && normalizedLeft.includes(normalizedRight);
}

function comparablePrompt(value) {
  return cleanPrompt(value).replace(TRAILING_PUNCTUATION_OR_SPACE, '');
}

function sentenceWithPeriod(value) {
  const text = cleanPrompt(value);
  if (!text) return '';
  return TERMINAL_PUNCTUATION.test(text) ? text : `${text}。`;
}
