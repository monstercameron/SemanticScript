# App

Top-level application workspace for runnable SemanticScript apps.

## Contents

- `todo/` contains the current console todo TUI sample app.

## Current Status

This folder is active app-development space. The current app demonstrates a
keyboard-driven terminal UI, JSON persistence, and native executable generation
from SemanticScript source.

## Maintenance

Keep app code on the top-level SemanticScript API where possible. Direct `c.*`
calls are acceptable only while the matching app-facing API surface is still
missing.
