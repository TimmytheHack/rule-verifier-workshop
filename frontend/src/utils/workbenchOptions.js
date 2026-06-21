export const FALLBACK_WORKBENCH_OPTIONS = {
  extractors: [
    { value: 'hybrid', label: '规则优先，LLM 补槽' },
    { value: 'regex', label: '规则解析软偏好' },
    { value: 'deepseek', label: 'LLM 辅助解析软偏好' },
  ],
  generators: [
    { value: 'template_evidence', label: '模板证据回答' },
    { value: 'deepseek_evidence', label: 'LLM 证据回答' },
  ],
  models: [
    { value: 'deepseek-v4-flash', label: 'LLM 快速模型' },
    { value: 'deepseek-v4-pro', label: 'LLM 高质量模型' },
  ],
  rank_windows: [
    {
      value: 'reach',
      label: '冲一冲',
      rank_window_lower_percent: 0,
      rank_window_upper_percent: 0,
      description: '只执行后 0% 上界，不设置前向下界。',
    },
    {
      value: 'steady',
      label: '稳一点',
      rank_window_lower_percent: 0,
      rank_window_upper_percent: 15,
      description: '只执行后 15% 上界，不设置前向下界。',
    },
    {
      value: 'safe',
      label: '保底',
      rank_window_lower_percent: 0,
      rank_window_upper_percent: 50,
      description: '只执行后 50% 上界，不设置前向下界。',
    },
  ],
  sort_modes: [
    { value: 'rank_asc', label: '按历史位次从高到低看（更冲）' },
    { value: 'rank_desc', label: '按历史位次从低到高看（更稳）' },
    { value: 'school_rank_asc', label: '同等条件下优先院校排名' },
  ],
};

const OPTION_GROUPS = [
  'extractors',
  'generators',
  'models',
  'rank_windows',
  'sort_modes',
];

export function normalizeWorkbenchOptions(payload) {
  const source = payload && typeof payload === 'object' ? 'api' : 'fallback';
  if (source === 'fallback') {
    return {
      source,
      ...cloneFallbackOptions(),
    };
  }

  const normalized = { source };
  let usedFallback = false;

  for (const group of OPTION_GROUPS) {
    const hasApiValues = Array.isArray(payload?.[group]) && payload[group].length;
    const values = hasApiValues ? payload[group] : cloneFallbackGroup(group);
    if (!hasApiValues) {
      usedFallback = true;
    }
    normalized[group] = hasApiValues ? values.map(normalizeOption) : values;
  }

  normalized.source = source === 'api' && usedFallback ? 'partial_fallback' : source;

  return normalized;
}

function cloneFallbackOptions() {
  return Object.fromEntries(
    OPTION_GROUPS.map((group) => [group, cloneFallbackGroup(group)]),
  );
}

function cloneFallbackGroup(group) {
  return FALLBACK_WORKBENCH_OPTIONS[group].map((option) => ({ ...option }));
}

export function normalizeOption(option) {
  return {
    ...option,
    value: option.value,
    label: option.label || option.value,
    description: option.description || '',
  };
}

export function firstOptionValue(options, fallback = '') {
  return Array.isArray(options) && options.length ? options[0].value : fallback;
}
