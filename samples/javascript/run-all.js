'use strict';

const http = require('http');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

// Runs the finite benchmark scripts and smoke-tests the long-running webserver.
const scriptDirectory = __dirname;

const runScript = (scriptName, input) => {
  console.log('');
  console.log(`>>> node ${scriptName}`);

  const result = spawnSync(process.execPath, [path.join(scriptDirectory, scriptName)], {
    input: input || '',
    encoding: 'utf8',
  });

  if (result.stdout) {
    process.stdout.write(result.stdout);
  }

  if (result.stderr) {
    process.stderr.write(result.stderr);
  }

  if (result.status !== 0) {
    throw new Error(`${scriptName} exited with status ${result.status}`);
  }
};

const requestText = (url) => new Promise((resolve, reject) => {
  http.get(url, (response) => {
    let body = '';

    response.setEncoding('utf8');
    response.on('data', (chunk) => {
      body += chunk;
    });
    response.on('end', () => {
      resolve({
        statusCode: response.statusCode,
        body: body.trim(),
      });
    });
  }).on('error', reject);
});

const wait = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds);
});

const runWebserverSmokeTest = () => {
  console.log('');
  console.log('>>> node webserver-console.js');

  const serverProcess = spawn(process.execPath, [path.join(scriptDirectory, 'webserver-console.js')], {
    env: Object.assign({}, process.env, { PORT: '3140' }),
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  serverProcess.stdout.on('data', (chunk) => {
    process.stdout.write(chunk);
  });

  serverProcess.stderr.on('data', (chunk) => {
    process.stderr.write(chunk);
  });

  return wait(500)
    .then(() => Promise.all([
      requestText('http://127.0.0.1:3140/'),
      requestText('http://127.0.0.1:3140/health'),
    ]))
    .then((responses) => {
      console.log(`GET / => ${responses[0].statusCode} ${responses[0].body}`);
      console.log(`GET /health => ${responses[1].statusCode} ${responses[1].body}`);
      serverProcess.kill();
    })
    .catch((error) => {
      serverProcess.kill();
      throw error;
    });
};

const runAll = () => {
  runScript('hello-world.js');
  runScript('simple-calculator.js');
  runScript('number-stats.js');
  runScript('string-analyzer.js');
  runScript('json-order-summary.js');
  runScript('inventory-manager.js');
  runScript('event-workflow.js');
  runScript('async-workflow.js');
  runScript('complex-checkout-saga.js');
  runScript('esoteric-church-encoding.js');
  runScript('esoteric-stack-language.js');
  runScript('esoteric-self-referential.js');
  runScript('esoteric-trampoline.js');
  runScript('esoteric-reactive-proxy.js');
  runScript('counterintuitive-coercion.js');
  runScript('counterintuitive-numbers.js');
  runScript('counterintuitive-mutation.js');
  runScript('counterintuitive-closure-capture.js');
  runScript('counterintuitive-this-binding.js');
  runScript('counterintuitive-event-loop.js');
  runScript('file-inventory.js');
  runScript('todos-list.js', '1\n7\n');

  return runWebserverSmokeTest();
};

runAll().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
