import { requestJson } from './client.js';

export function getLlmSettings() {
  return requestJson('/settings/llm');
}

export function saveLlmSettings(payload) {
  return requestJson('/settings/llm', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
