'use strict';

const http = require('http');

const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 3000);

// Build responses explicitly so the server behavior is easy to inspect.
const createTextResponse = (statusCode, body) => ({
  statusCode,
  headers: {
    'content-type': 'text/plain; charset=utf-8',
  },
  body,
});

const routeRequest = (request) => {
  if (request.method === 'GET' && request.url === '/') {
    return createTextResponse(200, 'Hello from raw Node.js\n');
  }

  if (request.method === 'GET' && request.url === '/health') {
    return createTextResponse(200, 'ok\n');
  }

  return createTextResponse(404, 'not found\n');
};

const server = http.createServer((request, response) => {
  const routedResponse = routeRequest(request);

  // Keep a console trace for benchmark visibility without introducing logging deps.
  console.log(`${request.method} ${request.url} -> ${routedResponse.statusCode}`);

  response.writeHead(routedResponse.statusCode, routedResponse.headers);
  response.end(routedResponse.body);
});

server.listen(port, host, () => {
  console.log(`Server listening at http://${host}:${port}`);
});

// Exporting the server makes it easy for tests or benchmark harnesses to stop it.
module.exports = server;
