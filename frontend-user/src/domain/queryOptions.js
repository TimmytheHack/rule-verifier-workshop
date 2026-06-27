const REQUIRED_INPUT_LABELS = {
  user_rank: '省排位',
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
      return {
        id,
        label: stringValue(field.label) || stringValue(field.source_column) || id,
        sourceColumn: stringValue(field.source_column) || '',
        allowedOps: stringList(field.allowed_ops),
        fieldType: stringValue(field.field_type) || 'text',
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
