export function defaultWorkbenchMode() {
  return 'api';
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
