import assert from 'node:assert/strict';
import test from 'node:test';

import {
  approveDomain,
  generateDomainPack,
  runDatasetQuery,
  uploadDataset,
} from './datasets.js';

test('uploadDataset sends raw file body without JSON content type', async () => {
  const originalFetch = globalThis.fetch;
  let request = null;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return {
      ok: true,
      async json() {
        return { dataset_id: 'ds_upload' };
      },
    };
  };
  try {
    const file = new Blob(['a,b\n1,2\n'], { type: 'text/csv' });
    file.name = 'rows.csv';

    const payload = await uploadDataset({ file });

    assert.equal(payload.dataset_id, 'ds_upload');
    assert.equal(request.options.body, file);
    assert.equal(new Headers(request.options.headers).has('Content-Type'), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('runDatasetQuery maps preflight confirmation fields exactly', async () => {
  const originalFetch = globalThis.fetch;
  let body = null;
  globalThis.fetch = async (_url, options) => {
    body = JSON.parse(options.body);
    return {
      ok: true,
      async json() {
        return { status: 'ok' };
      },
    };
  };
  try {
    await runDatasetQuery({
      datasetId: 'ds_query',
      domainName: 'leases',
      userInput: '找两房',
      hardFilters: { rent: { op: '<=', value: 3000 } },
      softPreferences: { prompt: '找两房' },
      preflightId: 'pf_current',
      confirmedBoundaries: [
        { confirmation_id: 'pfc_1', option_id: 'rank_window_steady' },
      ],
      disabledBoundaries: [
        { confirmation_id: 'pfc_2', option_id: 'do_not_use' },
      ],
    });

    assert.equal(body.preflight_id, 'pf_current');
    assert.deepEqual(body.confirmed_boundaries, [
      { confirmation_id: 'pfc_1', option_id: 'rank_window_steady' },
    ]);
    assert.deepEqual(body.disabled_boundaries, [
      { confirmation_id: 'pfc_2', option_id: 'do_not_use' },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('generateDomainPack defaults to a generic uploaded domain payload', async () => {
  const originalFetch = globalThis.fetch;
  let body = null;
  globalThis.fetch = async (_url, options) => {
    body = JSON.parse(options.body);
    return {
      ok: true,
      async json() {
        return { status: 'needs_review' };
      },
    };
  };
  try {
    await generateDomainPack('ds_generic', { llm: 'off' });

    assert.equal(body.llm, 'off');
    assert.equal(Object.hasOwn(body, 'template_id'), false);
    assert.equal(Object.hasOwn(body, 'base_domain'), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('approveDomain does not hide an implicit default_safe_sort decision', async () => {
  const originalFetch = globalThis.fetch;
  let body = null;
  globalThis.fetch = async (_url, options) => {
    body = JSON.parse(options.body);
    return {
      ok: true,
      async json() {
        return { status: 'approved' };
      },
    };
  };
  try {
    await approveDomain('ds_review');

    assert.equal(Object.hasOwn(body, 'default_safe_sort'), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
