# App

Top-level application workspace for runnable SemanticScript apps.

## Contents

- `todo/` contains the current console todo TUI sample app.
- `todo-web/` contains a web-server sample that returns a hello text response.
- `todo-web-advanced/` contains a route/method/request edge demo for the native
  HTTP API.
- `http-api-gauntlet/` contains a broad native HTTP API stress demo covering
  request reflection, body limits, binary body echo, multipart uploads,
  one-shot SSE, middleware, response headers, status codes, and negative
  runtime paths.

## Current Status

This folder is active app-development space. The current app demonstrates a
keyboard-driven terminal UI, JSON persistence, web-server metadata, and native
executable generation from SemanticScript source.

## Maintenance

Keep app code on the top-level SemanticScript API where possible. Direct `c.*`
calls are acceptable only while the matching app-facing API surface is still
missing.
