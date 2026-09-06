// Runs the actual provider with deterministic hooks; transport supplied by the
// test can be real FastAPI. Not a substitute for React/phone visual testing.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import * as mealFlow from '../../src/domain/mealFlow.ts';
import * as fixtures from '../../src/fixtures/recommendationRequest.ts';
import * as kitchen from '../../src/domain/kitchen.ts';
import * as commerce from '../../src/domain/commerce.ts';

export function providerHarness(api, commerceHost) {
  const slots = [];
  let cursor = 0;
  const react = {
    createContext: () => ({ Provider: 'Provider' }), useContext: () => null,
    useCallback: (fn) => fn,
    useRef: (value) => { const i = cursor++; return slots[i] ?? (slots[i] = { current: value }); },
    useState: (initial) => {
      const i = cursor++;
      if (!(i in slots)) slots[i] = initial;
      return [slots[i], (next) => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }];
    },
  };
  const jsx = (type, props) => ({ type, props });
  const modules = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx }, '../api/endpoints': api,
    '../fixtures/recommendationRequest': fixtures, '../domain/mealFlow': mealFlow, '../domain/kitchen': kitchen,
    '../domain/commerce': commerce,
  };
  const source = readFileSync(new URL('../../src/state/DemoContext.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require: (id) => {
    assert.ok(id in modules, `Unexpected import: ${id}`); return modules[id];
  } });
  return () => { cursor = 0; return exports.DemoProvider({ children: null, commerceHost }).props.value; };
}
