// Node harness that runs a MODULARIZE-built SemanticScript wasm module against
// a jsdom-provided DOM, optionally dispatches DOM events while the wasm `main`
// is suspended on an Asyncify await, then prints a JSON result snapshot.
//
// Completion is detected via Module.onExit, which fires after `main` truly
// returns -- including after an Asyncify resume. (The MODULARIZE factory
// promise is unreliable here: with Asyncify it resolves when main *suspends*,
// not when it finishes.) Build the module with EXIT_RUNTIME=1 so onExit fires.
//
// Usage:
//   node run_dom_harness.js '<config-json>'
//
// config: {
//   module:   absolute path to the emscripten .js factory (MODULARIZE),
//   html:     initial document HTML,
//   actions:  [{ selector, type, delayMs }]  // events to dispatch
//   timeoutMs: hard cap (default 5000)
// }
//
// output (stdout, one JSON object):
//   { ok, exitCode, stdout: [...], stderr: [...], bodyHtml, error }

'use strict';

const path = require('path');
const { JSDOM } = require('jsdom');

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

// Asyncify rethrows rewind failures into the global scope; surface them
// instead of letting the harness silently time out.
const _globalErrors = [];
process.on('uncaughtException', (e) => _globalErrors.push(String(e && e.stack || e)));
process.on('unhandledRejection', (e) => _globalErrors.push('unhandledRejection: ' + String(e && e.stack || e)));

async function main() {
  const config = JSON.parse(process.argv[2] || '{}');
  const html = config.html || '<!DOCTYPE html><html><body></body></html>';
  const timeoutMs = config.timeoutMs || 5000;

  const dom = new JSDOM(html, { runScripts: 'outside-only' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.self = dom.window;

  const stdout = [];
  const stderr = [];
  let settled = false;

  const snapshot = (extra) => Object.assign({
    stdout,
    stderr,
    globalErrors: _globalErrors,
    bodyHtml: document.body ? document.body.innerHTML : null,
  }, extra);

  const finish = (obj) => {
    if (settled) return;
    settled = true;
    clearTimeout(hardTimeout);
    emit(obj);
    // Give stdout a tick to flush, then exit so a kept-alive runtime (pending
    // listeners) does not hang the harness.
    setImmediate(() => process.exit(0));
  };

  const hardTimeout = setTimeout(() => finish(snapshot({ ok: false, error: 'timeout' })), timeoutMs);

  const factory = require(path.resolve(config.module));
  if (typeof factory !== 'function') {
    finish({ ok: false, error: 'module did not export a MODULARIZE factory' });
    return;
  }

  // Queue DOM event dispatches: they fire on the event loop while wasm `main`
  // is suspended on a nextEvent await, then the await resolves and main resumes.
  for (const action of config.actions || []) {
    setTimeout(() => {
      const target = action.selector ? document.querySelector(action.selector) : document;
      if (target) {
        target.dispatchEvent(new dom.window.Event(action.type, { bubbles: true }));
      }
    }, action.delayMs || 25);
  }

  try {
    await factory({
      print: (s) => stdout.push(s),
      printErr: (s) => stderr.push(s),
      onExit: (code) => finish(snapshot({ ok: code === 0, exitCode: code })),
    });
  } catch (e) {
    // ExitStatus is thrown by emscripten on exit; onExit already reported it.
    if (!settled) finish({ ok: false, error: (e && e.stack) ? e.stack : String(e), stdout, stderr });
  }
}

main().catch((e) => emit({ ok: false, error: String(e) }));
