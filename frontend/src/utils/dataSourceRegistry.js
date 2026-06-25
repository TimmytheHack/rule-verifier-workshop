import { BUILTIN_ADMISSIONS_SOURCE } from '../domain/admissionsAdapter.js';

export const DATA_SOURCES_STORAGE_KEY = 'szu_uploaded_data_sources';
export const SELECTED_SOURCE_STORAGE_KEY = 'szu_selected_data_source';

export function browserStorage() {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadUploadedDataSources(storage) {
  try {
    const activeStorage = storage === undefined ? browserStorage() : storage;
    const raw = activeStorage?.getItem(DATA_SOURCES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((source) => source?.id && source?.datasetId && source?.domainName)
      : [];
  } catch {
    return [];
  }
}

export function loadSelectedDataSourceId(options = {}) {
  try {
    const { storage, sources = [] } = options || {};
    const activeStorage = storage === undefined ? browserStorage() : storage;
    const saved = activeStorage?.getItem(SELECTED_SOURCE_STORAGE_KEY);
    if (
      saved === BUILTIN_ADMISSIONS_SOURCE.id
      || sources.some((source) => source.id === saved)
    ) {
      return saved;
    }
  } catch {
    return BUILTIN_ADMISSIONS_SOURCE.id;
  }
  return BUILTIN_ADMISSIONS_SOURCE.id;
}

export function mergeUploadedDataSource(currentSources, source, limit = 5) {
  if (!source?.id) {
    return [...(currentSources || [])];
  }
  return [
    source,
    ...(currentSources || []).filter((item) => item.id !== source.id),
  ].slice(0, limit);
}

export function persistUploadedDataSources(storage, value = []) {
  try {
    const activeStorage = storage === undefined ? browserStorage() : storage;
    activeStorage?.setItem(DATA_SOURCES_STORAGE_KEY, JSON.stringify(value));
  } catch {
    return undefined;
  }
}

export function persistSelectedDataSourceId(storage, value) {
  try {
    const activeStorage = storage === undefined ? browserStorage() : storage;
    activeStorage?.setItem(SELECTED_SOURCE_STORAGE_KEY, value || BUILTIN_ADMISSIONS_SOURCE.id);
  } catch {
    return undefined;
  }
}
