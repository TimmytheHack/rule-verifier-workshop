export function defaultWorkbenchMode() {
  return 'api';
}

export function canRerunConfirmedRequest({
  context,
  candidateIds,
  currentMode,
  selectedDataSourceId,
  currentInputSignature,
}) {
  return Boolean(
    context?.requestBody
    && Array.isArray(candidateIds)
    && candidateIds.length
    && currentMode === 'api'
    && context.mode === 'api'
    && context.dataSourceId === selectedDataSourceId
    && (
      !context.inputSignature
      || context.inputSignature === currentInputSignature
    ),
  );
}

export function shouldShowOptionsLoadError(mode, optionsLoadError) {
  return mode === 'api' && Boolean(optionsLoadError);
}

export function isActiveWorkbenchResponse({
  requestId,
  activeRequestId,
  requestDataSourceId,
  selectedDataSourceId,
  requestMode,
  currentMode,
}) {
  return requestId === activeRequestId
    && requestDataSourceId === selectedDataSourceId
    && requestMode === currentMode;
}

export function describeDataSourceState({ mode, selectedDataSource, runData }) {
  if (mode !== 'demo') {
    return selectedDataSource?.description || '';
  }
  if (runData?.frontend_state?.is_explicit_demo) {
    return '当前显示演示结果；切到后端后使用所选数据。';
  }
  return '演示模式尚未加载演示结果；开始查询前不会展示演示院校。';
}

const GROUP_MAJOR_SCORE_KEYS = [
  'min_score',
  'major_min_score_2024',
  'major_min_score',
  '最低分1',
  '最低分数',
  '最低分',
];

const GROUP_MAJOR_TITLE_KEYS = [
  'full_major_name',
  '专业全称',
  'major_name',
  '专业名称',
];

function isRecord(value) {
  return Boolean(value && typeof value === 'object');
}

function hasDisplayValue(value) {
  return value !== null && value !== undefined && value !== '';
}

function isItemRow(row) {
  return isRecord(row) && Object.prototype.hasOwnProperty.call(row, 'item_id');
}

function collectDisplayAttributes(row) {
  if (!isRecord(row)) return {};
  if (!isItemRow(row)) return row;
  const attributes = [
    ...(row.primary_attributes || []),
    ...(row.secondary_attributes || []),
  ];
  const byKey = Object.fromEntries(
    attributes
      .filter((item) => item?.key || item?.label)
      .map((item) => [item.key || item.label, item.value]),
  );
  return { ...(row.raw || {}), ...byKey };
}

function displayAttrValue(row, keys) {
  const attributes = collectDisplayAttributes(row);
  for (const key of keys) {
    const value = attributes[key];
    if (hasDisplayValue(value)) return value;
  }
  return '';
}

function groupCode(row) {
  return displayAttrValue(row, ['group_code', '院校专业组代码']);
}

function mapKey(value) {
  return hasDisplayValue(value) ? String(value).trim() : '';
}

function isGroupDetailRow(row) {
  return Boolean(
    row?.group_detail === true
    || row?.query_type === 'group_detail_report'
    || hasDisplayValue(displayAttrValue(row, ['group_metric_score', 'group_title', 'major_count'])),
  );
}

export function groupMajorSections(row) {
  if (Array.isArray(row?.majors)) {
    return row.majors.filter(isRecord);
  }
  if (!Array.isArray(row?.items) || !isGroupDetailRow(row)) {
    return [];
  }
  return row.items.filter(isRecord);
}

export function groupMajorTitle(major) {
  return displayAttrValue(major, GROUP_MAJOR_TITLE_KEYS)
    || major?.title
    || '专业名称暂无';
}

export function groupMajorScore(major) {
  return displayAttrValue(major, GROUP_MAJOR_SCORE_KEYS);
}

export function formatGroupMajorScore(major) {
  const score = groupMajorScore(major);
  return hasDisplayValue(score) ? score : '分数暂无';
}

function groupRows(runData) {
  const groups = runData?.result_sections?.groups;
  return Array.isArray(groups) ? groups : [];
}

function groupDetailFallbackRow(group) {
  return {
    ...group,
    group_detail: true,
    university_name: group.university_name || group.group_title || '专业组明细',
    group_name: group.group_name || group.group_title,
  };
}

export function resultRowsForDisplay(runData) {
  const itemRows = Array.isArray(runData?.items) ? runData.items : [];
  const topRows = Array.isArray(runData?.top_results) ? runData.top_results : [];
  const baseRows = itemRows.length ? itemRows : topRows;
  if (runData?.query_type !== 'group_detail_report') {
    return baseRows;
  }

  const groups = groupRows(runData);
  if (!groups.length) {
    return baseRows;
  }
  if (!baseRows.length) {
    return groups.map(groupDetailFallbackRow);
  }

  const groupsByCode = new Map(
    groups
      .map((group) => [mapKey(group.group_code), group])
      .filter(([code]) => code),
  );

  return baseRows.map((row) => {
    const matchingGroup = groupsByCode.get(mapKey(groupCode(row)));
    const majors = groupMajorSections(matchingGroup);
    if (!majors.length) {
      return row;
    }
    return {
      ...row,
      group_detail: true,
      group_code: groupCode(row) || matchingGroup.group_code,
      group_name: displayAttrValue(row, ['group_name', '专业组名称'])
        || matchingGroup.group_name
        || matchingGroup.group_title,
      majors,
    };
  });
}
