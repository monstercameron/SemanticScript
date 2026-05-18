# Feature Test Modules

Imported helpers and literal fixtures for feature tests.

## Contents

- `helper_lib.sscript` is imported by cross-file feature tests.
- `external_greeting_*.txt` files exercise external literal source loading.

## Current Status

Fixture-only support folder. These files exist to make feature tests cover
imports and literal loading without depending on external paths.

## Maintenance

Keep fixtures small and deterministic. If a test depends on a fixture, document
that dependency in the test's purpose or comments.
