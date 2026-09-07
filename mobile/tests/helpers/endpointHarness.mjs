// Executes the real endpoint adapters; tests replace only the HTTP transport.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import * as fixtures from '../../src/fixtures/recommendationRequest.ts';

export function endpointHarness(request) {
  const source = readFileSync(new URL('../../src/api/endpoints.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const modules = { './client': { request }, '../fixtures/recommendationRequest': fixtures };
  const exports = {};
  runInNewContext(compiled, { exports, require: (id) => {
    assert.ok(id in modules, `Unexpected import: ${id}`); return modules[id];
  } });
  return exports;
}
