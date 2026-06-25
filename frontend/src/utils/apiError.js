const ERROR_MESSAGES = {
  permission_denied: '没有权限。请确认已登录，或在本地演示中设置 actor_token。',
  dataset_not_found: '找不到这份上传数据。请切回内置数据，或重新上传表格。',
  dataset_not_queryable: '这份上传数据还不能查询。请先完成审核并生成可查询数据。',
  invalid_dataset_id: '数据编号无效。请重新上传表格。',
  invalid_preflight: '查询前检查已失效。请重新预检后再查询。',
  invalid_tool_request: '请求内容不完整，请检查当前页面输入。',
};

export function formatApiError(payload, fallback = '请求失败') {
  const detail = payload?.detail ?? payload;
  if (typeof detail === 'string') {
    return detail || fallback;
  }
  if (!detail || typeof detail !== 'object') {
    return fallback;
  }
  const code = detail.code ? String(detail.code) : '';
  const message = detail.message ? String(detail.message) : '';
  const readable = ERROR_MESSAGES[code] || message || fallback;
  return code && readable !== code ? `${readable}（${code}）` : readable;
}
