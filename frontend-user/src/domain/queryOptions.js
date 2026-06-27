const REQUIRED_INPUT_LABELS = {
  user_rank: '用户位次',
};

const CAPABILITY_LABELS = {
  admissions_profile_only: '只能查看字段',
  admissions_filterable: '可字段筛选',
  admissions_major_rank: '可查询专业位次',
  admissions_candidate_list: '可查询候选列表',
  admissions_verified_recommendation: '可生成验证推荐',
  filterable: '可字段筛选',
  profile_only: '只能查看字段',
};

const READINESS_LABELS = {
  candidate_list: '可查询候选列表',
  verified_recommendation: '可生成验证推荐',
};

export function summarizeDatasetCapability(profile = {}) {
  const options = safeObject(profile.semantic_query_options);
  const queryTypes = stringList(options.query_types);
  const capabilityLevel = stringValue(profile.capability_level) || inferCapabilityLevel(queryTypes);
  const readiness = stringValue(profile.recommendation_readiness)
    || inferRecommendationReadiness(capabilityLevel, queryTypes);

  return {
    capabilityLevel,
    readiness,
    label: READINESS_LABELS[readiness] || CAPABILITY_LABELS[capabilityLevel] || '能力待确认',
    queryTypes,
    requiresUserRank: requiredContext(options).includes('user_rank'),
    canCallRecommendation:
      capabilityLevel === 'admissions_verified_recommendation'
      && readiness === 'verified_recommendation',
  };
}

export function buildQueryControls(options = {}) {
  const normalizedOptions = safeObject(options);
  return {
    requiredInputs: requiredContext(normalizedOptions).map((id) => ({
      id,
      label: REQUIRED_INPUT_LABELS[id] || id,
      type: id === 'user_rank' ? 'number' : 'text',
    })),
    filters: Object.entries(safeObject(normalizedOptions.filters)).map(([id, value]) => {
      const field = safeObject(value);
      const allowedOps = stringList(field.allowed_ops);
      return {
        id,
        label: stringValue(field.label) || stringValue(field.source_column) || id,
        sourceColumn: stringValue(field.source_column) || '',
        allowedOps,
        defaultOp: allowedOps[0] || 'eq',
        fieldType: stringValue(field.field_type) || 'text',
        inputType: stringValue(field.field_type) === 'number' ? 'number' : 'text',
      };
    }),
    sortFields: Object.entries(safeObject(normalizedOptions.sort_fields)).map(([id, value]) => {
      const field = safeObject(value);
      return {
        id,
        label: stringValue(field.label) || stringValue(field.source_column) || id,
        sourceColumn: stringValue(field.source_column) || '',
        fieldType: stringValue(field.field_type) || 'text',
      };
    }),
  };
}

export function buildWorkbenchPayload({
  prompt = '',
  userContext = {},
  filterValues = {},
  filterOps = {},
  options = {},
} = {}) {
  const normalizedOptions = safeObject(options);
  const text = normalizedPrompt(prompt);
  const hardFilters = {};

  for (const inputId of requiredContext(normalizedOptions)) {
    const value = parseContextValue(inputId, safeObject(userContext)[inputId]);
    if (hasValue(value)) {
      hardFilters[inputId] = value;
    }
  }

  const filters = safeObject(normalizedOptions.filters);
  for (const [fieldId, spec] of Object.entries(filters)) {
    const field = safeObject(spec);
    const rawValue = safeObject(filterValues)[fieldId];
    if (!hasValue(rawValue)) continue;
    const allowedOps = stringList(field.allowed_ops);
    const selectedOp = stringValue(safeObject(filterOps)[fieldId]);
    const op = allowedOps.includes(selectedOp) ? selectedOp : allowedOps[0];
    if (!op) continue;
    const value = parseFilterValue(rawValue, field.field_type, op);
    if (!hasValue(value)) continue;
    hardFilters[fieldId] = { op, value };
  }

  return {
    user_input: text,
    hard_filters: hardFilters,
    soft_preferences: {
      prompt: text,
    },
  };
}

function requiredContext(options = {}) {
  return stringList(safeObject(options).required_user_context);
}

function inferCapabilityLevel(queryTypes) {
  if (queryTypes.includes('semantic_recommendation')) {
    return 'admissions_candidate_list';
  }
  if (queryTypes.includes('admissions_major_rank')) {
    return 'admissions_major_rank';
  }
  return queryTypes.length ? 'filterable' : 'profile_only';
}

function inferRecommendationReadiness(capabilityLevel, queryTypes) {
  if (capabilityLevel === 'admissions_verified_recommendation') {
    return 'verified_recommendation';
  }
  if (
    capabilityLevel === 'admissions_candidate_list'
    || queryTypes.includes('semantic_recommendation')
  ) {
    return 'candidate_list';
  }
  return capabilityLevel === 'filterable' ? 'not_applicable' : 'not_ready';
}

function stringList(value) {
  return Array.isArray(value)
    ? value.filter((item) => typeof item === 'string' && item.length > 0)
    : [];
}

function stringValue(value) {
  return typeof value === 'string' && value.length > 0 ? value : '';
}

function safeObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function normalizedPrompt(value) {
  const text = typeof value === 'string' ? value.trim() : '';
  return text || '查询';
}

function parseContextValue(inputId, value) {
  if (inputId === 'user_rank') {
    return parseNumber(value);
  }
  return typeof value === 'string' ? value.trim() : value;
}

function parseFilterValue(rawValue, fieldType, op) {
  if (op === 'contains_any' || op === 'in') {
    const values = String(rawValue)
      .split(/[,，、\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    return fieldType === 'number' ? values.map(parseNumber).filter(hasValue) : values;
  }
  if (op === 'between') {
    const values = String(rawValue)
      .split(/[-~至到,，、\s]+/)
      .map(parseNumber)
      .filter(hasValue);
    return values.length >= 2 ? values.slice(0, 2) : [];
  }
  return fieldType === 'number' ? parseNumber(rawValue) : String(rawValue).trim();
}

function parseNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const text = String(value ?? '').trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function hasValue(value) {
  return value !== null
    && value !== undefined
    && value !== ''
    && !(Array.isArray(value) && value.length === 0);
}
